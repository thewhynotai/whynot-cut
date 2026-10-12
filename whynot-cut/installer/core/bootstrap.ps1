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
# Log: ~\.whynot-cut\logs\install-YYYYmmdd-HHMMSS.log (uninstall-... for -Uninstall), shared with the core (--log).
# Exit code (in $LASTEXITCODE): the core's; 2 = cannot start (not Windows x64, unreadable components.json, missing
# core); 3 = a bootstrap step failed (download, sha256, uv, python), with a one-line message and the log path.
# -DryRun: writes nothing (no log, no folder). Runs the core's dry run only when uv and Python are already there (or
# WNC_TEST_UV is set); otherwise it names the steps that would follow.
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
            if ($env:WHYNOT_HOME) { $engine = Get-WncFullPath $env:WHYNOT_HOME } else { $engine = Join-Path $h '.whynot-cut' }
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
        $mode = ''
        if ($sandbox) { $mode = ' (sandbox)' }
        if ($DryRun) { $mode += ' (dry run: nothing is written)' }
        Write-WncLine "WhyNot Cut bootstrap: $command on win-x64; engine home $engine$mode"

        # == uv ==
        Write-WncStep 'uv'
        $uvExe = Join-Path $engine 'bin\uv.exe'
        $haveUv = Test-WncUv $uvExe $uvVer
        if ($haveUv) {
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
        $env:UV_PYTHON_INSTALL_DIR = Join-Path $engine 'python'
        $env:UV_CACHE_DIR = Join-Path $engine 'cache\uv'
        $env:UV_NO_CONFIG = '1'
        $env:UV_PYTHON_PREFERENCE = 'only-managed'
        $env:UV_NO_MODIFY_PATH = '1'
        $py = $null
        if ($haveUv -or $testUv) { $py = Find-WncPython $uv $pyVer }
        if (-not $py) {
            if ($DryRun) {
                Write-WncLine "dry run: would install Python $pyVer with uv into $($env:UV_PYTHON_INSTALL_DIR) (--no-bin --no-registry)"
                Write-WncLine ("dry run: then the installer core would run these steps: " + ($WncStepNames -join ', '))
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
        if ($sandbox) { $a += @('--home', $h) }
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
        return @{ Code = 0; Run = $true; Py = $py; CoreArgs = $a }
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
