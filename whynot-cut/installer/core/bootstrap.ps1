# WhyNot Cut installer bootstrap for Windows (Windows PowerShell 5.1 or PowerShell 7). Internal: installer\install.ps1
# loads this file as a script block and runs it; editors never run it directly.
#
# It does only what a bare PC needs before Python exists, then hands over to the installer core:
#   == uv ==      the pinned uv (components.json uv.assets.win-x64): downloaded into ~\.whynot-cut\downloads,
#                 sha256 verified (a mismatch deletes the file and stops), unpacked to ~\.whynot-cut\bin\uv.exe.
#                 Already there at the pinned version: no download.
#   == python ==  uv python install <runtime.python> --no-bin --no-registry into ~\.whynot-cut\python (no shim in
#                 ~\.local\bin, no HKCU key), then uv python find -> the python-build-standalone interpreter.
#   then          <python> -I -B -X utf8 installer\core\wnc_install.py install|uninstall --plugin-root ... --uv ...
#                 --python ... --log ... (the 14 steps). -X utf8: -I ignores PYTHONUTF8, and Arabic must survive
#                 a cp1252 console.
# -Uninstall runs on the engine's own Python when it is there (uv python find with the uv in bin\, at any version, else
# python\cpython-<ver>*\python.exe): nothing is downloaded; only without one are uv and Python fetched as above.
# -Uninstall -RemoveEngine: the core cannot delete the Python it runs on (Windows locks python.exe and its DLLs), so it
# lists python\ and bin\ (and the engine home itself when nothing else is left) in <engine>\.delete-after-exit. Once
# the core has exited, this script deletes what that list names, but ONLY <engine>\python and <engine>\bin (every line
# normalised first; anything else is refused and reported), never through a link or junction (a link is removed as a
# link), and the engine home itself only when it is then empty; then the list file. The DEFAULT ~\.whynot-cut may be a
# junction / symlink to a folder (Addendum F): python\ and bin\ are deleted through it, never the link or its target. The log went with logs\, so the
# summary is on the console only. The newest engine Python is chosen by version number (3.12.15 before 3.12.9).
# Log: ~\.whynot-cut\logs\install-YYYYmmdd-HHMMSS.log (uninstall-... for -Uninstall), shared with the core (--log).
# Exit code (in $LASTEXITCODE): the core's; 2 = cannot start (not Windows x64, unreadable components.json, missing
# core); 3 = a bootstrap step failed (download, sha256, uv, python), with a one-line message and the log path.
# -DryRun: writes nothing (no log, no folder). Runs the core's dry run only when uv and Python are already there (or
# WNC_TEST_UV is set); otherwise it names the steps that would follow.
# Engine home: resolved exactly like the engine (Resolve-WncEngineHome: WHYNOT_HOME and the other engine-home
# variables, else the plugin option engine_home from ~\.whynot-cut\plugin-options.json, else from settings.json
# pluginConfigs, else ~\.whynot-cut) BEFORE anything is downloaded. That folder is the default of the location question
# (owner decision 2026-10-12): -EngineHome <folder> answers it, -Yes takes the default, and without a terminal the
# default is used. The answer is placed and checked (Get-WncEnginePlace, the core's base.choose_engine_home: a full
# path, not a drive root / mounted volume / link, not inside the plugin folder; unless WhyNot Cut is already there
# also not holding the plugin, not the clients folder or holding / inside it, not inside or holding a folder marked
# .whynot-client; the user folder, Desktop, Documents, Downloads and any folder holding the editor's own files get a
# WhyNotCut subfolder (said in English and Arabic), so uninstall never empties a folder of the editor's files; in a
# sandbox inside the sandbox; 6 GB free on its drive, 9 GB with the Whisper model, unless WhyNot Cut is already
# there; it can be created and written); a refused folder is asked again (with -Yes: exit 2, nothing downloaded). A
# path with non-ASCII letters gets a warning (English + Arabic) suggesting C:\WhyNotCut and is asked again; -Yes keeps
# it; a folder WhyNot Cut is already installed in is kept without asking again. Choosing a folder other than an
# existing install's says (English + Arabic) that the old one is left behind, and where. uv, Python, the log and every later step land in that one folder: it is passed to the core as --engine-home
# (+ --engine-home-chosen when the editor chose it: the core then uses it as it is; otherwise the core stops with 2 if
# its own resolution, wnc_installer.base.resolve_engine_home, disagrees). The core remembers a chosen folder in
# settings.json pluginConfigs and the pointer file (questions step). -Uninstall asks nothing: the resolved folder, or
# -EngineHome. -Model <large-v3|large-v3-turbo|medium|small> goes to the core (its model question).
# Sandbox (-Home <dir>): HOME, USERPROFILE, APPDATA, LOCALAPPDATA, CLAUDE_CONFIG_DIR and WHYNOT_HOME point into <dir>
# before anything is downloaded (as wnc_installer.base.Paths.child_env does), and --home is passed on; the engine home
# is resolved from the sandbox's own pointer / settings.json only (never this machine's variables). Only then are the
# test hooks honoured: WNC_TEST_UV (a uv stand-in used for `python install/find` after the real archive was still
# downloaded and verified), WNC_TEST_ANSWERS (a file: one answer per line for the location question) and
# WNC_TEST_FREE_GB (the free space the check sees). Every environment variable it sets is restored when it ends (the
# script may run inside the editor's own PowerShell session through `irm | iex`), so is the console encoding.
# No questions by default (Addendum D, D-T1, task 9): an install prints "Installing everything WhyNot Cut needs (about N
# GB)" (English + Arabic; N from components.json `bytes` where present, the core's system.install_size_gb rule) and,
# with a person at the console, a 10-second line "Press C to customise (10)... / <Arabic>" that counts down in place
# ([Console]::KeyAvailable). C opens the Customise path; any other key or the end of the countdown installs with the
# strongest defaults, exactly like -Yes (the core gets --yes: the same state.json, answers.mode "default").
# -Customise (or C) asks the location question here and passes --customise, so the core asks the model, the language
# and the clients folder, every answer preselected. -Yes: no countdown, no question. No keyboard (input redirected,
# -NonInteractive, Door 2, Setup.exe, CI): like -Yes, never waiting for a key. -Yes with -Customise: exit 2.
# A RESOLVED engine home other than ~\.whynot-cut (a variable, the pointer or settings.json named it) that is itself a
# link / reparse point (junction, symlink, a volume mounted into a folder), a drive root, the user folder itself,
# Desktop / Documents / Downloads themselves (also where Windows' User Shell Folders put them: OneDrive Known Folder
# Move), or holds client data (the saved clients folder, or .whynot-client up to 3 levels below), or is too big to
# check for that (more than 5000 entries within 3 levels), or a network share / device path (\\server\share,
# \\localhost\C$, \\.\...; \\?\C:\x counts as C:\x) - compared as written and with links resolved - is refused with
# exit 2 before the countdown and any download (fix round 1), also when -EngineHome names that same folder (fix round
# 2), with the self-fix
# "run the installer again with -EngineHome <folder> / --engine-home <folder>" (English + Arabic); the core applies the
# same rule (base.resolved_home_problem). Sandbox-only test hooks for this: WNC_TEST_KEYS ("C", another key, or
# "none" = nobody presses), WNC_TEST_COUNTDOWN_S (the seconds the countdown waits with the hook; 0 = none), and the
# core reads the WNC_TEST_ANSWERS lines after the ones used here (WNC_TEST_ANSWERS_AT).
# ASCII only: Windows PowerShell 5.1 reads a file without a BOM as ANSI.
[Diagnostics.CodeAnalysis.SuppressMessageAttribute('PSReviewUnusedParameter', '',
    Justification = 'The parameters are read inside the & { } block below, which the analyzer does not follow.')]
[Diagnostics.CodeAnalysis.SuppressMessageAttribute('PSAvoidUsingWriteHost', '',
    Justification = 'Console lines for the editor; pipeline output would be captured and hide the core output.')]
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$PluginRoot,
    [Alias('Home')][string]$SandboxHome,
    [switch]$DryRun,
    [switch]$Yes,
    [string]$ClientsFolder,
    [string]$Language,
    [string]$Channel,
    [string]$Components,
    [string[]]$Skip,
    [switch]$Uninstall,
    [switch]$RemoveEngine,
    [switch]$RemoveModels,
    [string]$EngineHome,
    [string]$Model,
    [Alias('Customize')][switch]$Customise
)

