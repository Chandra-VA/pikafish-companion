$ErrorActionPreference = 'Stop'
$pikaProjectRoot = Split-Path -Parent $PSScriptRoot
$pikaCompiler = Join-Path $env:WINDIR 'Microsoft.NET\Framework64\v4.0.30319\csc.exe'
if (-not (Test-Path -LiteralPath $pikaCompiler)) { throw 'The .NET Framework C# compiler is unavailable. Use start_companion.cmd.' }
& $pikaCompiler /nologo /target:winexe /r:System.Windows.Forms.dll "/out:$pikaProjectRoot\PikafishAssistant.exe" (Join-Path $pikaProjectRoot 'companion\Launcher.cs')
if ($LASTEXITCODE -ne 0) { throw 'Launcher compilation failed.' }
Write-Host 'Built PikafishAssistant.exe. It locates its files relative to its own directory.'
