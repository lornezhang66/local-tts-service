$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python = if (Test-Path (Join-Path $Root ".venv\Scripts\python.exe")) {
  Join-Path $Root ".venv\Scripts\python.exe"
} else {
  "python"
}
& $Python (Join-Path $Root "ttsctl.py") @args
exit $LASTEXITCODE
