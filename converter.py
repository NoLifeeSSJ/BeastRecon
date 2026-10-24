"""Download and convert media without depending on the caller's working directory."""
from dataclasses import dataclass
import json
import os
from pathlib import Path
import queue
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unicodedata
from urllib.parse import urlsplit

FORMATS = ('mp3', 'm4a', 'wav', 'flac', 'mp4', 'webm')
AUDIO_FORMATS = ('mp3', 'm4a', 'wav', 'flac')


class ConversionCancelled(Exception):
    """The user stopped the current conversion."""


def prepare_runtime():
    """Explorer/pythonw launches don't activate the virtual environment's PATH."""
    folders = [str(Path(sys.executable).parent)]
    if os.name == 'nt':
        folders.append(str(Path(os.environ.get('LOCALAPPDATA', '')) / 'Microsoft/WinGet/Links'))
    current = os.environ.get('PATH', '').split(os.pathsep)
    os.environ['PATH'] = os.pathsep.join(folders + [p for p in current if p not in folders])


def _check_cancel(cancel):
    if cancel is not None and cancel.is_set():
        raise ConversionCancelled('Conversion cancelled.')


def _process_options():
    return {'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {}


def run(command):
    result = subprocess.run(command, capture_output=True, text=True, encoding='utf-8',
                            errors='replace', timeout=30, **_process_options())
    if result.returncode:
        raise RuntimeError(result.stderr.strip()[-3000:] or 'Command failed')
    return result.stdout


def _transcode(command, duration, progress, cancel):
    """Drain FFmpeg output while keeping cancellation responsive on Windows too."""
    updates = queue.Queue()
    with tempfile.TemporaryFile(mode='w+t', encoding='utf-8') as errors:
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=errors,
                                   text=True, encoding='utf-8', errors='replace', **_process_options())
        def read_output():
            for line in process.stdout:
                updates.put(line.strip())
        reader = threading.Thread(target=read_output, daemon=True)
        reader.start()
        try:
            while process.poll() is None or reader.is_alive() or not updates.empty():
                _check_cancel(cancel)
                try:
                    line = updates.get(timeout=0.1)
                except queue.Empty:
                    continue
                if line.startswith('out_time_us=') and duration:
                    try:
                        percent = min(99, max(0, int(float(line.split('=', 1)[1]) / 10000 / duration)))
                    except ValueError:
                        continue
                    progress(f'Converting media… {percent}%')
            if process.wait():
                errors.seek(0)
                raise RuntimeError(errors.read()[-3000:] or 'FFmpeg conversion failed.')
        finally:
            if process.poll() is None:
                process.kill()
            process.wait()
            reader.join()
            process.stdout.close()


def _clean_message(message):
    return re.sub(r'\x1b\[[0-9;]*m', '', str(message)).strip()


class _DownloadLogger:
    def __init__(self, progress, cancel):
        self.progress = progress
        self.cancel = cancel

    def debug(self, message):
        _check_cancel(self.cancel)

    def info(self, message):
        pass

    def warning(self, message):
        _check_cancel(self.cancel)
        self.progress('Download notice: ' + _clean_message(message))

    def error(self, message):
        # yt-dlp raises DownloadError as well; report it once with actionable context.
        pass


def _download_error(error):
    text = _clean_message(error)
    lower = text.lower()
    if any(word in lower for word in ('tunnel connection failed', 'unable to connect to proxy')):
        advice = 'The network proxy blocked or could not reach the media site. Check your proxy, firewall, or network access settings.'
    elif any(word in lower for word in ('sign in', 'sign-in', 'not a bot', 'po token')):
        advice = ('YouTube is requesting verification for this connection. Try a public video that does not '
                  'require sign-in, update BeastRecon, or retry on your normal home connection. '
                  'Videos requiring an account may remain unavailable in this app.')
    elif any(word in lower for word in ('403', 'forbidden', 'signature', 'challenge', 'javascript', 'js runtime')):
        advice = ('Update BeastRecon using Install.ps1 to refresh yt-dlp, its YouTube solver, and Deno. '
                  'YouTube may also be blocking this connection; an update cannot guarantee access.')
    elif any(word in lower for word in ('private video', 'unavailable', 'removed', 'not available', 'age-restricted')):
        advice = 'This video is unavailable or restricted. Try a public video accessible in your region without signing in.'
    elif 'certificate' in lower:
        advice = 'Check your PC clock and network certificate settings. TLS verification has been kept enabled.'
    else:
        advice = 'Check the link and your connection. Rerun Install.ps1 to update YouTube support if the problem continues.'
    return RuntimeError(f'{advice}\n\nDownload details:\n{text[-3000:]}')


@dataclass(frozen=True)
class MediaInfo:
    title: str
    creator: str = ''
    duration: float | None = None


