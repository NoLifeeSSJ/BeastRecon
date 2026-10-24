# BeastRecon V1.1 Media Converter

A Python desktop app for converting a YouTube/media URL or local file to MP3, M4A, WAV, FLAC, MP4, or WebM. MP3 downloads select the audio stream where available, avoiding the full video download. Audio-to-video conversion creates a black video background.

## Windows: install or update

Close BeastRecon first. Paste this entire block into PowerShell from any folder:

```powershell
& {
    $ErrorActionPreference = 'Stop'
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    New-Item -ItemType Directory -Path 'C:\BeastRecon' -Force | Out-Null
    $installer = Join-Path 'C:\BeastRecon' ('Install-Update-' + [guid]::NewGuid() + '.ps1')
    try {
        Invoke-WebRequest -UseBasicParsing -Uri 'https://raw.githubusercontent.com/NoLifeeSSJ/BeastRecon/main/Install.ps1' -OutFile $installer
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $installer
        if ($LASTEXITCODE -ne 0) { throw 'Installation failed. Check the error above.' }
    } finally {
        Remove-Item $installer -ErrorAction SilentlyContinue
    }
}
```

The installer downloads the app and its update staging files into `C:\BeastRecon`, installs Python and FFmpeg if missing, and updates yt-dlp with its official JavaScript solver and Deno runtime extras. It checks Tk, Deno, and a real local audio conversion before reporting success. It preserves `preferences.json` and the `Downloads` folder. It repairs a broken app virtual environment while keeping a backup, leaves unrelated Python environments alone, and creates Desktop and Start menu shortcuts with the BeastRecon icon. App Installer (winget) is needed to install missing Python/FFmpeg prerequisites.

Updates refresh Desktop and Start menu shortcuts to point at `C:\BeastRecon`. Any older installation under `%LOCALAPPDATA%` is left intact; your old downloads are kept. App-managed preferences are stored in `C:\BeastRecon\preferences.json`.

Launch with the Desktop or Start menu shortcut. To pin the app, right-click its running taskbar icon and choose **Pin to taskbar**. Windows controls pinning. If an old taskbar pin still opens V1.0, unpin it, launch the refreshed Desktop shortcut, and pin the new running app. The Windows installer and shortcuts still require testing on Windows; development checks run on Linux.

## Convert and play

1. Open **Preferences / About → Preferences** to set your permanent download folder. The Windows default is `C:\BeastRecon\Downloads`. The same window has **About** and the full **Changelog**, including the V1.0 development history.
2. Paste a video URL or browse for a local file. An automatic text preview shows the title, creator and duration when available; it loads after typing pauses. **Preview** also fetches it manually. This reads metadata without downloading the media or thumbnails.
3. Select **MP3** for audio or another format, then press **Download**. The app saves using the actual video/song title. Existing filenames receive `(2)`, `(3)`, etc. Invalid Windows filename characters are removed, and very long titles are shortened.
4. Watch activity details, download percentage/speed where available, and conversion progress. **Cancel** stops the job; a pending network request may take time to return.
5. When saving finishes, choose **Play file** to open your default media player or **Open folder** to locate the result.

The app remembers your selected output format. Preferences can turn automatic previews off; the manual Preview button remains available. If preview fails, you can still try Download. The title is refreshed during the download so an old preview cannot name the wrong file. Local files use their embedded title when present, otherwise the filename.

Intermediate media files use temporary storage and are cleaned up. Failed or cancelled conversions do not keep a partial output file. Large files need space for both the downloaded media and the converted output. Closing the app during conversion asks to cancel and waits for cleanup.

## YouTube troubleshooting

- Close the app and rerun the installer above to update yt-dlp, yt-dlp-ejs, and Deno. YouTube changes frequently; these components must stay current.
- If a conversion fails, use **Copy details** and include the text when reporting the problem. The activity panel includes download notices and the final error.
- An account requirement, age/region restriction, network proxy, or YouTube anti-bot verification can still prevent downloads. The app shows specific guidance; it does not bypass those restrictions or automatically read browser cookies.
- Playlists, channels, live/upcoming videos, and DRM-protected media are unsupported. For a URL that includes both a video and a playlist, only the video is selected.
- Use media you own or have permission to download. Not every site supported by yt-dlp guarantees a downloadable file.

## Manual development

Install Python 3.10+ with Tk, and FFmpeg (`ffmpeg` and `ffprobe` on PATH). Ubuntu/Debian package names are `python3-tk python3-venv ffmpeg`. Windows Python's standard installer includes Tk; FFmpeg can be installed with `winget install Gyan.FFmpeg`.

From this repository:

```sh
python -m venv .venv
```

Activate with `.venv\Scripts\activate` on Windows or `source .venv/bin/activate` on Linux/macOS:

```sh
python -m pip install --upgrade -r requirements.txt
python app.py
```

`Start-Windows.bat` is also available for launching from a source checkout. The application discovers the virtual environment's Deno binary even when launched through `pythonw.exe` without activation. No standalone `.exe` release is provided; packaging would also need to bundle the JavaScript runtime and solver.

## Validate

```sh
python -m unittest discover -s tests -v
```

Tests exercise preferences across restarts, automatic/manual/stale previews, safe title filenames, duplicate naming, one-click saving without a Save dialog, and FFmpeg conversions and decoding for every output format, local HTTP download-to-MP3, audio/video download selection, cancellation/partial-file cleanup, and restriction/error handling. YouTube option-selection tests use fixtures; they do not prove live YouTube access. Desktop tests require a display and otherwise report as skipped; under Xvfb they exercise conversion, playback/file-manager dispatch, cancellation, and copied error details. Windows media-player launching still needs a check on Windows.

Preview displays the title, creator and duration when available.

Live YouTube testing in the cloud workspace was blocked by its network proxy (HTTP 403), so the YouTube end-to-end check must be completed on a connection that permits YouTube access.
