@echo off
setlocal
cd /d "%~dp0"
where ffmpeg >nul 2>nul
if errorlevel 1 (
  echo Install FFmpeg first: winget install Gyan.FFmpeg
  echo Then reopen this launcher.
  pause
  exit /b 1
)
if not exist .venv\Scripts\python.exe (
  py -3 -m venv .venv
  if errorlevel 1 goto failed
)
.venv\Scripts\python.exe -m pip install --upgrade -r requirements.txt
if errorlevel 1 goto failed
.venv\Scripts\python.exe app.py
if errorlevel 1 goto failed
exit /b 0
:failed
echo Startup failed. Check the error above. Python 3.10+ with Tk is required.
pause
exit /b 1