def _media_info(info):
    duration = info.get('duration')
    return MediaInfo(str(info.get('title') or 'BeastRecon'),
                     str(info.get('artist') or info.get('uploader') or info.get('channel') or ''),
                     float(duration) if duration is not None else None)


def _validate_info(info):
    if not info or info.get('_type') in ('playlist', 'multi_video') or 'entries' in info:
        raise ValueError('Paste a link to one video, rather than a playlist or channel.')
    if info.get('is_live') or info.get('live_status') in ('is_live', 'is_upcoming', 'post_live'):
        raise ValueError('Live or upcoming videos are not supported. Try a finished video.')


def _url_options(source, progress, cancel):
    runtimes = {name: {'path': path} for name in ('deno', 'node') if (path := shutil.which(name))}
    host = (urlsplit(source).hostname or '').lower()
    youtube = host == 'youtu.be' or host == 'youtube.com' or host.endswith('.youtube.com')
    if youtube and not runtimes:
        raise RuntimeError('YouTube support needs the Deno JavaScript runtime. Rerun Install.ps1 to install it.')
    return {
        'noplaylist': True, 'extract_flat': 'in_playlist', 'lazy_playlist': True,
        'quiet': True, 'noprogress': True, 'no_color': True,
        'logger': _DownloadLogger(progress, cancel),
        'socket_timeout': 15, 'retries': 2, 'fragment_retries': 2, 'extractor_retries': 2,
        'js_runtimes': runtimes,
    }


def inspect_media(source, cancel=None):
    """Read a title/creator/duration without downloading the media or thumbnails."""
    prepare_runtime()
    _check_cancel(cancel)
    if urlsplit(source).scheme not in ('http', 'https'):
        media = Path(source).expanduser().resolve()
        if not media.is_file():
            raise ValueError('Choose an existing media file or paste a media URL.')
        return MediaInfo(media.stem)
    import yt_dlp
    options = _url_options(source, lambda message: None, cancel)
    options['format'] = 'bestaudio/best'
    try:
        with yt_dlp.YoutubeDL(options) as downloader:
            info = downloader.extract_info(source, download=False)
        _check_cancel(cancel)
        _validate_info(info)
        return _media_info(info)
    except yt_dlp.utils.DownloadError as error:
        _check_cancel(cancel)
        raise _download_error(error) from error


def safe_filename(title):
    """Keep readable Unicode titles while respecting Windows filename rules."""
    title = unicodedata.normalize('NFC', str(title))
    title = re.sub(r'[<>:"/\\|?*\x00-\x1f\x7f]', ' ', title)
    title = re.sub(r'\s+', ' ', title).strip(' .')
    title = title.encode('utf-8')[:160].decode('utf-8', errors='ignore').rstrip(' .') or 'BeastRecon'
    if re.fullmatch(r'(CON|PRN|AUX|NUL|COM[1-9¹²³]|LPT[1-9¹²³])', title.split('.')[0].rstrip(' .').upper()):
        title = '_' + title
    return title


def unique_destination(directory, title, extension):
    if extension not in FORMATS:
        raise ValueError('Unsupported output format')
    stem = safe_filename(title)
    target = Path(directory) / f'{stem}.{extension}'
    number = 2
    while target.exists() or target.is_symlink():
        target = Path(directory) / f'{stem} ({number}).{extension}'
        number += 1
    return target


def _download(source, temporary, extension, progress, cancel, on_metadata=None):
    try:
        import yt_dlp
    except ImportError:
        raise RuntimeError('URL support is missing. Rerun Install.ps1.') from None
    _check_cancel(cancel)
    last_update = 0.0
    audio_only = extension in AUDIO_FORMATS
    label = 'Downloading audio' if audio_only else 'Downloading media'

    def hook(data):
        nonlocal last_update
        _check_cancel(cancel)
        if data['status'] == 'finished':
            progress('Download finished. Preparing conversion…')
            return
        if data['status'] != 'downloading' or time.monotonic() - last_update < 0.25:
            return
        last_update = time.monotonic()
        total = data.get('total_bytes') or data.get('total_bytes_estimate')
        downloaded = data.get('downloaded_bytes', 0)
        amount = f'{downloaded / 1048576:.1f} MB'
        percent = f'{min(100, downloaded / total * 100):.0f}% • ' if total else ''
        speed = data.get('speed')
        speed_text = f' • {speed / 1048576:.1f} MB/s' if speed else ''
        eta = data.get('eta')
        eta_text = f' • {int(eta)}s left' if eta is not None else ''
        progress(f'{label}… {percent}{amount}{speed_text}{eta_text}')

    def postprocess_hook(data):
        _check_cancel(cancel)
        if data['status'] == 'started':
            progress('Preparing downloaded media…')

    options = _url_options(source, progress, cancel)
    options.update({
        'format': 'bestaudio/best' if audio_only else 'bestvideo*+bestaudio/best',
        'merge_output_format': 'mkv',
        'restrictfilenames': True,
        'outtmpl': str(Path(temporary) / 'source.%(ext)s'),
        'concurrent_fragment_downloads': 1,
        'progress_hooks': [hook], 'postprocessor_hooks': [postprocess_hook],
    })
    progress('Reading media details…')
    try:
        with yt_dlp.YoutubeDL(options) as downloader:
            info = downloader.extract_info(source, download=False)
            _check_cancel(cancel)
            _validate_info(info)
            if on_metadata is not None:
                on_metadata(_media_info(info))
            progress(f"{label}… {info.get('title') or 'media'}")
            downloader.process_ie_result(info, download=True)
    except yt_dlp.utils.DownloadError as error:
        _check_cancel(cancel)
        raise _download_error(error) from error
    _check_cancel(cancel)
    candidates = [p for p in Path(temporary).glob('source.*')
                  if p.is_file() and p.suffix not in ('.part', '.ytdl', '.json', '.jpg', '.png', '.webp')]
    if len(candidates) != 1:
        raise RuntimeError('The download did not produce one complete media file. Try updating BeastRecon.')
    return candidates[0]


