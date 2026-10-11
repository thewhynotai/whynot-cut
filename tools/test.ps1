# Run the WhyNot Cut unit suite with the engine runtime (never system Python: it silently skips HarfBuzz tests).
# Usage: powershell -File tools\test.ps1 [extra unittest args]     (--which: print the interpreter, then exit)
# Interpreter, the wrappers' order (3.0 T2.1): the runtime named by the one-line text file <home>\current
# (runtimes\<id>\, run with -s: no user site), else the 2.x venv\.
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$homeDir = if ($env:WHYNOT_HOME) { $env:WHYNOT_HOME } else { Join-Path $env:USERPROFILE '.whynot-cut' }
$py = $null; $flags = @()
$cur = Join-Path $homeDir 'current'
if (Test-Path -LiteralPath $cur -PathType Leaf) {
    $id = ([IO.File]::ReadAllText($cur)).Trim().TrimStart([char]0xFEFF)
    if ($id -and $id -notmatch '[\\/:]|\.\.') {
        $c = Join-Path $homeDir "runtimes\$id\Scripts\python.exe"
        if (Test-Path -LiteralPath $c) { $py = $c; $flags = @('-s') }
    }
}
if (-not $py) {
    $c = Join-Path $homeDir 'venv\Scripts\python.exe'
    if (Test-Path -LiteralPath $c) { $py = $c }
}
if (-not $py) { Write-Error "engine runtime not found under $homeDir (run reel setup)"; exit 2 }
if ($args.Count -gt 0 -and $args[0] -eq '--which') { Write-Output ((@($py) + $flags) -join ' '); exit 0 }
$env:PYTHONDONTWRITEBYTECODE = '1'; $env:PYTHONUTF8 = '1'
Push-Location $root
try { & $py @flags -B -W error::ResourceWarning -m unittest discover -s whynot-cut/tests @args; exit $LASTEXITCODE } finally { Pop-Location }
