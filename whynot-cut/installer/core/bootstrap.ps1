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
# link), and the engine home itself only when it is then empty; then the list file. The log went with logs\, so the
# summary is on the console only. The newest engine Python is chosen by version number (3.12.15 before 3.12.9).
# Log: ~\.whynot-cut\logs\install-YYYYmmdd-HHMMSS.log (uninstall-... for -Uninstall), shared with the core (--log).
# Exit code (in $LASTEXITCODE): the core's; 2 = cannot start (not Windows x64, unreadable components.json, missing
# core); 3 = a bootstrap step failed (download, sha256, uv, python), with a one-line message and the log path.
# -DryRun: writes nothing (no log, no folder). Runs the core's dry run only when uv and Python are already there (or
# WNC_TEST_UV is set); otherwise it names the steps that would follow.
# Engine home (outside a sandbox): resolved exactly like the engine (Resolve-WncEngineHome: WHYNOT_HOME and the other
# engine-home variables, else the plugin option engine_home from ~\.whynot-cut\plugin-options.json, else from
# settings.json pluginConfigs, else ~\.whynot-cut) BEFORE anything is downloaded, so uv, Python, the log and every
# later step land in that one folder; it is passed to the core as --engine-home, and the core stops with 2 if its own
# resolution (wnc_installer.base.resolve_engine_home) disagrees.
# Sandbox (-Home <dir>): HOME, USERPROFILE, APPDATA, LOCALAPPDATA, CLAUDE_CONFIG_DIR and WHYNOT_HOME point into <dir>
# before anything is downloaded (as wnc_installer.base.Paths.child_env does), and --home is passed on. Only then is
# the test hook WNC_TEST_UV honoured: a uv stand-in used for `python install/find` after the real archive was still
# downloaded and verified. Every environment variable it sets is restored when it ends (the script may run inside the
# editor's own PowerShell session through `irm | iex`), so is the console encoding.
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
    [switch]$RemoveModels
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
    $S = @{ Log = $null; Step = 'start'; Code = 0; Utf8 = (New-Object System.Text.UTF8Encoding $false) }
    $EnvNames = @('HOME', 'USERPROFILE', 'APPDATA', 'LOCALAPPDATA', 'CLAUDE_CONFIG_DIR', 'WHYNOT_HOME',
        'UV_PYTHON_INSTALL_DIR', 'UV_CACHE_DIR', 'UV_NO_CONFIG', 'UV_PYTHON_PREFERENCE', 'UV_NO_MODIFY_PATH')

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

    function Invoke-WncDeferredDelete([string]$Engine) {
        # after `uninstall --remove-engine`: the paths the core listed in <engine>\.delete-after-exit (see the header)
        $list = Join-Path $Engine '.delete-after-exit'
        if (-not [IO.File]::Exists($list)) { return }
        $root = [IO.Path]::GetFullPath($Engine).TrimEnd([char]92)
        if (Test-WncReparse $root) {
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
            if ($homeToo -and (-not $failed) -and [IO.Directory]::Exists($root) -and
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

    function Resolve-WncEngineHome([string]$UserHome) {
        # outside a sandbox: the engine home exactly as the engine resolves it (engine\reel\lib\plat.py engine_home;
        # the core's wnc_installer.base.resolve_engine_home is the same): the first variable that is set, else the
        # plugin option engine_home from the pointer file (~\.whynot-cut\plugin-options.json or WHYNOT_OPTIONS_FILE,
        # when it is a JSON object with an engine_home string; "" = not set), else from settings.json
        # pluginConfigs (whynot-cut@thewhynot-ai, else the first other whynot-cut@* entry with options), else
        # ~\.whynot-cut. @{ Path; Source }; Source is named like the core's (env:<NAME>, pointer:<file>,
        # settings:<file> <key>, default). uv and Python are placed there, and the core checks it (--engine-home).
        $names = @('WHYNOT_HOME', 'CLAUDE_PLUGIN_OPTION_ENGINE_HOME', 'REEL_HOME', 'CLAUDE_PLUGIN_OPTION_REEL_HOME',
            'NH_ENV_DIR')
        foreach ($n in $names) {
            $v = [Environment]::GetEnvironmentVariable($n, 'Process')
            if ($v) {
                $p = ConvertTo-WncHomePath -Value $v -UserHome $UserHome -Saved $false
                return @{ Path = $p; Source = "env:$n" }
            }
        }
        $pointer = Join-Path $UserHome '.whynot-cut\plugin-options.json'
        if ($env:WHYNOT_OPTIONS_FILE) {
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
            if ($env:CLAUDE_CONFIG_DIR) {
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

    function Initialize-WncBootstrap {
        # @{ Code; Run; Py; CoreArgs } - every check and download; the core itself runs outside, uncaptured
        $arch = $env:PROCESSOR_ARCHITEW6432
        if (-not $arch) { $arch = $env:PROCESSOR_ARCHITECTURE }
        if ($arch -ne 'AMD64') {
            Write-Host "WhyNot Cut runs on Windows x64 (and macOS); this PC is $arch."
            return @{ Code = 2 }
        }
        $root = Get-WncFullPath $PluginRoot
        $sandbox = [bool]$SandboxHome
        if ($sandbox) {
            $h = Get-WncFullPath $SandboxHome
            $engine = Join-Path $h '.whynot-cut'
            $env:HOME = $h
            $env:USERPROFILE = $h
            $env:APPDATA = Join-Path $h 'AppData\Roaming'
            $env:LOCALAPPDATA = Join-Path $h 'AppData\Local'
            $env:CLAUDE_CONFIG_DIR = Join-Path $h '.claude'
            $env:WHYNOT_HOME = $engine
        } else {
            $h = $env:USERPROFILE
            if (-not $h) { $h = $env:HOME }
            $resolved = Resolve-WncEngineHome $h
            $engine = Get-WncFullPath $resolved.Path
        }
        $testUv = $null
        if ($sandbox -and $env:WNC_TEST_UV) { $testUv = $env:WNC_TEST_UV }

        $compPath = Join-Path $root 'setup\components.json'
        if ($Components) { $compPath = Get-WncFullPath $Components }
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
        if ($sandbox) { $mode = ' (sandbox)' } else { $mode = " (from $($resolved.Source))" }
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
        if ($sandbox) { $a += @('--home', $h) } else { $a += @('--engine-home', $engine) }
        if ($Components) { $a += @('--components', $compPath) }
        if ($DryRun) { $a += '--dry-run' }
        if ($Yes) { $a += '--yes' }
        $skipList = @($Skip | Where-Object { $_ } | ForEach-Object { $_ -split ',' } | Where-Object { $_.Trim() } |
            ForEach-Object { $_.Trim() })
        if ($skipList.Count -gt 0) { $a += @('--skip', ($skipList -join ',')) }
        if ($ClientsFolder) { $a += @('--clients-folder', (Get-WncFullPath $ClientsFolder)) }
        if ($Language) { $a += @('--language', $Language) }
        if ($Channel) { $a += @('--channel', $Channel) }
        if ($Uninstall -and $RemoveEngine) { $a += '--remove-engine' }
        if ($Uninstall -and $RemoveModels) { $a += '--remove-models' }
        Write-WncLog 'INFO' ("bootstrap: running the installer core: $py " + ($a -join ' '))
        return @{ Code = 0; Run = $true; Py = $py; CoreArgs = $a; Engine = $engine }
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
                Invoke-WncDeferredDelete $prep.Engine
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
