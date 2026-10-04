@echo off
cd /d "%~dp0engine"
if not exist "Pikafish-Windows-x86-64-universal.exe" (
  echo Engine is missing. See docs\INSTALL.md.
  exit /b 1
)
"Pikafish-Windows-x86-64-universal.exe"
