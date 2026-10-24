# Standalone installer. Safe to run from any working directory.
$ErrorActionPreference = 'Stop'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

function Invoke-Checked {
    param([scriptblock]$Command)
    & $Command
    if ($LASTEXITCODE -ne 0) { throw "Command failed with exit code $LASTEXITCODE" }
}
function Refresh-Path {
    $env:Path = [Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' + [Environment]::GetEnvironmentVariable('Path', 'User') + ";$env:LOCALAPPDATA\Microsoft\WinGet\Links"
}
function Find-Python {
    $candidates = @("$env:LOCALAPPDATA\Programs\Python\Python312\python.exe", "$env:ProgramFiles\Python312\python.exe")
    $command = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($command) { $candidates += $command.Source }
    if (Get-Command py.exe -ErrorAction SilentlyContinue) {
        $resolved = & py.exe -3 -c 'import sys; print(sys.executable)' 2>$null
        if ($LASTEXITCODE -eq 0) { $candidates += $resolved }
    }
    foreach ($candidate in $candidates | Select-Object -Unique) {
        if (Test-Path $candidate) {
            & $candidate -c 'import sys, tkinter, venv; assert sys.version_info >= (3,10)' 2>$null
            if ($LASTEXITCODE -eq 0) { return $candidate }
        }
    }
    return $null
}

$temporary = Join-Path ([IO.Path]::GetTempPath()) ('BeastRecon-' + [guid]::NewGuid())
try {
    $install = Join-Path $env:LOCALAPPDATA 'BeastRecon'
    New-Item -ItemType Directory -Path $temporary -Force | Out-Null
    Write-Host 'Downloading BeastRecon...'
    $archive = Join-Path $temporary 'app.zip'
    Invoke-WebRequest -UseBasicParsing -Uri 'https://github.com/NoLifeeSSJ/BeastRecon/archive/refs/heads/main.zip' -OutFile $archive
    Expand-Archive -Path $archive -DestinationPath $temporary
    $source = Join-Path $temporary 'BeastRecon-main'
    $files = @('app.py', 'converter.py', 'requirements.txt', 'BeastRecon.ico', 'Install.ps1', 'README.md')
    foreach ($file in $files) {
        if (-not (Test-Path (Join-Path $source $file))) { throw "Download is missing $file" }
    }
    Refresh-Path
    $python = Find-Python
    if (-not $python) {
        if (-not (Get-Command winget -ErrorAction SilentlyContinue)) { throw 'Install App Installer from Microsoft Store, then rerun this installer.' }
        Invoke-Checked { winget install --id Python.Python.3.12 --exact --source winget --accept-package-agreements --accept-source-agreements }
        Refresh-Path
        $python = Find-Python
        if (-not $python) { throw 'Python with Tk could not be found after installation. Repair Python 3.12 with Tcl/Tk enabled.' }
    }
    if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue) -or -not (Get-Command ffprobe -ErrorAction SilentlyContinue)) {
        if (-not (Get-Command winget -ErrorAction SilentlyContinue)) { throw 'Install App Installer from Microsoft Store to install FFmpeg.' }
        Invoke-Checked { winget install --id Gyan.FFmpeg --exact --source winget --accept-package-agreements --accept-source-agreements }
        Refresh-Path
    }
    $ffmpeg = Get-Command ffmpeg -ErrorAction SilentlyContinue
    $ffprobe = Get-Command ffprobe -ErrorAction SilentlyContinue
    if (-not $ffmpeg -or -not $ffprobe) { throw 'FFmpeg installation did not expose ffmpeg and ffprobe. Restart PowerShell and rerun.' }
    Invoke-Checked { & $ffmpeg.Source -version | Out-Null }
    Invoke-Checked { & $ffprobe.Source -version | Out-Null }
    New-Item -ItemType Directory -Path $install -Force | Out-Null
    foreach ($file in $files) { Copy-Item (Join-Path $source $file) (Join-Path $install $file) -Force }
    # Recreate only this app's dedicated environment if it is broken.
    $venv = Join-Path $install '.venv'
    $runtime = Join-Path $venv 'Scripts\python.exe'
    $healthy = $false
    if (Test-Path $runtime) {
        & $runtime -c 'import tkinter, pip' 2>$null
        $healthy = $LASTEXITCODE -eq 0
    }
    if (-not $healthy) {
        if (Test-Path $venv) { Move-Item $venv ($venv + '.backup-' + [guid]::NewGuid()) }
        Invoke-Checked { & $python -m venv $venv }
    }
    Invoke-Checked { & $runtime -m pip install --upgrade -r (Join-Path $install 'requirements.txt') }
    Invoke-Checked { & $runtime -c 'import tkinter, yt_dlp; r=tkinter.Tk(); r.withdraw(); r.destroy()' }
    # Functional conversion check, using absolute paths independent of the caller's folder.
    $sample = Join-Path $temporary 'sample.wav'
    $output = Join-Path $temporary 'sample.mp3'
    Invoke-Checked { & $ffmpeg.Source -hide_banner -loglevel error -f lavfi -i 'sine=frequency=440:duration=0.2' $sample }
    Push-Location $install
    try { Invoke-Checked { & $runtime -c 'import sys; from converter import convert; convert(sys.argv[1], sys.argv[2])' $sample $output } }
    finally { Pop-Location }

    $pythonw = Join-Path $venv 'Scripts\pythonw.exe'
    $shell = New-Object -ComObject WScript.Shell
    $desktop = [Environment]::GetFolderPath('Desktop')
    $programs = [Environment]::GetFolderPath('Programs')
    foreach ($location in @($desktop, $programs)) {
        $shortcut = $shell.CreateShortcut((Join-Path $location 'BeastRecon.lnk'))
        $shortcut.TargetPath = $pythonw
        $shortcut.Arguments = '"' + (Join-Path $install 'app.py') + '"'
        $shortcut.WorkingDirectory = $install
        $shortcut.IconLocation = (Join-Path $install 'BeastRecon.ico') + ',0'
        $shortcut.Description = 'BeastRecon Media Converter'
        $shortcut.Save()
    }
    Write-Host "Installed and tested successfully in $install" -ForegroundColor Green
    Write-Host 'Desktop and Start menu shortcuts created. To pin: right-click the running taskbar icon and choose Pin to taskbar.'
    Start-Process -FilePath $pythonw -ArgumentList ('"' + (Join-Path $install 'app.py') + '"') -WorkingDirectory $install
} catch {
    Write-Host "Installation failed: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
} finally {
    if (Test-Path $temporary) { Remove-Item $temporary -Recurse -Force }
}
