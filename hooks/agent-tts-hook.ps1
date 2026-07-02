$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python = if ($env:AGENT_TTS_PYTHON) { $env:AGENT_TTS_PYTHON } else { "python" }
& $Python (Join-Path $Root "agent_tts_hook.py") @args
