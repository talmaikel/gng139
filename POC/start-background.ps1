$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
if (-not (Test-Path '.venv/Scripts/python.exe')) { throw 'Create the environment first; see README.md.' }
if (Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue) { throw 'Port 8000 is already in use. Keep the existing server or choose another port.' }
New-Item -ItemType Directory -Force -Path 'data' | Out-Null
$shakedServer = Start-Process -FilePath (Join-Path $PSScriptRoot '.venv/Scripts/python.exe') -ArgumentList '-m','uvicorn','app.main:app','--host','127.0.0.1','--port','8000' -WorkingDirectory $PSScriptRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $PSScriptRoot 'data/server.log') -RedirectStandardError (Join-Path $PSScriptRoot 'data/server-error.log') -PassThru
Write-Output "Shaked server PID: $($shakedServer.Id). Open http://127.0.0.1:8000"
