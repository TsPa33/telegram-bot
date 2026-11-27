@echo off
setlocal
cd /d "%~dp0"
where pyw >nul 2>nul
if %errorlevel%==0 (
  start "" pyw -3 "%~dp0carpot_local_aleto.pyw"
  exit /b 0
)
where pythonw >nul 2>nul
if %errorlevel%==0 (
  start "" pythonw "%~dp0carpot_local_aleto.pyw"
  exit /b 0
)
echo Python for Windows is not installed or is not on PATH.
echo Install Python from https://www.python.org/downloads/windows/
echo Select Add Python to PATH during setup.
pause
