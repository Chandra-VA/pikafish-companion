@echo off
cd /d "%~dp0"
if not exist "%~dp0assistant-env\Scripts\pythonw.exe" (
  echo Python environment is missing. Run scripts\setup.ps1 first.
  exit /b 1
)
start "" "%~dp0assistant-env\Scripts\pythonw.exe" "%~dp0companion\web_app.py"
