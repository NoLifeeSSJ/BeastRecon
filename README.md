# BeastRecon Media Converter

A native Python desktop app for converting local media and media URLs to MP3, M4A, WAV, FLAC, MP4, or WebM. URL support uses yt-dlp; site availability varies. MP3 to MP4 adds a black video background. DRM-protected sources are unsupported.

## Run

Install Python 3.10+ with Tk and FFmpeg (both `ffmpeg` and `ffprobe` must be on PATH). On Windows, Python's standard installer includes Tk; FFmpeg can be installed with `winget install Gyan.FFmpeg` followed by opening a new terminal. On Ubuntu, install `python3-tk python3-venv ffmpeg`.

On Windows, run `powershell -NoProfile -ExecutionPolicy Bypass -File .\Install.ps1` to install Python, FFmpeg, and the app dependencies using winget, then launch the app. App Installer (winget) is required. The installer may ask you to reopen PowerShell after installing prerequisites.

For later launches, double-click `Start-Windows.bat` after installing Python and FFmpeg. It creates a virtual environment, installs URL support, and opens the app.

For manual setup, from this repository:

```sh
python -m venv .venv
```

Activate with `.venv\Scripts\activate` on Windows or `source .venv/bin/activate` on Linux/macOS, then:

```sh
python -m pip install -r requirements.txt
python app.py
```

Paste a URL or browse for a file, choose the output format, and click **Convert and save**. Existing output files are never overwritten; choose a new filename. Downloads use temporary storage and are removed after conversion. Large files need enough space for both input and output. Conversion runs in the background; closing the app interrupts it.

## Optional executable

On the target operating system, inside the activated environment:

```sh
python -m pip install pyinstaller
pyinstaller --windowed --onefile --name BeastRecon --collect-all yt_dlp app.py
```

The executable appears in `dist`. FFmpeg must still be installed on the user's PATH. Cross-platform executable builds are not supported by PyInstaller; build Windows executables on Windows.

## Validate

```sh
python -m unittest discover -s tests -v
```

The integration tests require FFmpeg. URL downloads additionally require Internet access; no external sites are contacted by the tests. Use media you own or have permission to download.

## Windows installer and shortcuts

`Install.ps1` now runs from any folder. It downloads the application into `%LOCALAPPDATA%\BeastRecon`, installs missing prerequisites, repairs a broken app virtual environment (keeping a backup), checks Tk and an actual audio conversion, then creates Desktop and Start menu shortcuts with the BeastRecon icon. Rerun it to update or repair the installation. It leaves unrelated Python environments alone.

Windows controls taskbar pinning: launch BeastRecon, right-click its taskbar icon, and choose **Pin to taskbar**. The installer does not use unsupported pinning hacks. Windows installation and shortcut behavior still require testing on Windows.