def convert(source, destination, progress=lambda message: None, cancel=None):
    return _convert(source, Path(destination), progress, cancel)


def convert_to_folder(source, directory, extension, progress=lambda message: None, cancel=None, on_metadata=None):
    """Save using the actual media title, keeping existing files intact."""
    return _convert(source, None, progress, cancel, directory=directory,
                    extension=extension, on_metadata=on_metadata)


def _convert(source, destination, progress, cancel, *, directory=None, extension=None, on_metadata=None):
    prepare_runtime()
    _check_cancel(cancel)
    target = destination.expanduser().resolve() if destination is not None else None
    if target is not None:
        extension = target.suffix.lower().lstrip('.')
    else:
        directory = Path(directory).expanduser().resolve()
        directory.mkdir(parents=True, exist_ok=True)
    if extension not in FORMATS:
        raise ValueError('Unsupported output format')
    for binary in ('ffmpeg', 'ffprobe'):
        if not shutil.which(binary):
            raise RuntimeError(f'{binary} is missing. Rerun Install.ps1 to install FFmpeg.')
    if target is not None and target.exists():
        raise ValueError('Output already exists. Choose a new filename.')
    if target is not None and not target.parent.is_dir():
        raise ValueError('Output folder does not exist.')
    title = 'BeastRecon'
    def metadata(info):
        nonlocal title
        title = info.title
        if on_metadata is not None:
            on_metadata(info)
    with tempfile.TemporaryDirectory(prefix='beastrecon-') as temporary:
        parsed = urlsplit(source)
        if parsed.scheme in ('http', 'https'):
            if not parsed.hostname:
                raise ValueError('Enter a valid HTTP or HTTPS URL.')
            media = _download(source, temporary, extension, progress, cancel, metadata)
        else:
            media = Path(source).expanduser().resolve()
            if not media.is_file():
                raise ValueError('Select an existing media file or enter an HTTP/HTTPS URL.')
            if media == target:
                raise ValueError('Input and output must be different files.')
        _check_cancel(cancel)
        progress('Checking downloaded media…')
        probe = json.loads(run(['ffprobe', '-v', 'error', '-show_streams', '-show_format', '-of', 'json', str(media)]))
        streams = probe['streams']
        duration = float(probe.get('format', {}).get('duration') or 0)
        if parsed.scheme not in ('http', 'https'):
            tags = probe.get('format', {}).get('tags', {})
            metadata(MediaInfo(tags.get('title') or media.stem, tags.get('artist') or '', duration))
        video = any(s['codec_type'] == 'video' for s in streams)
        audio = any(s['codec_type'] == 'audio' for s in streams)
        command = ['ffmpeg', '-hide_banner', '-loglevel', 'error', '-nostdin', '-n',
                   '-progress', 'pipe:1', '-stats_period', '0.5', '-i', str(media)]
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
        progress('Converting media…')
        _transcode(command + [str(staged)], duration, progress, cancel)
        _check_cancel(cancel)
        progress('Saving converted file…')
        # Reserve the name only after conversion. A concurrent download may have
        # claimed it since metadata was read; select the next suffix in that case.
        while True:
            if destination is None:
                target = unique_destination(directory, title, extension)
            try:
                output = target.open('xb')
                break
            except FileExistsError:
                if destination is not None:
                    raise ValueError('Output already exists. Choose a new filename.') from None
        try:
            with output, staged.open('rb') as converted:
                while chunk := converted.read(1024 * 1024):
                    _check_cancel(cancel)
                    output.write(chunk)
        except BaseException:
            target.unlink(missing_ok=True)
            raise
    progress(f'Saved: {target}')
    return target
