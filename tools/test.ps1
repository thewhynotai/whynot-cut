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
    if ($id -cmatch '^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$' -and $id -notmatch '\.\.') {   # the id rule of lib/plat.py
        $c = Join-Path $homeDir "runtimes\$id\Scripts\python.exe"
        $cfg = Join-Path $homeDir "runtimes\$id\pyvenv.cfg"       # can it start: plat.runtime_usable()
        $base = if (Test-Path -LiteralPath $cfg) { Get-Content -LiteralPath $cfg | Where-Object { $_ -match '^\s*home\s*=' } |
            Select-Object -First 1 | ForEach-Object { ($_ -split '=', 2)[1].Trim() } }
        if ((Test-Path -LiteralPath $c) -and $base -and (Test-Path -LiteralPath (Join-Path $base 'python.exe'))) {
            $py = $c; $flags = @('-s')
        } else { Write-Warning "runtime $id cannot start (run reel setup); trying the 2.x venv" }
    }
}
if (-not $py) {
    $c = Join-Path $homeDir 'venv\Scripts\python.exe'
    if (Test-Path -LiteralPath $c) { $py = $c }
}
if (-not $py) { Write-Error "engine runtime not found under $homeDir (run reel setup)"; exit 2 }
if ($args.Count -gt 0 -and $args[0] -eq '--which') { Write-Output ((@($py) + $flags) -join ' '); exit 0 }
$env:PYTHONDONTWRITEBYTECODE = '1'; $env:PYTHONUTF8 = '1'
# Test temp files away from the system drive when this machine has a data drive (Addendum F2-T2): WHYNOT_TEST_TMP wins,
# else D:\ClaudeData\Temp\wnc-tests when D:\ClaudeData exists; otherwise the normal TEMP. Only this process.
$tt = $env:WHYNOT_TEST_TMP
if (-not $tt -and (Test-Path -LiteralPath 'D:\ClaudeData' -PathType Container)) { $tt = 'D:\ClaudeData\Temp\wnc-tests' }
if ($tt) { New-Item -ItemType Directory -Force -Path $tt | Out-Null; $env:TEMP = $tt; $env:TMP = $tt }
Push-Location $root
try { & $py @flags -B -W error::ResourceWarning -m unittest discover -s whynot-cut/tests @args; exit $LASTEXITCODE } finally { Pop-Location }
