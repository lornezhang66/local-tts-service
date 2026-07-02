$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
.\.venv\Scripts\python.exe .\server.py --open
