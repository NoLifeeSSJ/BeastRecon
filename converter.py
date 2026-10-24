"""Media conversion engine; requires FFmpeg and yt-dlp for URLs."""
from pathlib import Path
import shutil
import subprocess
import tempfile
from urllib.parse import urlsplit

FORMATS = ('mp3', 'm4a', 'wav', 'flac', 'mp4', 'webm')


def run(command):
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(result.stderr.strip()[-3000:] or 'Command failed')
    return result.stdout


def convert(source, destination, progress=lambda message: None):
    target = Path(destination).expanduser().resolve()
    extension = target.suffix.lower().lstrip('.')
    if extension not in FORMATS:
        raise ValueError('Unsupported output format')
    for binary in ('ffmpeg', 'ffprobe'):
        if not shutil.which(binary):
            raise RuntimeError(f'{binary} is missing. Install FFmpeg and add it to PATH.')
    if target.exists():
        raise ValueError('Output already exists. Choose a new filename.')
    if not target.parent.is_dir():
        raise ValueError('Output folder does not exist.')
    with tempfile.TemporaryDirectory(prefix='beastrecon-') as temporary:
        parsed = urlsplit(source)
        if parsed.scheme in ('http', 'https'):
            if not parsed.hostname:
                raise ValueError('Enter a valid HTTP or HTTPS URL.')
            progress('Downloading media…')
            try:
                import yt_dlp
            except ImportError:
                raise RuntimeError('URL support requires yt-dlp. Install requirements.txt first.') from None
            with yt_dlp.YoutubeDL({
                'noplaylist': True, 'quiet': True, 'noprogress': True,
                'restrictfilenames': True,
                'outtmpl': str(Path(temporary) / 'source.%(ext)s'),
            }) as downloader:
                downloader.download([source])
            candidates = [p for p in Path(temporary).glob('source.*') if p.suffix != '.part']
            if len(candidates) != 1:
                raise RuntimeError('Download did not produce one media file.')
            media = candidates[0]
        else:
            media = Path(source).expanduser().resolve()
            if not media.is_file():
                raise ValueError('Select an existing media file or enter an HTTP/HTTPS URL.')
            if media == target:
                raise ValueError('Input and output must be different files.')
        progress('Converting media…')
        import json
        streams = json.loads(run(['ffprobe', '-v', 'error', '-show_streams', '-of', 'json', str(media)]))['streams']
        video = any(s['codec_type'] == 'video' for s in streams)
        audio = any(s['codec_type'] == 'audio' for s in streams)
        command = ['ffmpeg', '-hide_banner', '-loglevel', 'error', '-nostdin', '-n', '-i', str(media)]
        if extension in ('mp4', 'webm'):
            if not video:
                if not audio:
                    raise ValueError('No audio or video stream found.')
                command += ['-f', 'lavfi', '-i', 'color=c=black:s=1280x720:r=25', '-map', '1:v:0', '-map', '0:a:0', '-shortest']
            else:
                command += ['-map', '0:v:0', '-map', '0:a:0?']
            command += (['-c:v', 'libx264', '-preset', 'fast', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-movflags', '+faststart']
                        if extension == 'mp4' else ['-c:v', 'libvpx-vp9', '-c:a', 'libopus'])
        else:
            if not audio:
                raise ValueError('This file has no audio to extract.')
            command += ['-map', '0:a:0', '-vn']
            command += {'mp3': ['-c:a', 'libmp3lame', '-q:a', '2'], 'm4a': ['-c:a', 'aac', '-b:a', '192k'],
                        'wav': ['-c:a', 'pcm_s16le'], 'flac': ['-c:a', 'flac']}[extension]
        staged = Path(temporary) / ('converted.' + extension)
        run(command + [str(staged)])
        # Exclusive creation prevents overwriting files created while converting.
        try:
            with target.open('xb') as output, staged.open('rb') as converted:
                shutil.copyfileobj(converted, output)
        except FileExistsError:
            raise ValueError('Output already exists. Choose a new filename.') from None
    progress(f'Saved: {target}')
    return target