& {
    Set-StrictMode -Version 2.0
    $ErrorActionPreference = 'Stop'
    $ProgressPreference = 'SilentlyContinue'

    # the core's STEP_ORDER (wnc_installer/cli.py); tests/test_installer.py keeps the two in step
    $WncStepNames = @('preflight', 'questions', 'runtime', 'ffmpeg', 'gitbash', 'gpu', 'claude', 'adobe', 'fonts',
        'settings', 'model', 'state', 'doctor', 'launch')
    # and its uninstall steps (wnc_installer/uninstall.py STEP_NAMES)
    $WncUninstallStepNames = @('plugin', 'adobe', 'fonts', 'marketplace', 'engine')
    $S = @{ Log = $null; Step = 'start'; Code = 0; Utf8 = (New-Object System.Text.UTF8Encoding $false);
        Answers = $null; AnswerAt = 0; FreeGb = $null; Mode = 'yes'; TestKeys = $null; CountdownS = 10 }
    $WncModels = @('large-v3', 'large-v3-turbo', 'medium', 'small')  # wnc_installer/system.py MODELS
    $WncNeedGb = 6  # free space for the engine; + $WncModelGb with the Whisper model (system.py RED_GB / AMBER_GB)
    $WncModelGb = 3
    # the install size estimate (system.py RUNTIME_GB, FFMPEG_GB, FONTS_GB, GIT_GB and MODEL_SIZES)
    $WncSizes = @{ runtime = 0.5; ffmpeg = 0.1; fonts = 0.01; git = 0.4; cuda = 1.0 }  # Git unpacked; CUDA (NVIDIA)
    $WncModelSizes = @{ 'large-v3' = 2.9; 'large-v3-turbo' = 1.6; 'medium' = 1.5; 'small' = 0.5 }
    # the Arabic lines, UTF-8 in base64 (this file stays ASCII)
    $WncAr = @{
        Intro = ('2KPZitmGINmK2K3Zgdi4IFdoeU5vdCBDdXQg2YXZhNmB2KfYqiDYp9mE2KrYtNi62YrZhCAo2KjYp9mK2KvZiNmGINmIIGZmbXBlZyDZiNmG' +
            '2YXZiNiw2KwgV2hpc3BlcinYnyDYqtit2KrYp9isINit2YjYp9mE2YogNiDYrNmK2KzYp9io2KfZitiq2Iwg2Yg5INmF2Lkg2KfZhNmG2YXZiNiw' +
            '2KwuINin2LbYuti3IEVudGVyINmE2KfYrtiq2YrYp9ixINin2YTZhdis2YTYryDYqNmK2YYg2KfZhNmC2YjYs9mK2YYu')
        Existing = ('V2h5Tm90IEN1dCDZhdir2KjZkdiqINio2KfZhNmB2LnZhCDZgdmKINmH2LDYpyDYp9mE2YXYrNmE2K/YmyDYp9i22LrYtyBFbnRlciDZhNil' +
            '2KjZgtin2KbZhy4=')
        NonAscii = ('2KrZhtio2YrZhzog2YHZiiDZh9iw2Kcg2KfZhNmF2LPYp9ixINit2LHZiNmBINi62YrYsSDYpdmG2KzZhNmK2LLZitip2Iwg2YjZgtivINiq' +
            '2YHYtNmEINio2LnYtiDYp9mE2KPYr9mI2KfYqiDZhdi52YfYmyDYp9mE2KPZgdi22YQg2YXYrNmE2K8g2KjYs9mK2Lcg2YXYq9mEIEM6XFdoeU5v' +
            'dEN1dA==')
        Folder = '2KfZhNmF2KzZhNiv'
        Cannot = ('2YTYpyDZitmF2YPZhiDYp9iz2KrYrtiv2KfZhSDZh9iw2Kcg2KfZhNmF2KzZhNiv2Jsg2KfYrtiq2LEg2YXYrNmE2K/Zi9inINii2K7YsS4=')
        Subfolder = ('2YfYsNinINin2YTZhdis2YTYryDZgdmK2Ycg2YXZhNmB2KfYqiDYo9iu2LHZidiMINmE2LDZhNmDINiz2YrZj9ir2KjZjtmR2KogV2h5Tm90' +
            'IEN1dCDZgdmKINmF2KzZhNivINiu2KfYtSDYqNmHINiv2KfYrtmE2YcgKFdoeU5vdEN1dCnYjCDZiNmE2YYg2YrZhNmF2LMg2KfZhNil2YTYutin' +
            '2KEg2KjYp9mC2Yog2KfZhNmF2YTZgdin2Kou')
        Size = ('2KzYp9ix2Y0g2KrYq9io2YrYqiDZg9mEINmF2Kcg2YrYrdiq2KfYrNmHIFdoeU5vdCBDdXQgKNit2YjYp9mE2YogezB9INis2YrY' +
            'rNin2KjYp9mK2Kop')
        Countdown = '2KfYtti62LcgQyDZhNmE2KrYrti12YrYtQ=='
        Customising = ('2KfZhNiq2K7YtdmK2LU6INij2KzYqCDYudmGINin2YTYo9iz2KbZhNipINin2YTYqtin2YTZitip2Jsg2KfYtti62LcgRW50ZXIg' +
            '2YTYpdio2YLYp9ihINin2YTYpdis2KfYqNipINin2YTZhdmC2KrYsdit2Kku')
        Guard = ('2YTZhiDZitiz2KrYrtiv2YUgV2h5Tm90IEN1dCDZh9iw2Kcg2KfZhNmF2KzZhNivINmE2YXZhNmB2KfYqiDYp9mE2KrYtNi62YrZhC4g' +
            '2YTYpdi12YTYp9itINiw2YTZgyDYtNi62ZHZhCDYp9mE2YXYq9io2ZHYqiDZhdix2Kkg2KPYrtix2Ykg2YXYuSAtRW5naW5lSG9tZSA8Zm9s' +
            'ZGVyPiAo2LnZhNmJIG1hY09TOiAtLWVuZ2luZS1ob21lIDxmb2xkZXI+KSDZiNin2K7YqtixINmF2KzZhNiv2YvYpyDYrtin2LXZi9inINio2Ycu')
        LeftBehind = ('2KrZhtio2YrZhzog2KfZhNiq2KvYqNmK2Kog2KfZhNmC2K/ZitmFINiz2YrYqNmC2Ykg2YHZiiDZhdmD2KfZhtmHINmI2YTZhiDZitmP2LPY' +
            'qtiu2K/ZhSDYqNi52K8g2KfZhNii2YbYmyDYp9it2LDZgdmHINio2YbZgdiz2YMg2KXZhiDZhNmFINiq2LnYryDYqtit2KrYp9is2Yc6')
    }
    $EnvNames = @('HOME', 'USERPROFILE', 'APPDATA', 'LOCALAPPDATA', 'CLAUDE_CONFIG_DIR', 'WHYNOT_HOME',
        'UV_PYTHON_INSTALL_DIR', 'UV_CACHE_DIR', 'UV_NO_CONFIG', 'UV_PYTHON_PREFERENCE', 'UV_NO_MODIFY_PATH',
        'WNC_TEST_ANSWERS_AT')

    function Write-WncLog([string]$Level, [string]$Text) {
        if (-not $S.Log) { return }
        $line = (Get-Date).ToString("yyyy-MM-dd'T'HH:mm:ssK") + " $Level $Text`n"
        try { [IO.File]::AppendAllText($S.Log, $line, $S.Utf8) } catch { Write-Verbose "log write failed: $_" }
    }

    function Write-WncLine([string]$Text) {
        Write-Host $Text
        Write-WncLog 'INFO' $Text
    }

    function Write-WncStep([string]$Name) {
        $S.Step = $Name
        Write-Host "== $Name =="
        Write-WncLog 'STEP' "== $Name =="
    }

    function Test-WncPlaceholder($Value) {
        return ($null -eq $Value) -or (($Value -is [string]) -and $Value.StartsWith('<release'))
    }

    function Get-WncFullPath([string]$Path) {
        # absolute, without a trailing \ or / (a bare drive root keeps its \): Windows PowerShell hands a native
        # program 'C:\x y\' as "C:\x y\", whose \" the program reads as a quote and swallows the next arguments
        $full = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($Path)
        $trimmed = $full.TrimEnd([char[]]@([char]92, [char]47))
        if ($trimmed -match '^[A-Za-z]:$') { return $trimmed + [char]92 }
        if (-not $trimmed) { return $full }
        return $trimmed
    }

    function ConvertTo-WncNativeArgument([string[]]$ArgList) {
        # Windows PowerShell 5.1 and PowerShell 7.0-7.2 (legacy native quoting) put an argument with whitespace in
        # quotes without doubling its trailing backslashes; double them here so the program gets the argument intact
        $v = $PSVersionTable.PSVersion
        $legacy = ($v.Major -lt 7) -or (($v.Major -eq 7) -and ($v.Minor -lt 3))
        if (-not $legacy) { return ,$ArgList }
        $out = @(foreach ($arg in $ArgList) {
                if (($arg -match '\s') -and ($arg -match '(\\+)$')) { $arg + $Matches[1] } else { $arg }
            })
        return ,$out
    }

    function Invoke-WncNative([string]$Exe, [string[]]$ArgList) {
        # stdout lines, stderr lines and the exit code; stderr never turns into a terminating error (PS 5.1)
        $old = $ErrorActionPreference
        $ErrorActionPreference = 'Continue'
        try {
            $safe = ConvertTo-WncNativeArgument $ArgList
            $all = @(& $Exe @safe 2>&1)
            $rc = $LASTEXITCODE
        } finally {
            $ErrorActionPreference = $old
        }
        $out = @($all | Where-Object { $_ -isnot [System.Management.Automation.ErrorRecord] } | ForEach-Object { "$_" })
        $err = @($all | Where-Object { $_ -is [System.Management.Automation.ErrorRecord] } | ForEach-Object { "$_" })
        foreach ($l in ($out + $err)) { Write-WncLog 'INFO' "  $l" }
        return @{ Code = $rc; Out = $out; Err = $err }
    }

    function Get-WncTail($Result) {
        $lines = @($Result.Err + $Result.Out | Where-Object { $_.Trim() })
        if ($lines.Count -eq 0) { return '(no output)' }
        return $lines[-1].Trim()
    }

    function Test-WncUv([string]$Exe, [string]$Version) {
        if (-not (Test-Path -LiteralPath $Exe -PathType Leaf)) { return $false }
        try {
            $r = Invoke-WncNative $Exe @('--version')
        } catch {
            return $false
        }
        return ($r.Code -eq 0) -and ((($r.Out -join ' ').Trim()) -match ('^uv ' + [regex]::Escape($Version) + '(\s|$)'))
    }

    function Get-WncFileSha([string]$Path) {
        return (Get-FileHash -Algorithm SHA256 -LiteralPath $Path).Hash.ToLowerInvariant()
    }

    function Get-WncDownload([string]$Url, [string]$Sha, [string]$Dir) {
        $name = [Uri]::UnescapeDataString(([Uri]$Url).AbsolutePath.Split('/')[-1])
        if (-not $name) { throw "cannot name the download for $Url" }
        $dest = Join-Path $Dir $name
        $part = "$dest.part"
        if (Test-Path -LiteralPath $dest -PathType Leaf) {
            if ((Get-WncFileSha $dest) -eq $Sha) {
                Write-WncLine "cached $name (sha256 ok)"
                return $dest
            }
            Write-WncLine "cached $name has the wrong sha256; fetching it again"
            Remove-Item -LiteralPath $dest -Force
        }
        $null = New-Item -ItemType Directory -Force -Path $Dir
        Write-WncLine "download $Url"
        $last = $null
        for ($i = 1; $i -le 3; $i++) {
            if (Test-Path -LiteralPath $part) { Remove-Item -LiteralPath $part -Force }
            try {
                Invoke-WebRequest -UseBasicParsing -Uri $Url -OutFile $part
                $last = $null
                break
            } catch {
                $last = $_.Exception.Message
                $status = 0
                try { $status = [int]$_.Exception.Response.StatusCode } catch { $status = 0 }
                if ($status -ge 400 -and $status -lt 500) { break }
                if ($i -lt 3) {
                    Write-WncLine "download interrupted ($last); retrying ($($i + 1)/3)"
                    Start-Sleep -Seconds $i
                }
            }
        }
        if ($null -ne $last) {
            if (Test-Path -LiteralPath $part) { Remove-Item -LiteralPath $part -Force }
            throw "could not download $name from $Url ($last)"
        }
        $got = Get-WncFileSha $part
        if ($got -ne $Sha) {
            Remove-Item -LiteralPath $part -Force
            throw "sha256 mismatch for $name (expected $Sha, got $got); the file was deleted"
        }
        Move-Item -LiteralPath $part -Destination $dest -Force
        Write-WncLine "verified $name (sha256 ok)"
        return $dest
    }

    function Install-WncUv([string]$Archive, [string]$Kind, [string]$Version, [string]$Engine, [string]$UvExe) {
        if ($Kind -ne 'zip') { throw "uv archive type '$Kind' cannot be unpacked on Windows" }
        $stage = Join-Path $Engine "downloads\uv-$Version.staging"
        if (Test-Path -LiteralPath $stage) { Remove-Item -LiteralPath $stage -Recurse -Force }
        Expand-Archive -LiteralPath $Archive -DestinationPath $stage -Force
        $found = @(Get-ChildItem -LiteralPath $stage -Recurse -File -Filter 'uv.exe')
        if ($found.Count -eq 0) { throw "$(Split-Path $Archive -Leaf) holds no uv.exe" }
        $null = New-Item -ItemType Directory -Force -Path (Split-Path $UvExe -Parent)
        Copy-Item -LiteralPath $found[0].FullName -Destination "$UvExe.new" -Force
        Move-Item -LiteralPath "$UvExe.new" -Destination $UvExe -Force
        Remove-Item -LiteralPath $stage -Recurse -Force
        Write-WncLine "uv $Version unpacked to $UvExe"
    }

    function Find-WncPython([string]$Uv, [string]$Version) {
        $r = Invoke-WncNative $Uv @('python', 'find', $Version, '--python-preference', 'only-managed')
        if ($r.Code -ne 0) { return $null }
        $lines = @($r.Out | Where-Object { $_.Trim() })
        if ($lines.Count -eq 0) { return $null }
        $py = $lines[-1].Trim()
        if (Test-Path -LiteralPath $py -PathType Leaf) { return $py }
        return $null
    }

    function Get-WncPythonDirNewestFirst([object[]]$Dirs) {
        # cpython-<x.y.z>-... folders, newest version first, compared as numbers (3.12.15 before 3.12.9)
        $keyed = foreach ($d in @($Dirs | Where-Object { $_ })) {
            $v = New-Object Version 0, 0, 0
            if ($d.Name -match '^cpython-(\d+)\.(\d+)\.(\d+)') {
                $v = New-Object Version ([int]$Matches[1]), ([int]$Matches[2]), ([int]$Matches[3])
            }
            New-Object PSObject -Property @{ Dir = $d; Ver = $v }
        }
        return ,@($keyed | Sort-Object -Property Ver -Descending | ForEach-Object { $_.Dir })
    }

    function Find-WncEnginePython([string]$Uv, [string]$Version, [string]$Engine) {
        # uninstall: the python-build-standalone already in the engine home, or $null (nothing is downloaded here)
        if ($Uv -and (Test-Path -LiteralPath $Uv -PathType Leaf)) {
            $py = $null
            try { $py = Find-WncPython $Uv $Version } catch { $py = $null }
            if ($py) { return $py }
        }
        $dir = Join-Path $Engine 'python'
        if (-not (Test-Path -LiteralPath $dir -PathType Container)) { return $null }
        $dirs = Get-WncPythonDirNewestFirst -Dirs @(Get-ChildItem -LiteralPath $dir -Directory -Filter "cpython-$Version*" `
                -ErrorAction SilentlyContinue)
        foreach ($d in $dirs) {
            $exe = Join-Path $d.FullName 'python.exe'
            if (-not (Test-Path -LiteralPath $exe -PathType Leaf)) { continue }
            try {
                $r = Invoke-WncNative $exe @('-I', '-B', '-c', 'pass')
                if ($r.Code -eq 0) { return $exe }
            } catch {
                Write-WncLog 'INFO' "  $exe does not start: $($_.Exception.Message)"
            }
        }
        return $null
    }

    function Test-WncReparse([string]$Path) {
        # a junction, symlink or any other reparse point
        try {
            $attr = [IO.File]::GetAttributes($Path)
        } catch {
            return $false
        }
        return (($attr -band [IO.FileAttributes]::ReparsePoint) -ne 0)
    }

    function Invoke-WncDeleteTree([string]$Path) {
        # never Remove-Item -Recurse (Windows PowerShell 5.1 follows junctions): a link is removed as a link, its
        # target never entered; read-only files are cleared first
        if (Test-WncReparse $Path) {
            if ([IO.Directory]::Exists($Path)) { [IO.Directory]::Delete($Path, $false) } else { [IO.File]::Delete($Path) }
            return
        }
        if ([IO.Directory]::Exists($Path)) {
            foreach ($child in [IO.Directory]::GetFileSystemEntries($Path)) { Invoke-WncDeleteTree $child }
            [IO.Directory]::Delete($Path, $false)
        } elseif ([IO.File]::Exists($Path)) {
            [IO.File]::SetAttributes($Path, [IO.FileAttributes]::Normal)
            [IO.File]::Delete($Path)
        }
    }

    function Invoke-WncDeferredDelete([string]$Engine, [string]$UserHome) {
        # after `uninstall --remove-engine`: the paths the core listed in <engine>\.delete-after-exit (see the header)
        $list = Join-Path $Engine '.delete-after-exit'
        if (-not [IO.File]::Exists($list)) { return }
        $root = [IO.Path]::GetFullPath($Engine).TrimEnd([char]92)
        # Addendum F: the DEFAULT ~\.whynot-cut may be a junction / symlink to a folder (D:\ClaudeData\...): its
        # python\ and bin\ are deleted through it, never the link itself nor its target folder
        $linked = (Test-WncReparse $root) -and [IO.Directory]::Exists($root) -and $UserHome -and
            ($root -ieq [IO.Path]::GetFullPath((Join-Path $UserHome '.whynot-cut')).TrimEnd([char]92))
        if ((Test-WncReparse $root) -and (-not $linked)) {
            Write-Host "WARNING: $root is a link; the paths in $list were left alone"
            return
        }
        # the ONLY paths it may name: <engine>\python, <engine>\bin and <engine> itself (that one only once empty);
        # every line is normalised first (GetFullPath: \ and / alike, repeated separators, . and ..; case ignored)
        $allowed = @((Join-Path $root 'python'), (Join-Path $root 'bin'))
        $homeToo = $false
        $failed = $false
        $lines = @()
        try {
            $lines = [IO.File]::ReadAllLines($list, $S.Utf8)
        } catch {
            Write-Host "WARNING: cannot read $list ($($_.Exception.Message)); nothing was deleted"
        }
        foreach ($line in $lines) {
            try {
                $p = $line.Trim()
                if (-not $p) { continue }
                $full = [IO.Path]::GetFullPath($p).TrimEnd([char[]]@([char]92, [char]47))
                if ($full -ieq $root) { $homeToo = $true; continue }
                $target = $null
                foreach ($a in $allowed) { if ($full -ieq $a) { $target = $a } }
                if (-not $target) {
                    Write-Host "WARNING: refused '$p' in $list (only python\ and bin\ of $root may be listed)"
                    continue
                }
                # only an entry named EXACTLY python / bin (fix round 2): NTFS would also open the editor's `Bin`
                $leaf = Split-Path $target -Leaf
                $names = @([IO.Directory]::GetFileSystemEntries($root) | ForEach-Object { [IO.Path]::GetFileName($_) })
                if ($names -cnotcontains $leaf) {
                    if ($names -contains $leaf) {
                        Write-Host "WARNING: refused '$p' in $list (the folder there is not named exactly $leaf`: not WhyNot Cut's)"
                    }
                    continue
                }
                $err = $null
                for ($i = 1; $i -le 5; $i++) {
                    # the core has just exited: Windows may hold its files a moment longer
                    try {
                        Invoke-WncDeleteTree $target
                        $err = $null
                        break
                    } catch {
                        $err = $_.Exception.Message
                        Start-Sleep -Milliseconds (200 * $i)
                    }
                }
                if ($null -ne $err) {
                    Write-Host "WARNING: could not delete $target ($err); delete it by hand"
                    $failed = $true
                } else {
                    Write-Host "deleted $target"
                }
            } catch {
                Write-Host "WARNING: refused '$line' in $list ($($_.Exception.Message))"
            }
        }
        try {
            [IO.File]::Delete($list)
            if ($homeToo -and (-not $failed) -and (-not $linked) -and [IO.Directory]::Exists($root) -and
                (@([IO.Directory]::GetFileSystemEntries($root)).Count -eq 0)) {
                [IO.Directory]::Delete($root, $false)
                # a program that still has the folder open (an antivirus or indexer scanning what was just deleted)
                # can keep its name listed for a moment after the delete succeeded: wait for it, briefly
                for ($i = 0; ($i -lt 30) -and [IO.Directory]::Exists($root); $i++) { Start-Sleep -Milliseconds 100 }
                if ([IO.Directory]::Exists($root)) {
                    Write-Host "WARNING: $root is still listed; Windows removes it once the program holding it lets go"
                } else {
                    Write-Host "deleted $root"
                }
            }
        } catch {
            Write-Host "WARNING: could not finish the clean-up of $root ($($_.Exception.Message))"
        }
    }

    function Read-WncJsonObject([string]$Path) {
        # the file as a JSON object, read the way the engine reads it (json.loads of UTF-8 text: a BOM or invalid
        # UTF-8 is not JSON); $null when it is missing, unreadable, not JSON or not an object
        try {
            if ((-not $Path) -or (-not [IO.File]::Exists($Path))) { return $null }
            $bytes = [IO.File]::ReadAllBytes($Path)
            if (($bytes.Length -ge 3) -and ($bytes[0] -eq 0xEF) -and ($bytes[1] -eq 0xBB) -and ($bytes[2] -eq 0xBF)) {
                return $null
            }
            $text = (New-Object System.Text.UTF8Encoding -ArgumentList $false, $true).GetString($bytes)
            if ($text.TrimStart([char[]]@(32, 9, 10, 13)) -notmatch '^\{') { return $null }
            $obj = $text | ConvertFrom-Json
            if ($obj -is [System.Management.Automation.PSCustomObject]) { return $obj }
        } catch {
            Write-Verbose "not a JSON object: $Path ($($_.Exception.Message))"
        }
        return $null
    }

    function Get-WncMember($Object, [string]$Name) {
        # @{ Found; Value } of the member named exactly $Name (case-sensitive, like a Python dict key)
        if ($Object -is [System.Management.Automation.PSCustomObject]) {
            foreach ($p in $Object.PSObject.Properties) {
                if ($p.Name -ceq $Name) { return @{ Found = $true; Value = $p.Value } }
            }
        }
        return @{ Found = $false; Value = $null }
    }

    function ConvertTo-WncHomePath([string]$Value, [string]$UserHome, [bool]$Saved) {
        # a configured path as the engine reads it: a saved plugin option goes through plat.native_path (a Git-Bash
        # path /d/x is D:/x); then ~, ~/x and ~\x are under the user home
        $v = $Value
        if ($Saved -and ($v -match '^/([a-zA-Z])(/|$)')) {
            $v = $Matches[1].ToUpperInvariant() + ':/' + $v.Substring([Math]::Min(3, $v.Length))
        }
        if (($v -eq '~') -or $v.StartsWith('~/') -or $v.StartsWith('~\')) { $v = $UserHome + $v.Substring(1) }
        return $v
    }

    function Resolve-WncEngineHome([string]$UserHome, [switch]$Sandbox) {
        # the engine home exactly as the engine resolves it (engine\reel\lib\plat.py engine_home; the core's
        # wnc_installer.base.resolve_engine_home is the same): the first variable that is set, else the plugin option
        # engine_home from the pointer file (~\.whynot-cut\plugin-options.json or WHYNOT_OPTIONS_FILE, when it is a
        # JSON object with an engine_home string; "" = not set), else from settings.json pluginConfigs
        # (whynot-cut@thewhynot-ai, else the first other whynot-cut@* entry with options), else ~\.whynot-cut.
        # -Sandbox: no variable at all, only <UserHome>\.whynot-cut\plugin-options.json and <UserHome>\.claude.
        # @{ Path; Source }; Source is named like the core's (env:<NAME>, pointer:<file>, settings:<file> <key>,
        # default). It is the location question's default.
        $names = @('WHYNOT_HOME', 'CLAUDE_PLUGIN_OPTION_ENGINE_HOME', 'REEL_HOME', 'CLAUDE_PLUGIN_OPTION_REEL_HOME',
            'NH_ENV_DIR')
        if ($Sandbox) { $names = @() }
        foreach ($n in $names) {
            $v = [Environment]::GetEnvironmentVariable($n, 'Process')
            if ($v) {
                $p = ConvertTo-WncHomePath -Value $v -UserHome $UserHome -Saved $false
                return @{ Path = $p; Source = "env:$n" }
            }
        }
        $pointer = Join-Path $UserHome '.whynot-cut\plugin-options.json'
        if ($env:WHYNOT_OPTIONS_FILE -and (-not $Sandbox)) {
            $pointer = ConvertTo-WncHomePath -Value $env:WHYNOT_OPTIONS_FILE -UserHome $UserHome -Saved $false
        }
        $saved = ''
        $source = 'default'
        $m = Get-WncMember (Read-WncJsonObject $pointer) 'engine_home'
        if ($m.Found -and ($m.Value -is [string])) {
            $saved = $m.Value
            $source = "pointer:$pointer"
        } else {
            $cfg = Join-Path $UserHome '.claude'
            if ($env:CLAUDE_CONFIG_DIR -and (-not $Sandbox)) {
                $cfg = ConvertTo-WncHomePath -Value $env:CLAUDE_CONFIG_DIR -UserHome $UserHome -Saved $false
            }
            $settings = Join-Path $cfg 'settings.json'
            $configs = (Get-WncMember (Read-WncJsonObject $settings) 'pluginConfigs').Value
            if ($configs -is [System.Management.Automation.PSCustomObject]) {
                $ours = 'whynot-cut@thewhynot-ai'
                $keys = @($ours) + @($configs.PSObject.Properties | ForEach-Object { $_.Name } |
                        Where-Object { $_.StartsWith('whynot-cut@', [StringComparison]::Ordinal) -and ($_ -cne $ours) })
                foreach ($k in $keys) {
                    $opts = (Get-WncMember (Get-WncMember $configs $k).Value 'options').Value
                    if ($opts -is [System.Management.Automation.PSCustomObject]) {
                        $e = (Get-WncMember $opts 'engine_home').Value
                        if ($e -is [string]) { $saved = $e }
                        $source = "settings:$settings $k"
                        break
                    }
                }
            }
        }
        if ($saved) {
            return @{ Path = (ConvertTo-WncHomePath -Value $saved -UserHome $UserHome -Saved $true); Source = $source }
        }
        return @{ Path = (Join-Path $UserHome '.whynot-cut'); Source = 'default' }
    }

    function Get-WncArabic([string]$Key) {
        return [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($WncAr[$Key]))
    }

    function Get-WncNormPath([string]$Path) {
        # absolute, \ only, no trailing \ (a drive root keeps its \): for comparisons, which ignore case
        $full = [IO.Path]::GetFullPath($Path).TrimEnd([char[]]@([char]92, [char]47))
        if ($full -match '^[A-Za-z]:$') { return $full + [char]92 }
        return $full
    }

    function Test-WncWithin([string]$Child, [string]$Parent, [switch]$Strict) {
        # $Child is $Parent or below it (both from Get-WncNormPath); -Strict: below it only
        if ($Child -ieq $Parent) { return (-not $Strict) }
        $prefix = $Parent.TrimEnd([char]92) + [char]92
        return $Child.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase)
    }

    function Get-WncClientRootList([string]$UserHome, [string]$Pointer) {
        # the clients folders saved so far: clients_root in ~\.claude\whynot-cut.local.md (the preferences) and in
        # the pointer file
        $out = @()
        $prefs = Join-Path $UserHome '.claude\whynot-cut.local.md'
        try {
            if ([IO.File]::Exists($prefs)) {
                $text = [IO.File]::ReadAllText($prefs, [Text.Encoding]::UTF8)
                if ($text -match '(?s)\A\s*---\s*\r?\n(.*?)\r?\n---') {
                    foreach ($line in ($Matches[1] -split '\r?\n')) {
                        if ($line -match '^\s*clients_root\s*:\s*(.*)$') {
                            $v = $Matches[1].Trim()
                            if ($v -match '^"(.*)"$' -or $v -match "^'(.*)'$") {
                                $v = $Matches[1]
                            } else {
                                $v = ($v -split ' #')[0].Trim()
                            }
                            if ($v) { $out += $v }
                        }
                    }
                }
            }
        } catch {
            Write-Verbose "preferences not read: $($_.Exception.Message)"
        }
        $m = Get-WncMember (Read-WncJsonObject $Pointer) 'clients_root'
        if ($m.Found -and ($m.Value -is [string]) -and $m.Value.Trim()) { $out += $m.Value }
        return ,@($out | ForEach-Object { ConvertTo-WncHomePath -Value $_ -UserHome $UserHome -Saved $true })
    }

    function Read-WncJsonFile([string]$Path) {
        # the file as a JSON value (UTF-8; a BOM is tolerated), or $null when it is missing, too big or not JSON
        try {
            if ((-not [IO.File]::Exists($Path)) -or ((New-Object IO.FileInfo $Path).Length -gt 1MB)) { return $null }
            return ([IO.File]::ReadAllText($Path, [Text.Encoding]::UTF8) | ConvertFrom-Json)
        } catch {
            return $null
        }
    }

    function Test-WncEngineHomeMark([string]$Path) {
        # a GENUINE WhyNot Cut engine home (fix round 2: file names alone can be anyone's), the core's
        # base.is_engine_home: state.json is a JSON object with schema 1 and a "plugin" key, or `current` names a valid
        # runtime id whose runtimes\<id>\WHYNOT_RUNTIME is a JSON object with that same id
        $st = Read-WncJsonFile (Join-Path $Path 'state.json')
        if ($st -is [System.Management.Automation.PSCustomObject]) {
            $schema = Get-WncMember $st 'schema'
            if ($schema.Found -and ($schema.Value -is [int] -or $schema.Value -is [long]) -and ($schema.Value -eq 1) -and
                (Get-WncMember $st 'plugin').Found) {
                return $true
            }
        }
        $cur = Join-Path $Path 'current'
        if (-not [IO.File]::Exists($cur)) { return $false }
        try { $rid = [IO.File]::ReadAllText($cur, [Text.Encoding]::UTF8).Trim() } catch { return $false }
        if (($rid -cnotmatch '^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$') -or $rid.Contains('..')) { return $false }
        $stamp = Read-WncJsonFile (Join-Path $Path "runtimes\$rid\WHYNOT_RUNTIME")
        if (-not ($stamp -is [System.Management.Automation.PSCustomObject])) { return $false }
        $id = Get-WncMember $stamp 'id'
        return ($id.Found -and ($id.Value -is [string]) -and ($id.Value -ceq $rid))
    }

    function Get-WncOccupiedEntry([string]$Path, [bool]$PointerOk) {
        # what makes an existing folder the editor's (the core's base.occupied_entries): every entry except the write
        # probe (.wnc-write-test*), the -Source cache (a `downloads` folder holding only `release-*` folders) and, in
        # ~\.whynot-cut, the pointer plugin-options.json. Names compare EXACTLY (case too).
        $out = @()
        if (-not [IO.Directory]::Exists($Path)) { return ,$out }
        foreach ($e in [IO.Directory]::GetFileSystemEntries($Path)) {
            $n = [IO.Path]::GetFileName($e)
            if ($n.StartsWith('.wnc-write-test', [StringComparison]::Ordinal)) { continue }
            if ($PointerOk -and ($n -ceq 'plugin-options.json')) { continue }
            if (($n -ceq 'downloads') -and [IO.Directory]::Exists($e) -and (-not (Test-WncReparse $e))) {
                $kids = @([IO.Directory]::GetFileSystemEntries($e) | ForEach-Object { [IO.Path]::GetFileName($_) })
                if (@($kids | Where-Object { -not $_.StartsWith('release-', [StringComparison]::Ordinal) }).Count -eq 0) {
                    continue
                }
            }
            $out += $n
        }
        return ,@($out | Sort-Object)
    }

    function Find-WncMarkerScan([string]$Path) {
        # @{ Found; TooBig }: a folder up to 3 levels below $Path holding .whynot-client (links never entered), and
        # whether more than 5000 entries were met first (the core's base._marker_scan, MARKER_SCAN_LIMIT)
        $seen = 0
        $stack = New-Object System.Collections.Stack
        $stack.Push(@($Path, 0))
        while ($stack.Count -gt 0) {
            $item = $stack.Pop()
            try { $entries = [IO.Directory]::GetFileSystemEntries($item[0]) } catch { continue }
            foreach ($e in $entries) {
                $seen++
                if ($seen -gt 5000) { return @{ Found = $null; TooBig = $true } }
                if ([IO.Path]::GetFileName($e) -eq '.whynot-client') { return @{ Found = $item[0]; TooBig = $false } }
                if (($item[1] -lt 3) -and [IO.Directory]::Exists($e) -and (-not (Test-WncReparse $e))) {
                    $stack.Push(@($e, ($item[1] + 1)))
                }
            }
        }
        return @{ Found = $null; TooBig = $false }
    }

    function Find-WncMarkerBelow([string]$Path) {
        # a folder up to 3 levels below $Path holding .whynot-client, or $null (the chosen-folder rule: past the
        # limit, $null)
        return (Find-WncMarkerScan $Path).Found
    }

    function Get-WncEnginePlace([string]$Path, [string]$UserHome, [string]$Root, [string[]]$Clients,
        [string]$SandboxRoot) {
        # where the engine goes for the folder the editor chose: @{ Path; Note; Problem }. The core's
        # wnc_installer.base.choose_engine_home, same rules and order: refused - not a full path, a drive root or
        # mounted volume, a link / mount point, inside the plugin folder; unless it is already an engine home also
        # one that holds the plugin (except in its downloads\: the -Source cache), is / holds / lies inside the saved
        # clients folder, lies inside or holds (3 levels) a .whynot-client folder. Moved into <it>\WhyNotCut: the user
        # folder, Desktop, Documents, Downloads, and any existing folder with any entry (Get-WncOccupiedEntry: names
        # are not trusted) that is not a GENUINE engine home (Test-WncEngineHomeMark: by content). Then the final
        # folder: not holding the user folder, not inside
        # Claude's folder, not a WhyNotCut subfolder holding other files, in a sandbox inside it.
        if ((-not $Path) -or ($Path -notmatch '^([A-Za-z]:[\\/]|\\\\[^\\]+\\[^\\]+)')) {
            return @{ Problem = "$Path is not a full path (for example C:\WhyNotCut)" }
        }
        $n = Get-WncNormPath $Path
        if (($n -match '^[A-Za-z]:\\$') -or ($n -match '^\\\\[^\\]+\\[^\\]+$')) {
            return @{ Problem = "$Path is a drive root or a mounted volume; choose a folder on it, for example $(Join-Path $n 'WhyNotCut')" }
        }
        if ([IO.Directory]::Exists($n) -and (Test-WncReparse $n)) {
            return @{ Problem = "$Path is a link or mount point; choose a real folder" }
        }
        $r = Get-WncNormPath $Root
        if (Test-WncWithin $n $r) {
            return @{ Problem = "$Path is inside the plugin folder $r, which is replaced on every update" }
        }
        $existing = Test-WncEngineHomeMark $n
        if (-not $existing) {
            if ((Test-WncWithin $r $n -Strict) -and (-not (Test-WncWithin $r (Join-Path $n 'downloads'))) -and
                (-not (Test-WncWithin $r (Join-Path $n 'WhyNotCut\downloads')))) {
                return @{ Problem = "$Path holds the plugin folder $r; choose a folder of its own" }
            }
            foreach ($c in @($Clients | Where-Object { $_ })) {
                try { $cn = Get-WncNormPath $c } catch { continue }
                if ((Test-WncWithin $n $cn) -or (Test-WncWithin $cn $n -Strict)) {
                    return @{ Problem = "$Path is, holds or is inside your clients folder $c; keep the engine apart from client footage" }
                }
            }
            $d = $n
            while ($d) {
                if (Test-Path -LiteralPath (Join-Path $d '.whynot-client')) {
                    return @{ Problem = "$Path is inside a client folder ($d holds .whynot-client)" }
                }
                $up = [IO.Path]::GetDirectoryName($d)
                if ((-not $up) -or ($up -eq $d)) { break }
                $d = $up
            }
            if ([IO.Directory]::Exists($n)) {
                $below = Find-WncMarkerBelow $n
                if ($below) { return @{ Problem = "$Path holds a client folder ($below holds .whynot-client)" } }
            }
        }
        $final = $n
        $note = ''
        $homeRoots = @($UserHome) + @('Desktop', 'Documents', 'Downloads' | ForEach-Object { Join-Path $UserHome $_ })
        $isRoot = @($homeRoots | Where-Object { (Get-WncNormPath $_) -ieq $n }).Count -gt 0
        $pointerOk = (Get-WncNormPath (Join-Path $UserHome '.whynot-cut')) -ieq $n  # the hook's pointer lives there
        if ((-not $existing) -and ($isRoot -or ((Get-WncOccupiedEntry -Path $n -PointerOk $pointerOk).Count -gt 0))) {
            $final = Join-Path $n 'WhyNotCut'
            $note = "$Path already holds other files, so WhyNot Cut goes into its own folder $final (uninstall then never touches the rest)"
        }
        if (Test-WncWithin (Get-WncNormPath $UserHome) $final) {
            return @{ Problem = "$final is your user folder or holds it; choose a folder of its own" }
        }
        if (Test-WncWithin $final (Get-WncNormPath (Join-Path $UserHome '.claude'))) {
            return @{ Problem = "$final is inside Claude's folder $(Join-Path $UserHome '.claude')" }
        }
        if (($final -ine $n) -and (-not (Test-WncEngineHomeMark $final)) -and
            ((Get-WncOccupiedEntry -Path $final -PointerOk $false).Count -gt 0)) {
            return @{ Problem = "$final already holds other files; choose an empty folder or one of its own" }
        }
        if ($SandboxRoot -and (-not (Test-WncWithin $final (Get-WncNormPath $SandboxRoot) -Strict))) {
            return @{ Problem = "$final is outside the sandbox home $SandboxRoot (-Home: nothing outside it is used)" }
        }
        return @{ Path = $final; Note = $note; Problem = $null }
    }

    function Get-WncFreeGb([string]$Path) {
        # free space on the drive of $Path in GB, or $null when it cannot be read (a network path)
        if ($null -ne $S.FreeGb) { return [double]$S.FreeGb }
        try {
            $rootDir = [IO.Path]::GetPathRoot($Path)
            if ($rootDir -match '^[A-Za-z]:') {
                return [math]::Round((New-Object IO.DriveInfo $rootDir).AvailableFreeSpace / 1GB, 1)
            }
        } catch {
            Write-Verbose "free space not read: $($_.Exception.Message)"
        }
        return $null
    }

    function Test-WncKeyboard {
        # a person at the console: an interactive session whose input is not redirected, not -NonInteractive
        try { if ([Console]::IsInputRedirected) { return $false } } catch { return $false }
        if (-not [Environment]::UserInteractive) { return $false }
        if (@([Environment]::GetCommandLineArgs() | Where-Object { $_ -match '^-noni' }).Count -gt 0) { return $false }
        return $true
    }

    function Test-WncCanAsk {
        # the location question: only on the Customise path (D-T1), never with -Yes, never for -Uninstall; the test
        # hook (sandbox only); else only with a keyboard
        if ($Yes -or $Uninstall -or ($S.Mode -ne 'customise')) { return $false }
        if ($null -ne $S.Answers) { return $true }
        return (Test-WncKeyboard)
    }

    function Get-WncValue($Object, [string[]]$Keys) {
        # the JSON value at that key path (exact names), or $null
        $v = $Object
        foreach ($k in $Keys) {
            $m = Get-WncMember $v $k
            if (-not $m.Found) { return $null }
            $v = $m.Value
        }
        return $v
    }

    function Get-WncSizedGb($Items, [double]$Fallback) {
        # the sum of the `bytes` of the entries that have one, in GB; $Fallback when none has (system.py _sized_gb)
        $sum = [double]0
        $any = $false
        foreach ($i in @($Items)) {
            $b = (Get-WncMember $i 'bytes').Value
            if (($b -is [int]) -or ($b -is [long])) {
                $sum += [double]$b
                $any = $true
            }
        }
        if ($any) { return $sum / 1GB }
        return $Fallback
    }

    function Test-WncGitMissing([bool]$Sandbox) {
        # no Git Bash where the core's gitbash step looks (claude.find_git_bash; a sandbox: its LOCALAPPDATA only)
        $c = @()
        if ($env:LOCALAPPDATA) {
            $c += Join-Path $env:LOCALAPPDATA 'Programs\Git\bin\bash.exe'
            $c += Join-Path $env:LOCALAPPDATA 'WhyNotCut\git\bin\bash.exe'
        }
        if (-not $Sandbox) {
            $git = @(Get-Command git -CommandType Application -ErrorAction SilentlyContinue)
            if ($git.Count -gt 0) { $c += Join-Path (Split-Path (Split-Path $git[0].Source -Parent) -Parent) 'bin\bash.exe' }
            foreach ($v in @($env:ProgramFiles, ${env:ProgramFiles(x86)})) { if ($v) { $c += Join-Path $v 'Git\bin\bash.exe' } }
        }
        return (@($c | Where-Object { [IO.File]::Exists($_) }).Count -eq 0)
    }

    function Get-WncInstallGb([string]$CompPath, [string[]]$SkipList, [bool]$Sandbox) {
        # D-T1: about how many GB the install brings, rounded up to one decimal (the core's system.install_size_gb):
        # the runtime 0.5, ffmpeg and the fonts (their `bytes`, else 0.1 / 0.01), the Whisper model (-Model or
        # large-v3: models.<m>.bytes, else its size), PortableGit unpacked (0.4) when Git Bash is missing and the CUDA
        # libraries (1.0) when an NVIDIA GPU is there
        $c = $null
        try { $c = [IO.File]::ReadAllText($CompPath, [Text.Encoding]::UTF8) | ConvertFrom-Json } catch { $c = $null }
        $m = 'large-v3'
        if ($Model) { $m = $Model }
        $total = [double]0
        if ($SkipList -notcontains 'runtime') { $total += $WncSizes.runtime }
        if ($SkipList -notcontains 'ffmpeg') {
            $total += Get-WncSizedGb (Get-WncValue $c @('ffmpeg', 'assets', 'win-x64', 'files')) $WncSizes.ffmpeg
        }
        if ($SkipList -notcontains 'fonts') {
            $items = @(Get-WncValue $c @('fonts', 'files')) + @(Get-WncValue $c @('fonts', 'licenses'))
            $total += Get-WncSizedGb $items $WncSizes.fonts
        }
        if ($SkipList -notcontains 'model') {
            $b = Get-WncValue $c @('models', $m, 'bytes')
            if (($b -is [int]) -or ($b -is [long])) { $total += [double]$b / 1GB } else { $total += $WncModelSizes[$m] }
        }
        if (($SkipList -notcontains 'gitbash') -and (Test-WncGitMissing $Sandbox)) { $total += $WncSizes.git }
        if (($SkipList -notcontains 'gpu') -and (Test-WncNvidia $Sandbox)) { $total += $WncSizes.cuda }
        $gb = [Math]::Ceiling([Math]::Round($total * 10, 6)) / 10
        return $gb.ToString('0.0', [Globalization.CultureInfo]::InvariantCulture)
    }

    function Read-WncCountdown {
        # D-T1: "Press C to customise (10)..." on one line that counts down in place, 10 s. Returns 'customise' (C),
        # 'key' (any other key: go on at once) or 'timeout'. The sandbox-only hook WNC_TEST_KEYS stands in for the
        # keyboard ("C", another key, "none" = nobody presses; it waits WNC_TEST_COUNTDOWN_S seconds in all). Any
        # console error ends it as a timeout: it never blocks.
        $line = (Get-WncArabic 'Countdown')
        $ell = [string][char]0x2026
        $hook = $null -ne $S.TestKeys
        $result = 'timeout'
        if (-not $hook) {
            try {
                while ([Console]::KeyAvailable) { $null = [Console]::ReadKey($true) }  # typed ahead: not an answer
            } catch {
                return 'timeout'
            }
        }
        for ($sec = 10; ($sec -ge 1) -and ($result -eq 'timeout'); $sec--) {  # (not $s: that is $S)
            Write-Host -NoNewline ("`rPress C to customise ($sec)$ell / $line ")
            if ($hook) {
                $k = ([string]$S.TestKeys).Trim()
                if ($k -and ($k -ne 'none')) {
                    if ($k.Substring(0, 1) -ieq 'c') { $result = 'customise' } else { $result = 'key' }
                } elseif ($S.CountdownS -gt 0) {
                    Start-Sleep -Milliseconds (100 * $S.CountdownS)
                }
                continue
            }
            $until = [DateTime]::UtcNow.AddSeconds(1)
            while (($result -eq 'timeout') -and ([DateTime]::UtcNow -lt $until)) {
                try {
                    if ([Console]::KeyAvailable) {
                        $key = [Console]::ReadKey($true)
                        if (([string]$key.KeyChar) -ieq 'c') { $result = 'customise' } else { $result = 'key' }
                    } else {
                        Start-Sleep -Milliseconds 50
                    }
                } catch {
                    Write-Host ''
                    return 'timeout'
                }
            }
        }
        Write-Host ''
        return $result
    }

    function Select-WncMode([string]$CompPath, [string[]]$SkipList, [bool]$Sandbox) {
        # D-T1: 'customise' (-Customise, or C during the countdown), 'default' (a person at the console who did not
        # customise) or 'yes' (-Yes, -Uninstall, or nobody at a keyboard). The core gets --customise for the first,
        # --yes for the other two: the same strongest defaults and the same state.json.
        if ($Uninstall) { return 'yes' }
        if ($Customise) { return 'customise' }
        $gb = Get-WncInstallGb -CompPath $CompPath -SkipList $SkipList -Sandbox $Sandbox
        Write-Host "Installing everything WhyNot Cut needs (about $gb GB)"
        Write-Host ((Get-WncArabic 'Size') -f $gb)
        if ($Yes) { return 'yes' }
        if (($null -eq $S.TestKeys) -and (-not (Test-WncKeyboard))) { return 'yes' }
        if ((Read-WncCountdown) -ne 'customise') { return 'default' }
        Write-Host 'Customise: answer the questions below; Enter keeps the suggested answer.'
        Write-Host (Get-WncArabic 'Customising')
        return 'customise'
    }

    function ConvertFrom-WncDevicePath([string]$Path) {
        # \\?\C:\x (a long-path prefix) is C:\x; any other \\?\ or \\.\ form is left as it is (refused by the guard)
        if ($Path -match '^[\\/]{2}[?.][\\/]([A-Za-z]:([\\/].*)?)$') { return $Matches[1] }
        return $Path
    }

    function Get-WncLinkTarget([string]$Path) {
        # where a junction / symlink points (full path), or $null (a volume mount point, an unreadable link)
        try {
            $item = Get-Item -LiteralPath $Path -Force
            $target = @($item.Target | Where-Object { $_ })
            if ($target.Count -eq 0) { return $null }
            $t = [string]$target[0]
            if ($t -match '^\\\\\?\\') { $t = $t.Substring(4) }
            if ($t -match '^Volume\{' -or $t -match '^\\\\\?\\Volume') { return $null }
            if (-not ($t -match '^([A-Za-z]:[\\/]|\\\\)')) { $t = Join-Path (Split-Path $Path -Parent) $t }
            return (Get-WncNormPath $t)
        } catch {
            return $null
        }
    }

    function Get-WncRealPath([string]$Path) {
        # $Path with every junction / symlink on the way resolved (the core's os.path.realpath), or $null when a link
        # cannot be followed (a folder mount point); a part that does not exist yet is kept as written
        if ($Path -match '^[\\/]{2}') { return $null }  # network / device paths: not followed (fix round 2)
        try { $cur = Get-WncNormPath $Path } catch { return $null }
        for ($hop = 0; $hop -lt 40; $hop++) {
            if ($cur -match '^[\\/]{2}') { return $null }
            $rootDir = [IO.Path]::GetPathRoot($cur)
            $parts = @($cur.Substring($rootDir.Length).Split([char[]]@([char]92), [StringSplitOptions]::RemoveEmptyEntries))
            $built = $rootDir
            $changed = $false
            for ($i = 0; $i -lt $parts.Count; $i++) {
                $next = Join-Path $built $parts[$i]
                if (Test-WncReparse $next) {
                    $target = Get-WncLinkTarget $next
                    if (-not $target) { return $null }
                    $rest = @($parts | Select-Object -Skip ($i + 1))
                    $cur = $target
                    if ($rest.Count -gt 0) { $cur = Get-WncNormPath (Join-Path $target ($rest -join [string][char]92)) }
                    $changed = $true
                    break
                }
                $built = $next
            }
            if (-not $changed) { return (Get-WncNormPath $built) }
        }
        return $null
    }

    function Get-WncKnownFolderList([string]$UserHome, [bool]$Sandbox) {
        # @(name, folder) pairs of Desktop / Documents / Downloads: under the user folder and, outside a sandbox, where
        # Windows puts them (OneDrive Known Folder Move; the core's base.shell_folders reads the same registry values)
        $out = @(foreach ($r in @('Desktop', 'Documents', 'Downloads')) { ,@($r, (Join-Path $UserHome $r)) })
        if (-not $Sandbox) {
            $key = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders'
            foreach ($pair in @(@('Desktop', 'Desktop'), @('Documents', 'Personal'),
                    @('Downloads', '{374DE290-123F-4565-9164-39C4925E467B}'))) {
                try {
                    $v = (Get-ItemProperty -LiteralPath $key -Name $pair[1] -ErrorAction Stop).($pair[1])
                    if ($v) { $out += ,@($pair[0], [Environment]::ExpandEnvironmentVariables([string]$v)) }
                } catch {
                    Write-Verbose "no shell folder $($pair[1])"
                }
            }
        }
        return ,$out
    }

    function Get-WncResolvedHomeProblem([string]$Path, [string]$UserHome, [string[]]$Clients, [bool]$Sandbox) {
        # task 9 (the core's base.resolved_home_problem): why a RESOLVED engine home other than ~\.whynot-cut may not
        # be used - a link / reparse point itself (junction, symlink, a volume mounted into a folder), a drive root,
        # the user folder or Desktop / Documents / Downloads themselves (also where Windows' shell folders put them),
        # the saved clients folder or a folder holding it, a folder with .whynot-client in it or up to 3 levels
        # below, or one too big to check for that (more than 5000 entries); compared as written and with links
        # resolved; else $null
        if ($Path -match '^[\\/]{2}') {
            # (after ConvertFrom-WncDevicePath) \\.\..., \\?\UNC\..., \\server\share\... (also \\localhost\C$):
            # a network or device path is never a resolved engine home (fix round 2)
            return 'a network share or device path; name a folder on a local drive'
        }
        $n = Get-WncNormPath $Path
        if ($n -ieq (Get-WncNormPath (Join-Path $UserHome '.whynot-cut'))) { return $null }
        $rootLike = '^([A-Za-z]:\\|\\\\[^\\]+\\[^\\]+)$'
        if ($n -match $rootLike) { return 'a drive root or a mount point' }
        if (Test-WncReparse $n) {
            return 'a link or mount point (a junction, symlink or mounted folder); name the real folder instead'
        }
        $real = Get-WncRealPath $n
        if (-not $real) { return 'reached through a link or mount point that cannot be followed; name the real folder' }
        $keys = @($n, $real)
        if ($real -match $rootLike) { return 'a drive root or a mount point' }
        $homes = @((Get-WncNormPath $UserHome), (Get-WncRealPath $UserHome)) | Where-Object { $_ }
        if (@($keys | Where-Object { $homes -contains $_ }).Count -gt 0) { return 'your user folder itself' }
        foreach ($pair in (Get-WncKnownFolderList -UserHome $UserHome -Sandbox $Sandbox)) {
            try { $f = @((Get-WncNormPath $pair[1]), (Get-WncRealPath $pair[1])) | Where-Object { $_ } } catch { continue }
            if (@($keys | Where-Object { $f -contains $_ }).Count -gt 0) { return "your $($pair[0]) folder itself" }
        }
        foreach ($c in @($Clients | Where-Object { $_ })) {
            try { $cs = @((Get-WncNormPath $c), (Get-WncRealPath $c)) | Where-Object { $_ } } catch { continue }
            foreach ($ck in $cs) {
                foreach ($k in $keys) { if (Test-WncWithin $ck $k) { return "your clients folder $c, or it holds it" } }
            }
        }
        if ([IO.Directory]::Exists($real)) {
            $scan = Find-WncMarkerScan $real
            if ($scan.Found) { return "holding a client folder ($($scan.Found) holds .whynot-client)" }
            if ($scan.TooBig) {
                return ('too big to check for client folders (more than 5000 entries within 3 levels); choose an ' +
                    'engine folder of its own with -EngineHome / --engine-home')
            }
        }
        return $null
    }

    function Test-WncNvidia([bool]$Sandbox) {
        # an NVIDIA GPU for the size estimate (the gpu step installs the CUDA libraries, about 1 GB): nvidia-smi is
        # there; a sandbox only WNC_TEST_NVIDIA=1 (the core's runtime._nvidia_present, without running it)
        if ($Sandbox) { return ($env:WNC_TEST_NVIDIA -eq '1') }
        if (@(Get-Command nvidia-smi -CommandType Application -ErrorAction SilentlyContinue).Count -gt 0) { return $true }
        $windir = $env:SystemRoot
        if (-not $windir) { $windir = 'C:\Windows' }
        return [IO.File]::Exists((Join-Path $windir 'System32\nvidia-smi.exe'))
    }

    function Read-WncAnswer([string]$Default) {
        # one line from the editor (Enter = $Default, shown in brackets); $null when there is no more input
        Write-Host -NoNewline ("Folder / " + (Get-WncArabic 'Folder') + " [$Default]: ")
        if ($null -ne $S.Answers) {
            if ($S.AnswerAt -ge $S.Answers.Count) {
                Write-Host ''
                return $null
            }
            $a = [string]$S.Answers[$S.AnswerAt]
            $S.AnswerAt++
            Write-Host $a
            return $a.Trim()
        }
        $line = Read-Host
        if ($null -eq $line) { return $null }
        return $line.Trim()
    }

    function ConvertFrom-WncTyped([string]$Text, [string]$UserHome) {
        # a typed or -EngineHome folder: quotes trimmed, ~ is the user folder; a full path made canonical, any other
        # text returned as it is (Get-WncEnginePlace refuses it)
        $t = $Text.Trim().Trim([char]34).Trim([char]39)
        $t = ConvertTo-WncHomePath -Value $t -UserHome $UserHome -Saved $false
        if ($t -match '^([A-Za-z]:[\\/]|\\\\[^\\]+\\[^\\]+)') { return Get-WncFullPath $t }
        return $t
    }

    function Select-WncEngineHome([string]$Default, [string]$UserHome, [string]$Root, [string]$Pointer,
        [string]$SandboxRoot, [bool]$WithModel) {
        # the location question (see the header): @{ Code = 0; Path; Chosen } or @{ Code = 2 }
        $ask = Test-WncCanAsk
        $clients = Get-WncClientRootList -UserHome $UserHome -Pointer $Pointer
        $suggest = 'C:\WhyNotCut'
        if ($SandboxRoot) { $suggest = Join-Path $SandboxRoot 'WhyNotCut' }
        $chosen = $false
        $text = $Default
        if ($EngineHome) {
            $text = $EngineHome
            $chosen = $true
        } elseif ($ask) {
            Write-Host ('Where should WhyNot Cut keep its engine (Python, ffmpeg, the Whisper model)? It needs about ' +
                "$WncNeedGb GB, $($WncNeedGb + $WncModelGb) GB with the model. Enter keeps the folder in brackets.")
            Write-Host (Get-WncArabic 'Intro')
            if (Test-WncEngineHomeMark $Default) {
                Write-Host "WhyNot Cut is already installed in $Default; Enter keeps it there."
                Write-Host (Get-WncArabic 'Existing')
            }
            $a = Read-WncAnswer $Default
            if ($a) {
                $text = $a
                $chosen = $true
            }
        }
        $warned = $false  # warned once about non-ASCII letters: the next answer is taken as it is
        # WhyNot Cut already lives in the default folder: a 3.0 install, or a 2.x one (venv, models ... without a
        # 3.0 state.json) - leaving either behind is said
        $oldInstall = (Test-WncEngineHomeMark $Default) -or ((Get-WncOccupiedEntry -Path $Default -PointerOk $true).Count -gt 0)
        for ($try = 1; $try -le 8; $try++) {
            $p = ConvertFrom-WncTyped -Text $text -UserHome $UserHome
            $isDefault = ($p -match '^([A-Za-z]:[\\/]|\\\\)') -and ((Get-WncNormPath $p) -ieq (Get-WncNormPath $Default))
            if ($isDefault) {
                # the resolved home (default ~\.whynot-cut, or saved in the pointer / settings.json / a variable) is
                # used as it is (fix round 3): a 2.x home (venv, models, ...) is upgraded in place, never moved
                $chosen = $false
                $p = Get-WncNormPath $p
                $problem = $null
                if ($SandboxRoot -and (-not (Test-WncWithin $p (Get-WncNormPath $SandboxRoot) -Strict))) {
                    $problem = "$p is outside the sandbox home $SandboxRoot (-Home: nothing outside it is used)"
                }
            } else {
                # a folder the editor chose: placed (its own WhyNotCut subfolder when it holds anything) and checked
                $place = Get-WncEnginePlace -Path $p -UserHome $UserHome -Root $Root -Clients $clients `
                    -SandboxRoot $SandboxRoot
                $problem = $place.Problem
                if (-not $problem) {
                    if ($place.Note) {
                        Write-Host $place.Note
                        Write-Host (Get-WncArabic 'Subfolder')
                    }
                    $p = $place.Path
                }
            }
            $existing = (-not $problem) -and (Test-WncEngineHomeMark $p)
            if ((-not $problem) -and ($p -match '[^\x00-\x7F]') -and $existing) {
                # an existing install is never moved by Enter: no re-ask (fix round 1)
                Write-Host "note: $p has non-English letters; WhyNot Cut is already installed there, so it stays there"
            } elseif ((-not $problem) -and ($p -match '[^\x00-\x7F]') -and (-not $warned)) {
                Write-Host ("WARNING: $p has non-English letters. Some tools can fail on such a path; a plain " +
                    'folder such as C:\WhyNotCut is safer.')
                Write-Host (Get-WncArabic 'NonAscii')
                $warned = $true
                if ($ask) {
                    $a = Read-WncAnswer $suggest
                    if ($null -eq $a) { return @{ Code = 2 } }
                    if ($a) { $text = $a } else { $text = $suggest }
                    $chosen = $true
                    continue
                }
                Write-Host '(kept: no question was asked)'
            }
            if ((-not $problem) -and (-not $existing)) {
                $need = $WncNeedGb
                if ($WithModel) { $need += $WncModelGb }
                $free = Get-WncFreeGb $p
                if (($null -ne $free) -and ($free -lt $need)) {
                    $problem = ("only $free GB free on its drive; WhyNot Cut needs $need GB there ($WncNeedGb GB, plus " +
                        "$WncModelGb GB for the Whisper model unless you add -Skip model)")
                }
            }
            if ((-not $problem) -and (-not $DryRun)) {
                try {
                    $null = [IO.Directory]::CreateDirectory($p)
                    $probe = Join-Path $p (".wnc-write-test-$PID")
                    [IO.File]::WriteAllText($probe, 'x')
                    [IO.File]::Delete($probe)
                    # claim the folder before anything lands in it (fix round 2): a run that stops before the core
                    # (a failed download) leaves a GENUINE engine home, so the next run uses it again directly
                    $st = Join-Path $p 'state.json'
                    if (-not [IO.File]::Exists($st)) {
                        [IO.File]::WriteAllText($st, '{"schema": 1, "plugin": null, "updated_at": null, "steps": {}}' +
                            "`n", $S.Utf8)
                    }
                } catch {
                    $problem = "it cannot be created or written ($($_.Exception.Message))"
                }
            }
            if (-not $problem) {
                if ($oldInstall -and ((Get-WncNormPath $p) -ine (Get-WncNormPath $Default))) {
                    Write-Host ("WARNING: the WhyNot Cut already installed in $Default stays there and is no longer " +
                        'used; delete it yourself when you no longer need it.')
                    Write-Host ((Get-WncArabic 'LeftBehind') + " $Default")
                }
                return @{ Code = 0; Path = $p; Chosen = $chosen }
            }
            Write-Host "WhyNot Cut cannot use $p as its engine home: $problem"
            Write-Host (Get-WncArabic 'Cannot')
            if (-not $ask) {
                Write-Host 'Nothing was downloaded. Run the installer again with -EngineHome <folder>.'
                return @{ Code = 2 }
            }
            $a = Read-WncAnswer $Default
            if ($null -eq $a) { return @{ Code = 2 } }
            if ($a) {
                $text = $a
                $chosen = $true
            } else {
                $text = $Default
                $chosen = $false
            }
        }
        return @{ Code = 2 }
    }

    function Initialize-WncBootstrap {
        # @{ Code; Run; Py; CoreArgs } - every check and download; the core itself runs outside, uncaptured
        $arch = $env:PROCESSOR_ARCHITEW6432
        if (-not $arch) { $arch = $env:PROCESSOR_ARCHITECTURE }
        if ($arch -ne 'AMD64') {
            Write-Host "WhyNot Cut runs on Windows x64 (and macOS); this PC is $arch."
            return @{ Code = 2 }
        }
        $root = Get-WncFullPath $PluginRoot
        if ($Model -and ($WncModels -notcontains $Model)) {
            Write-Host "ERROR: -Model $Model is not one of $($WncModels -join ', ')"
            return @{ Code = 2 }
        }
        if ($Customise -and $Yes -and (-not $Uninstall)) {
            Write-Host 'ERROR: -Yes and -Customise cannot be used together (-Yes asks nothing; -Customise asks the questions)'
            return @{ Code = 2 }
        }
        $skipList = @($Skip | Where-Object { $_ } | ForEach-Object { $_ -split ',' } | Where-Object { $_.Trim() } |
            ForEach-Object { $_.Trim() })
        $sandbox = [bool]$SandboxHome
        if ($sandbox) {
            $h = Get-WncFullPath $SandboxHome
            $env:HOME = $h
            $env:USERPROFILE = $h
            $env:APPDATA = Join-Path $h 'AppData\Roaming'
            $env:LOCALAPPDATA = Join-Path $h 'AppData\Local'
            $env:CLAUDE_CONFIG_DIR = Join-Path $h '.claude'
            $resolved = Resolve-WncEngineHome $h -Sandbox
            $pointer = Join-Path $h '.whynot-cut\plugin-options.json'
            if ($env:WNC_TEST_ANSWERS) { $S.Answers = @([IO.File]::ReadAllLines($env:WNC_TEST_ANSWERS, $S.Utf8)) }
            if ($env:WNC_TEST_FREE_GB) { $S.FreeGb = $env:WNC_TEST_FREE_GB }
            if ($null -ne $env:WNC_TEST_KEYS) { $S.TestKeys = $env:WNC_TEST_KEYS }
            $cd = 0
            if ([int]::TryParse([string]$env:WNC_TEST_COUNTDOWN_S, [ref]$cd) -and ($cd -ge 0)) { $S.CountdownS = $cd }
        } else {
            $h = $env:USERPROFILE
            if (-not $h) { $h = $env:HOME }
            $resolved = Resolve-WncEngineHome $h
            $pointer = Join-Path $h '.whynot-cut\plugin-options.json'
            if ($env:WHYNOT_OPTIONS_FILE) {
                $pointer = ConvertTo-WncHomePath -Value $env:WHYNOT_OPTIONS_FILE -UserHome $h -Saved $false
            }
        }
        try {
            $default = Get-WncFullPath (ConvertFrom-WncDevicePath $resolved.Path)
        } catch {
            $default = [string]$resolved.Path  # (a path PowerShell cannot even read: the guard below refuses it)
        }
        $chosen = $false
        $sandboxRoot = $null
        if ($sandbox) { $sandboxRoot = $h }
        $compPath = Join-Path $root 'setup\components.json'
        if ($Components) { $compPath = Get-WncFullPath $Components }
        $isResolved = -not $EngineHome
        if ($EngineHome) {
            # -EngineHome naming the saved home itself is that home, used as it is (not placed): guard it too (fix round 2)
            try {
                $typed = ConvertFrom-WncTyped -Text (ConvertFrom-WncDevicePath $EngineHome) -UserHome $h
                $isResolved = ($typed -match '^([A-Za-z]:[\\/]|\\\\)') -and
                    ((Get-WncNormPath $typed) -ieq (Get-WncNormPath $default))
            } catch {
                $isResolved = $false  # (the chosen-folder rules refuse it)
            }
        }
        if ((-not $Uninstall) -and $isResolved) {
            # task 9: a home saved somewhere in a place it must never be: stop and say the fix, before the countdown
            # and any download (fix round 1), also when -EngineHome names that same folder (fix round 2)
            $clients = Get-WncClientRootList -UserHome $h -Pointer $pointer
            try {
                $why = Get-WncResolvedHomeProblem -Path $default -UserHome $h -Clients $clients -Sandbox $sandbox
            } catch {
                $why = "a path that cannot be checked ($($_.Exception.Message))"
            }
            if ($why) {
                Write-Host ("ERROR: WhyNot Cut will not use $default as its engine home (from $($resolved.Source)): it " +
                    "is $why. Nothing was downloaded. To fix it, run the installer again with -EngineHome <folder> / " +
                    '--engine-home <folder> (a folder of its own, for example C:\WhyNotCut).')
                Write-Host (Get-WncArabic 'Guard')
                return @{ Code = 2 }
            }
        }
        # D-T1: no question unless the editor customises (the -Customise flag, or C during the countdown)
        $S.Mode = Select-WncMode -CompPath $compPath -SkipList $skipList -Sandbox $sandbox
        if ($Uninstall) {
            # no question: the folder the engine uses (or -EngineHome); the core checks a chosen one
            $engine = $default
            if ($EngineHome) {
                $engine = ConvertFrom-WncTyped -Text $EngineHome -UserHome $h
                $chosen = $true
            }
        } else {
            $sel = Select-WncEngineHome -Default $default -UserHome $h -Root $root -Pointer $pointer `
                -SandboxRoot $sandboxRoot -WithModel ($skipList -notcontains 'model')
            if ($sel.Code -ne 0) { return @{ Code = 2 } }
            $engine = $sel.Path
            $chosen = $sel.Chosen
        }
        if ($sandbox) { $env:WHYNOT_HOME = $engine }
        $testUv = $null
        if ($sandbox -and $env:WNC_TEST_UV) { $testUv = $env:WNC_TEST_UV }
        # the core reads the test answers after the ones the location question used
        if ($null -ne $S.Answers) { $env:WNC_TEST_ANSWERS_AT = [string]$S.AnswerAt }

        try {
            $c = [IO.File]::ReadAllText($compPath, [Text.Encoding]::UTF8) | ConvertFrom-Json
            $uvVer = [string]$c.uv.version
            $asset = $c.uv.assets.'win-x64'
            $uvUrl = [string]$asset.url
            $uvSha = ([string]$asset.sha256).ToLowerInvariant()
            $uvKind = [string]$asset.archive
            $pyVer = [string]$c.runtime.python
        } catch {
            Write-Host "ERROR: cannot read the uv / Python pins in $compPath ($($_.Exception.Message))"
            return @{ Code = 2 }
        }
        if ((Test-WncPlaceholder $uvUrl) -or ($uvSha -notmatch '^[0-9a-f]{64}$') -or (-not $uvVer) -or (-not $pyVer)) {
            Write-Host "ERROR: $compPath has no usable uv pin for win-x64 (url, sha256, version) or runtime.python"
            return @{ Code = 2 }
        }
        $core = Join-Path $root 'installer\core\wnc_install.py'
        if (-not (Test-Path -LiteralPath $core -PathType Leaf)) {
            Write-Host "ERROR: the installer core is missing: $core"
            return @{ Code = 2 }
        }
        $command = 'install'
        if ($Uninstall) { $command = 'uninstall' }
        if (-not $DryRun) {
            $logs = Join-Path $engine 'logs'
            $null = New-Item -ItemType Directory -Force -Path $logs
            $S.Log = Join-Path $logs ("{0}-{1}.log" -f $command, (Get-Date -Format 'yyyyMMdd-HHmmss'))
            [IO.File]::WriteAllText($S.Log, '', $S.Utf8)
        }
        if ($chosen) {
            $mode = ' (chosen)'
        } elseif ($resolved.Source -eq 'default') {
            $mode = ' (default)'
        } else {
            $mode = " (from $($resolved.Source))"
        }
        if ($sandbox) { $mode += ' (sandbox)' }
        if ($DryRun) { $mode += ' (dry run: nothing is written)' }
        Write-WncLine "WhyNot Cut bootstrap: $command on win-x64; engine home $engine$mode"

        $env:UV_PYTHON_INSTALL_DIR = Join-Path $engine 'python'
        $env:UV_CACHE_DIR = Join-Path $engine 'cache\uv'
        $env:UV_NO_CONFIG = '1'
        $env:UV_PYTHON_PREFERENCE = 'only-managed'
        $env:UV_NO_MODIFY_PATH = '1'
        $uvExe = Join-Path $engine 'bin\uv.exe'
        $py = $null
        if ($Uninstall) {
            $probe = $uvExe
            if ($testUv) { $probe = $testUv }
            $py = Find-WncEnginePython -Uv $probe -Version $pyVer -Engine $engine
        }

        # == uv ==
        Write-WncStep 'uv'
        $haveUv = $false
        if ($py) {
            Write-WncLine "uninstall: the engine's own Python is there; uv and Python are not downloaded"
        } elseif (Test-WncUv $uvExe $uvVer) {
            $haveUv = $true
            Write-WncLine "uv $uvVer is installed ($uvExe)"
        } elseif ($DryRun) {
            Write-WncLine "dry run: would download uv $uvVer from $uvUrl (sha256 $uvSha) and unpack it to $uvExe"
        } else {
            $archive = Get-WncDownload -Url $uvUrl -Sha $uvSha -Dir (Join-Path $engine 'downloads')
            Install-WncUv -Archive $archive -Kind $uvKind -Version $uvVer -Engine $engine -UvExe $uvExe
            $haveUv = $true
        }
        $uv = $uvExe
        if ($testUv) {
            $uv = $testUv
            Write-WncLine "test hook: WNC_TEST_UV=$testUv stands in for uv"
        }

        # == python ==
        Write-WncStep 'python'
        if ((-not $py) -and ($haveUv -or $testUv)) { $py = Find-WncPython $uv $pyVer }
        if (-not $py) {
            if ($DryRun) {
                Write-WncLine "dry run: would install Python $pyVer with uv into $($env:UV_PYTHON_INSTALL_DIR) (--no-bin --no-registry)"
                $names = $WncStepNames
                if ($Uninstall) { $names = $WncUninstallStepNames }
                Write-WncLine ("dry run: then the installer core would run these steps: " + ($names -join ', '))
                return @{ Code = 0 }
            }
            Write-WncLine "installing Python $pyVer into $($env:UV_PYTHON_INSTALL_DIR)"
            $r = Invoke-WncNative $uv @('python', 'install', $pyVer, '--no-bin', '--no-registry')
            if ($r.Code -ne 0) { throw "uv could not install Python $pyVer (exit $($r.Code)): $(Get-WncTail $r)" }
            $py = Find-WncPython $uv $pyVer
            if (-not $py) { throw "uv installed Python $pyVer but cannot find it" }
        }
        Write-WncLine "Python $pyVer at $py"

        $a = @('-I', '-B', '-X', 'utf8', $core, $command, '--plugin-root', $root, '--uv', $uv, '--python', $py)
        if ($S.Log) { $a += @('--log', $S.Log) }
        if ($sandbox) {
            $a += @('--home', $h)
            if ($chosen -or ((Get-WncNormPath $engine) -ine (Get-WncNormPath (Join-Path $h '.whynot-cut')))) {
                $a += @('--engine-home', $engine)
            }
        } else {
            $a += @('--engine-home', $engine)
        }
        if ($chosen) { $a += '--engine-home-chosen' }
        if ($Model) { $a += @('--model', $Model) }
        if ($Components) { $a += @('--components', $compPath) }
        if ($DryRun) { $a += '--dry-run' }
        if ($Uninstall) {
            if ($Yes) { $a += '--yes' }
        } elseif ($S.Mode -eq 'customise') {
            $a += '--customise'
        } else {
            $a += '--yes'  # the default install is exactly the -Yes path (D-T1)
        }
        if ($skipList.Count -gt 0) { $a += @('--skip', ($skipList -join ',')) }
        if ($ClientsFolder) { $a += @('--clients-folder', (Get-WncFullPath $ClientsFolder)) }
        if ($Language) { $a += @('--language', $Language) }
        if ($Channel) { $a += @('--channel', $Channel) }
        if ($Uninstall -and $RemoveEngine) { $a += '--remove-engine' }
        if ($Uninstall -and $RemoveModels) { $a += '--remove-models' }
        Write-WncLog 'INFO' ("bootstrap: running the installer core: $py " + ($a -join ' '))
        return @{ Code = 0; Run = $true; Py = $py; CoreArgs = $a; Engine = $engine; UserHome = $h }
    }

    $saved = @{}
    foreach ($n in $EnvNames) { $saved[$n] = [Environment]::GetEnvironmentVariable($n, 'Process') }
    $oldEncoding = $null
    try {
        $oldEncoding = [Console]::OutputEncoding
        [Console]::OutputEncoding = $S.Utf8  # uv and the core print UTF-8 (paths with Arabic letters)
    } catch {
        $oldEncoding = $null
    }
    try {
        $tls12 = [Net.SecurityProtocolType]::Tls12
        [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor $tls12
        $prep = Initialize-WncBootstrap
        if ($prep.Code -eq 0 -and $prep.ContainsKey('Run')) {
            $py = $prep.Py
            $coreArgs = ConvertTo-WncNativeArgument $prep.CoreArgs
            & $py @coreArgs
            $S.Code = $LASTEXITCODE
            if ($Uninstall -and $RemoveEngine -and (-not $DryRun)) {
                $S.Log = $null  # it went with logs\
                Invoke-WncDeferredDelete -Engine $prep.Engine -UserHome $prep.UserHome
            }
        } else {
            $S.Code = $prep.Code
        }
    } catch {
        $msg = "WhyNot Cut bootstrap failed at step $($S.Step): $($_.Exception.Message)"
        Write-WncLog 'ERROR' $msg
        if ($S.Log) { $msg += " Log: $($S.Log)" }
        Write-Host "ERROR: $msg"
        $S.Code = 3
    } finally {
        foreach ($n in $EnvNames) { [Environment]::SetEnvironmentVariable($n, $saved[$n], 'Process') }
        if ($null -ne $oldEncoding) {
            try { [Console]::OutputEncoding = $oldEncoding } catch { Write-Verbose 'console encoding not restored' }
        }
    }
    $global:LASTEXITCODE = $S.Code
}
