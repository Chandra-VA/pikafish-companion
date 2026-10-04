param([string]$PythonCommand = 'python')
$ErrorActionPreference = 'Stop'
if ($env:OS -ne 'Windows_NT') { throw 'This assistant supports Windows only.' }
$pikaProjectRoot = Split-Path -Parent $PSScriptRoot
& $PythonCommand -c 'import sys; assert sys.version_info >= (3,12), "Python 3.12 or later is required"'
if ($LASTEXITCODE -ne 0) { throw 'Install Python 3.12 or later first.' }
$pikaEnvironment = Join-Path $pikaProjectRoot 'assistant-env'
if (-not (Test-Path -LiteralPath (Join-Path $pikaEnvironment 'pyvenv.cfg'))) {
    & $PythonCommand -m venv $pikaEnvironment
    if ($LASTEXITCODE -ne 0) { throw 'Failed to create the Python environment.' }
}
$pikaPython = Join-Path $pikaEnvironment 'Scripts\python.exe'
& $pikaPython -m pip install -r (Join-Path $pikaProjectRoot 'requirements.txt')
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
New-Item -ItemType Directory -Force -Path (Join-Path $pikaProjectRoot 'engine') | Out-Null
Write-Host 'Environment ready. Install the official engine and create your local templates: docs/INSTALL.md.'
