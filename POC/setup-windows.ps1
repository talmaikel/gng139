$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot

Write-Host 'Shakdan POC - Windows setup' -ForegroundColor Cyan

$pythonCommand = Get-Command python -ErrorAction SilentlyContinue
if (-not $pythonCommand) {
    throw 'Python was not found. Install Python 3.12 (64-bit), reopen PowerShell, and run this script again.'
}

$pythonVersion = & $pythonCommand.Source -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
if ($LASTEXITCODE -ne 0 -or [version]$pythonVersion -lt [version]'3.11') {
    throw "Python 3.11 or newer is required. Detected: $pythonVersion"
}

if (-not (Test-Path '.venv\Scripts\python.exe')) {
    Write-Host 'Creating the local Python environment...'
    & $pythonCommand.Source -m venv .venv
}

$venvPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
Write-Host 'Installing project packages...'
& $venvPython -m pip install --upgrade pip
& $venvPython -m pip install -r requirements.txt

$vendorFiles = @(
    'static\vendor\leaflet.js',
    'static\vendor\leaflet.css'
)
if ($vendorFiles.Where({ -not (Test-Path $_) }).Count -gt 0) {
    Write-Host 'Restoring the local map library...'
    & $venvPython scripts\vendor.py
}

$edgeLocations = @()
if (${env:ProgramFiles(x86)}) {
    $edgeLocations += Join-Path ${env:ProgramFiles(x86)} 'Microsoft\Edge\Application\msedge.exe'
}
if ($env:ProgramFiles) {
    $edgeLocations += Join-Path $env:ProgramFiles 'Microsoft\Edge\Application\msedge.exe'
}
$edgeLocations = $edgeLocations | Where-Object { Test-Path $_ }
if ($edgeLocations.Count -eq 0) {
    Write-Warning 'Microsoft Edge was not found. The POC will open, but the Playwright municipal-browser fallback will not run.'
} else {
    Write-Host 'Microsoft Edge: found' -ForegroundColor Green
}

$tesseractCommand = Get-Command tesseract -ErrorAction SilentlyContinue
$tesseractPath = if ($tesseractCommand) {
    $tesseractCommand.Source
} elseif (Test-Path 'C:\Program Files\Tesseract-OCR\tesseract.exe') {
    'C:\Program Files\Tesseract-OCR\tesseract.exe'
} else {
    $null
}

if (-not $tesseractPath) {
    Write-Warning 'Tesseract was not found. The website will run, but OCR of scanned documents will be unavailable.'
} else {
    $languages = & $tesseractPath --list-langs 2>$null
    $missingLanguages = @('heb', 'eng') | Where-Object { $_ -notin $languages }
    if ($missingLanguages.Count -gt 0) {
        Write-Warning "Tesseract is installed, but these language packs are missing: $($missingLanguages -join ', ')"
    } else {
        Write-Host 'Tesseract OCR: Hebrew and English found' -ForegroundColor Green
    }
}

Write-Host 'Running the automated checks...'
& $venvPython -m pytest -q

Write-Host ''
Write-Host 'Setup complete.' -ForegroundColor Green
Write-Host 'Run .\start.ps1 and open http://127.0.0.1:8000/'
