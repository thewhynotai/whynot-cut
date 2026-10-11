# Run the WhyNot Cut unit suite with the engine runtime (never system Python: it silently skips HarfBuzz tests).
# Usage: powershell -File tools\test.ps1 [extra unittest args]
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$homeDir = if ($env:WHYNOT_HOME) { $env:WHYNOT_HOME } else { Join-Path $env:USERPROFILE '.whynot-cut' }
$py = @("$homeDir\current\python\python.exe", "$homeDir\venv\Scripts\python.exe") | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $py) { Write-Error "engine runtime not found under $homeDir (run reel setup)"; exit 2 }
$env:PYTHONDONTWRITEBYTECODE = '1'; $env:PYTHONUTF8 = '1'
Push-Location $root
try { & $py -B -m unittest discover -s whynot-cut/tests @args; exit $LASTEXITCODE } finally { Pop-Location }
