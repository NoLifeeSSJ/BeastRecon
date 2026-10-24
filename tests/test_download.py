from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import patch

from converter import ConversionCancelled, _download, _download_error, convert


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


class DownloadTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / 'fixture.wav'
        subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i',
                        'sine=frequency=440:duration=0.3', str(self.source)], check=True)

    def test_http_url_to_decodable_mp3_with_progress(self):
        server = ThreadingHTTPServer(('127.0.0.1', 0), partial(QuietHandler, directory=str(self.root)))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        progress = []
        target = convert(f'http://127.0.0.1:{server.server_port}/fixture.wav',
                         self.root / 'result.mp3', progress.append)
        subprocess.run(['ffmpeg', '-v', 'error', '-i', str(target), '-f', 'null', '-'], check=True)
        self.assertGreater(target.stat().st_size, 0)
        self.assertTrue(any(message.startswith('Downloading audio') for message in progress))
        self.assertTrue(any(message.startswith('Converting media') for message in progress))
        self.assertTrue(progress[-1].startswith('Saved:'))

    def test_separate_video_and_audio_streams_are_merged(self):
        video = self.root / 'video.mp4'
        subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i',
                        'color=c=blue:s=160x90:d=0.3', '-c:v', 'libx264', str(video)], check=True)
        server = ThreadingHTTPServer(('127.0.0.1', 0), partial(QuietHandler, directory=str(self.root)))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        base = f'http://127.0.0.1:{server.server_port}'
        info = {
            'id': 'fixture', 'title': 'Fixture', 'extractor': 'generic',
            'webpage_url': base + '/fixture',
            'formats': [
                {'format_id': 'audio', 'url': base + '/fixture.wav', 'ext': 'wav',
                 'vcodec': 'none', 'acodec': 'pcm_s16le'},
                {'format_id': 'video', 'url': base + '/video.mp4', 'ext': 'mp4',
                 'vcodec': 'h264', 'acodec': 'none', 'width': 160, 'height': 90},
            ],
        }
        # Fixture replaces only remote extraction; real yt-dlp selection, HTTP
        # downloads, merging, and final FFmpeg conversion all execute.
        import yt_dlp
        with patch.object(yt_dlp.YoutubeDL, 'extract_info', return_value=info):
            output = convert(base + '/fixture', self.root / 'result.mp4')
        import json
        streams = json.loads(subprocess.check_output(['ffprobe', '-v', 'error', '-show_streams', '-of', 'json', str(output)]))['streams']
        self.assertEqual({stream['codec_type'] for stream in streams}, {'audio', 'video'})

    def test_audio_and_video_select_appropriate_download_formats(self):
        for extension, expected in [('mp3', 'bestaudio/best'), ('m4a', 'bestaudio/best'),
                                    ('mp4', 'bestvideo*+bestaudio/best')]:
            with self.subTest(extension=extension), tempfile.TemporaryDirectory() as download:
                with patch('yt_dlp.YoutubeDL') as factory:
                    downloader = factory.return_value.__enter__.return_value
                    downloader.extract_info.return_value = {'title': 'Fixture'}
                    downloader.process_ie_result.side_effect = lambda *args, **kwargs: shutil.copyfile(self.source, Path(download) / 'source.wav')
                    _download('https://youtu.be/fixture', download, extension, lambda m: None, None)
                    options = factory.call_args.args[0]
                    self.assertEqual(options['format'], expected)
                    self.assertTrue(options['noplaylist'])
                    self.assertTrue(options['js_runtimes'])
                    self.assertEqual(options['socket_timeout'], 15)
                    downloader.extract_info.assert_called_once_with('https://youtu.be/fixture', download=False)

    def test_playlist_and_live_video_rejected_before_downloading(self):
        for metadata in ({'_type': 'playlist', 'entries': []}, {'is_live': True}, {'live_status': 'is_upcoming'}):
            with self.subTest(metadata=metadata), patch('yt_dlp.YoutubeDL') as factory:
                downloader = factory.return_value.__enter__.return_value
                downloader.extract_info.return_value = metadata
                with self.assertRaises(ValueError):
                    _download('https://youtu.be/fixture', self.root, 'mp3', lambda m: None, None)
                downloader.process_ie_result.assert_not_called()

    def test_download_cancellation_leaves_no_output(self):
        cancel = threading.Event()
        with patch('yt_dlp.YoutubeDL') as factory:
            downloader = factory.return_value.__enter__.return_value
            downloader.extract_info.return_value = {'title': 'Fixture'}
            def download(*args, **kwargs):
                cancel.set()
                factory.call_args.args[0]['progress_hooks'][0]({'status': 'downloading'})
            downloader.process_ie_result.side_effect = download
            with self.assertRaises(ConversionCancelled):
                convert('https://youtu.be/fixture', self.root / 'result.mp3', cancel=cancel)
        self.assertFalse((self.root / 'result.mp3').exists())

    def test_cancellation_during_conversion_or_save_leaves_no_partial_file(self):
        for stage in ('Converting media', 'Saving converted file'):
            with self.subTest(stage=stage):
                cancel = threading.Event()
                def progress(message):
                    if message.startswith(stage):
                        cancel.set()
                target = self.root / 'result.mp3'
                with self.assertRaises(ConversionCancelled):
                    convert(str(self.source), target, progress, cancel)
                self.assertFalse(target.exists())

    def test_error_advice_distinguishes_network_and_youtube_verification(self):
        network = str(_download_error('Tunnel connection failed: 403 Forbidden; Confirm you are on the latest version'))
        self.assertIn('network proxy', network)
        self.assertNotIn('YouTube is requesting verification', network)
        self.assertIn('YouTube is requesting verification', str(_download_error("Sign in to confirm you're not a bot")))
        self.assertIn('refresh yt-dlp', str(_download_error('HTTP Error 403: Forbidden')))

    def test_missing_javascript_runtime_reports_repair_action(self):
        with patch('converter.shutil.which', return_value=None):
            with self.assertRaisesRegex(RuntimeError, 'Deno.*Install.ps1'):
                _download('https://www.youtube.com/watch?v=fixture', self.root, 'mp3', lambda m: None, None)
