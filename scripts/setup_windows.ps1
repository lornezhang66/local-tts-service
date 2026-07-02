$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

if (!(Test-Path ".venv")) {
  python -m venv .venv
}

.\.venv\Scripts\python.exe -m pip install --upgrade pip setuptools wheel
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe .\scripts\download_models.py

if (!(Test-Path "config.json")) {
  Copy-Item "config.example.json" "config.json"
}

Write-Host "Local TTS Service is ready. Run .\scripts\run_windows.ps1"
