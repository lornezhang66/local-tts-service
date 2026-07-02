$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$Python = if (Test-Path ".\.venv\Scripts\python.exe") {
  ".\.venv\Scripts\python.exe"
} else {
  "python"
}

& $Python .\scripts\install_agent_hooks.py --all
