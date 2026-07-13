$ErrorActionPreference = "Stop"

$InstallRoot = Join-Path $env:LOCALAPPDATA "LocalTTS"
$AppDir = Join-Path $InstallRoot "local-tts-service"

if (-not (Test-Path (Join-Path $AppDir "ttsctl.ps1"))) {
  $TempDir = Join-Path ([System.IO.Path]::GetTempPath()) ("local-tts-" + [guid]::NewGuid())
  $Archive = Join-Path $TempDir "local-tts.zip"
  New-Item -ItemType Directory -Force -Path $TempDir | Out-Null
  try {
    Invoke-WebRequest "https://github.com/lornezhang66/local-tts-service/archive/refs/heads/main.zip" -OutFile $Archive
    Expand-Archive $Archive -DestinationPath $TempDir
    New-Item -ItemType Directory -Force -Path $InstallRoot | Out-Null
    Move-Item (Join-Path $TempDir "local-tts-service-main") $AppDir
  } finally {
    Remove-Item $TempDir -Recurse -Force -ErrorAction SilentlyContinue
  }
}

& (Join-Path $AppDir "ttsctl.ps1") install
