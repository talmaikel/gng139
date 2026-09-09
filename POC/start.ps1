$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
if (-not (Test-Path '.venv/Scripts/python.exe')) { throw 'Create the environment first; see README.md.' }
& '.venv/Scripts/python.exe' -m uvicorn app.main:app --host 127.0.0.1 --port 8000
