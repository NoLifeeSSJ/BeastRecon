$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot

function Invoke-Checked {
    param([scriptblock]$Command)
    & $Command
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed with exit code $LASTEXITCODE"
    }
}

if (-not (Test-Path '.\app.py') -or -not (Test-Path '.\requirements.txt')) {
    throw 'Run this installer from the BeastRecon app folder.'
}
if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
    throw 'Install App Installer from the Microsoft Store to enable winget.'
}

if (-not (Get-Command py -ErrorAction SilentlyContinue)) {
    Invoke-Checked {
        winget install --id Python.Python.3.12 --exact --source winget --accept-package-agreements --accept-source-agreements
    }
}
if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue) -or -not (Get-Command ffprobe -ErrorAction SilentlyContinue)) {
    Invoke-Checked {
        winget install --id Gyan.FFmpeg --exact --source winget --accept-package-agreements --accept-source-agreements
    }
}
$env:Path = [Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' + [Environment]::GetEnvironmentVariable('Path', 'User')
if (-not (Get-Command py -ErrorAction SilentlyContinue)) {
    throw 'Reopen PowerShell and run Install.ps1 again to activate Python.'
}
if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue) -or -not (Get-Command ffprobe -ErrorAction SilentlyContinue)) {
    throw 'Reopen PowerShell and run Install.ps1 again to activate FFmpeg.'
}
Invoke-Checked { py -3 -c "import sys; assert sys.version_info >= (3, 10), 'Python 3.10+ required'; import tkinter" }
if (-not (Test-Path '.\.venv\Scripts\python.exe')) {
    Invoke-Checked { py -3 -m venv .venv }
}
Invoke-Checked { & .\.venv\Scripts\python.exe -m pip install -r requirements.txt }
Write-Host 'Installation complete. Opening BeastRecon...' -ForegroundColor Green
Invoke-Checked { & .\.venv\Scripts\python.exe app.py }
