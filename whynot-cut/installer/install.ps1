# WhyNot Cut installer for Windows 10/11 x64 - per user, no admin rights.
#
# From the extracted WhyNot Cut zip (PowerShell, in the extracted folder):
#     powershell -ExecutionPolicy Bypass -File whynot-cut\installer\install.ps1
# One line (once the files are hosted, H3):
#     irm https://dl.thewhynot.ai/install.ps1 | iex
# With options, one line:
#     & ([scriptblock]::Create((irm https://dl.thewhynot.ai/install.ps1))) -Source <zip or https url> -SourceSha256 <hex>
#
# Where the plugin comes from: this script's folder's parent when it holds setup\components.json (the zip layout
# whynot-cut\installer\install.ps1). Otherwise (irm | iex, or this file copied alone) the release zip given by -Source
# (a path or an https URL) and -SourceSha256 is copied or downloaded into a fresh folder of this run under the OS temp
# dir (an earlier run's cached copy of the same zip is read instead of fetched), verified, and extracted; its
# whynot-cut-marketplace\whynot-cut folder is the plugin. Nothing is written into the engine home before the bootstrap
# has checked it (fix round 6, R5-5): an install keeps the release in <engine home>\downloads\release-<sha8>\ once every
# check passed (-ReleaseStage); the temporary folder is deleted when the run ends (a failure there is only a warning).
# Without -Source the release index is used - until it is hosted (H3) the script says so and stops with exit code 2.
# Then installer\core\bootstrap.ps1 (uv + Python) runs and hands over to the Python installer core. Every option is
# described in installer\README.md. Exit code: the installer's (0 done, 1 a step failed, 2 cannot start, 3 a download
# or bootstrap step failed).
# It asks no question by default (D-T1): it says how much it installs and counts down 10 seconds ("Press C to
# customise"); C or -Customise asks the questions (location, model, language, clients folder), every answer
# preselected; -Yes skips the countdown too.
# ASCII only: Windows PowerShell 5.1 reads a file without a BOM as ANSI (the Arabic line is decoded from base64).
[Diagnostics.CodeAnalysis.SuppressMessageAttribute('PSReviewUnusedParameter', '',
    Justification = 'The parameters are read inside the & { } block below, which the analyzer does not follow.')]
[Diagnostics.CodeAnalysis.SuppressMessageAttribute('PSAvoidUsingWriteHost', '',
    Justification = 'Console lines for the editor; pipeline output would be captured and hide the core output.')]
[CmdletBinding()]
param(
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
    [string]$Source,
    [string]$SourceSha256,
    [Alias('Customize')][switch]$Customise
)

# Filled by the release tool once the files are hosted (H3). The index is JSON:
#   { "stable": { "url": "https://.../WhyNotCut-<version>.zip", "sha256": "<64 hex>" }, "beta": { ... } }
$WncReleaseIndexUrl = '<release>'
$WncScriptPath = $PSCommandPath  # empty under `irm | iex`

& {
    Set-StrictMode -Version 2.0
    $ErrorActionPreference = 'Stop'
    $ProgressPreference = 'SilentlyContinue'
    $tls12 = [Net.SecurityProtocolType]::Tls12
    [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor $tls12
    $W = @{ Temp = $null }  # this run's release stage under the OS temp dir (-Source), deleted at the end

    function Get-WncFullPath([string]$Path) {
        return $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($Path)
    }

    function Get-WncArabic([string]$Base64) {
        return [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($Base64))
    }

    function Get-WncEngineHome {
        # where an earlier run cached the release zip (-Source mode, before any plugin file exists; only READ here -
        # fix round 6, R5-5): the engine home as the bootstrap will find it - -EngineHome (its WhyNotCut subfolder
        # when it holds other files or is the user folder / Desktop / Documents / Downloads, as bootstrap.ps1
        # Get-WncEnginePlace does), else the engine-home variables (not in a sandbox), the pointer's engine_home, our
        # settings.json pluginConfigs option, else ~\.whynot-cut. A rare disagreement with the bootstrap only means
        # the zip is fetched again.
        $h = $env:USERPROFILE
        if (-not $h) { $h = $env:HOME }
        if ($SandboxHome) { $h = Get-WncFullPath $SandboxHome }
        if ($EngineHome) {
            $e = Get-WncFullPath $EngineHome
            $mark = @('state.json', 'current', 'bin\uv.exe', 'bin\uv') |
                Where-Object { Test-Path -LiteralPath (Join-Path $e $_) -PathType Leaf }
            $roots = @($h) + @('Desktop', 'Documents', 'Downloads' | ForEach-Object { Join-Path $h $_ })
            $isRoot = @($roots | Where-Object { $_.TrimEnd([char]92) -ieq $e.TrimEnd([char]92) }).Count -gt 0
            $full = (Test-Path -LiteralPath $e -PathType Container) -and
                (@(Get-ChildItem -LiteralPath $e -Force -ErrorAction SilentlyContinue).Count -gt 0)
            if ((-not $mark) -and ($isRoot -or $full)) { return Join-Path $e 'WhyNotCut' }
            return $e
        }
        if (-not $SandboxHome) {
            foreach ($n in @('WHYNOT_HOME', 'CLAUDE_PLUGIN_OPTION_ENGINE_HOME', 'REEL_HOME',
                    'CLAUDE_PLUGIN_OPTION_REEL_HOME', 'NH_ENV_DIR')) {
                $v = [Environment]::GetEnvironmentVariable($n, 'Process')
                if ($v) { return Get-WncFullPath $v }
            }
        }
        try {
            $o = [IO.File]::ReadAllText((Join-Path $h '.whynot-cut\plugin-options.json'), [Text.Encoding]::UTF8) |
                ConvertFrom-Json
            if ($o.engine_home -is [string]) {
                if ($o.engine_home) { return Get-WncFullPath $o.engine_home }
                return Join-Path $h '.whynot-cut'
            }
        } catch {
            Write-Verbose "no pointer: $($_.Exception.Message)"
        }
        try {
            $cfg = Join-Path $h '.claude'
            if ($env:CLAUDE_CONFIG_DIR -and (-not $SandboxHome)) { $cfg = $env:CLAUDE_CONFIG_DIR }
            $s = [IO.File]::ReadAllText((Join-Path $cfg 'settings.json'), [Text.Encoding]::UTF8) | ConvertFrom-Json
            $v = $s.pluginConfigs.'whynot-cut@thewhynot-ai'.options.engine_home
            if ($v -is [string] -and $v) { return Get-WncFullPath $v }
        } catch {
            Write-Verbose "no saved engine home in settings.json: $($_.Exception.Message)"
        }
        return Join-Path $h '.whynot-cut'
    }

    function Get-WncSha([string]$Path) {
        return (Get-FileHash -Algorithm SHA256 -LiteralPath $Path).Hash.ToLowerInvariant()
    }

    function Get-WncRelease {
        # @{ Code; Root }: the plugin folder of the release zip, fetched, verified and extracted
        $src = $Source
        $sha = $SourceSha256
        if (-not $src) {
            if ($WncReleaseIndexUrl.StartsWith('<release')) {
                Write-Host ('WhyNot Cut hosting is not ready yet (H3): download the WhyNot Cut zip, extract it, then ' +
                    'run installer\install.ps1 (powershell -ExecutionPolicy Bypass -File whynot-cut\installer\install.ps1).')
                Write-Host (Get-WncArabic ('2KfZhNin2LPYqti22KfZgdipINi62YrYsSDYrNin2YfYstipINio2LnYryAoSDMpOiDZhtiy2ZHZhCDZhdmE2YEgV2h5Tm90IEN1' +
                        'dCDYqNi12YrYutipIHppcNiMINmB2YPZkdmH2Iwg2KvZhSDYtNi62ZHZhCBpbnN0YWxsZXJcaW5zdGFsbC5wczE='))
                return @{ Code = 2 }
            }
            $ch = $Channel
            if (-not $ch) { $ch = 'stable' }
            $index = Invoke-RestMethod -UseBasicParsing -Uri $WncReleaseIndexUrl
            $entry = $index.$ch
            $src = [string]$entry.url
            $sha = [string]$entry.sha256
            Write-Host "WhyNot Cut $ch release: $src"
        }
        if ($sha -notmatch '^[0-9a-fA-F]{64}$') {
            Write-Host 'ERROR: -Source needs -SourceSha256 <the 64-character sha256 of the zip>.'
            return @{ Code = 2 }
        }
        $sha = $sha.ToLowerInvariant()
        $isUrl = $src -match '^https?://'
        if ($src -match '^http://' -and $src -notmatch '^http://(127\.0\.0\.1|localhost)[:/]') {
            Write-Host "ERROR: -Source must be a file or an https:// URL: $src"
            return @{ Code = 2 }
        }
        if ($isUrl) {
            $name = [Uri]::UnescapeDataString(([Uri]$src).AbsolutePath.Split('/')[-1])
        } else {
            $src = Get-WncFullPath $src
            $name = Split-Path $src -Leaf
        }
        if (-not $name) { $name = 'WhyNotCut.zip' }
        $rel = 'release-' + $sha.Substring(0, 8)
        if ($DryRun) {
            Write-Host "dry run: would fetch $src, check its sha256 $sha, extract it into a temporary folder and run its installer"
            return @{ Code = 0 }
        }
        # fix round 6 (R5-5): nothing is written into the engine home before the bootstrap has checked it - the zip is
        # fetched, verified and extracted in a fresh folder of this run under the OS temp dir (deleted when the run
        # ends); the bootstrap keeps it in <engine home>\downloads\release-<sha8> only once every check has passed
        $W.Temp = Join-Path ([IO.Path]::GetTempPath()) ('WhyNotCut-release-' + [Guid]::NewGuid().ToString('N').Substring(0, 12))
        $dir = Join-Path $W.Temp $rel
        $null = New-Item -ItemType Directory -Force -Path $dir
        $zip = Join-Path $dir $name
        $x = Join-Path $dir 'x'
        $plugin = Join-Path $x 'whynot-cut-marketplace\whynot-cut'
        $part = "$zip.part"
        # an earlier run's cache of the same zip is read (never written here), else the zip is fetched
        $cached = Join-Path (Get-WncEngineHome) "downloads\$rel\$name"
        if ((Test-Path -LiteralPath $cached -PathType Leaf) -and ((Get-WncSha $cached) -eq $sha)) {
            Copy-Item -LiteralPath $cached -Destination $part -Force
        } else {
            Write-Host "fetching $src"
            if ($isUrl) {
                Invoke-WebRequest -UseBasicParsing -Uri $src -OutFile $part
            } else {
                Copy-Item -LiteralPath $src -Destination $part -Force
            }
        }
        $got = Get-WncSha $part
        if ($got -ne $sha) {
            Remove-Item -LiteralPath $part -Force
            throw "sha256 mismatch for $name (expected $sha, got $got); the file was deleted"
        }
        Move-Item -LiteralPath $part -Destination $zip -Force
        Write-Host "verified $name (sha256 ok)"
        Expand-Archive -LiteralPath $zip -DestinationPath $x -Force
        if (-not (Test-Path -LiteralPath (Join-Path $plugin 'installer\core\bootstrap.ps1') -PathType Leaf)) {
            throw "$name is not a WhyNot Cut release zip (no whynot-cut-marketplace\whynot-cut\installer)"
        }
        Write-Host "WhyNot Cut files: $plugin"
        return @{ Code = 0; Root = $plugin; Stage = $dir }
    }

    function Remove-WncTree([string]$Path) {
        # never Remove-Item -Recurse (Windows PowerShell 5.1 follows junctions): a link is removed as a link, its
        # target never entered; read-only files are cleared first (bootstrap.ps1 Invoke-WncDeleteTree)
        $attr = [IO.File]::GetAttributes($Path)
        if (($attr -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
            if ([IO.Directory]::Exists($Path)) { [IO.Directory]::Delete($Path, $false) } else { [IO.File]::Delete($Path) }
            return
        }
        if ([IO.Directory]::Exists($Path)) {
            foreach ($child in [IO.Directory]::GetFileSystemEntries($Path)) { Remove-WncTree $child }
            [IO.Directory]::Delete($Path, $false)
        } else {
            [IO.File]::SetAttributes($Path, [IO.FileAttributes]::Normal)
            [IO.File]::Delete($Path)
        }
    }

    function Remove-WncStage {
        # the per-run release stage (fix round 6, R5-5): deleted when the run ends; a failure is only a warning
        if ((-not $W.Temp) -or (-not (Test-Path -LiteralPath $W.Temp))) { return }
        try {
            Remove-WncTree $W.Temp
        } catch {
            Write-Host "WARNING: could not delete the temporary folder $($W.Temp) ($($_.Exception.Message)); delete it yourself"
        }
    }

    # UTF-8 on the console from the first line on (uv, the core and the Arabic lines); put back at the end
    $oldEncoding = $null
    try {
        $oldEncoding = [Console]::OutputEncoding
        [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding $false
    } catch {
        $oldEncoding = $null
    }
    $code = 3
    try {
        $code = 0
        $root = $null
        $stage = $null
        if ($WncScriptPath) {
            $candidate = Split-Path (Split-Path $WncScriptPath -Parent) -Parent
            if (Test-Path -LiteralPath (Join-Path $candidate 'setup\components.json') -PathType Leaf) { $root = $candidate }
        }
        if (-not $root) {
            try {
                $release = Get-WncRelease
                $code = $release.Code
                if ($release.ContainsKey('Root')) { $root = $release.Root }
                if ($release.ContainsKey('Stage')) { $stage = $release.Stage }
            } catch {
                Write-Host "ERROR: WhyNot Cut could not get its files: $($_.Exception.Message)"
                $code = 3
            }
        }
        if ($root -and $code -eq 0) {
            $bootstrap = Join-Path $root 'installer\core\bootstrap.ps1'
            # loaded as a script block: runs under any execution policy, and its own `exit`-free code keeps an
            # `irm | iex` session open
            $block = [scriptblock]::Create([IO.File]::ReadAllText($bootstrap))
            $bootArgs = @{ PluginRoot = $root }
            if ($SandboxHome) { $bootArgs.SandboxHome = $SandboxHome }
            if ($DryRun) { $bootArgs.DryRun = $true }
            if ($Yes) { $bootArgs.Yes = $true }
            if ($ClientsFolder) { $bootArgs.ClientsFolder = $ClientsFolder }
            if ($Language) { $bootArgs.Language = $Language }
            if ($Channel) { $bootArgs.Channel = $Channel }
            if ($Components) { $bootArgs.Components = $Components }
            if ($Skip) { $bootArgs.Skip = $Skip }
            if ($Uninstall) { $bootArgs.Uninstall = $true }
            if ($RemoveEngine) { $bootArgs.RemoveEngine = $true }
            if ($RemoveModels) { $bootArgs.RemoveModels = $true }
            if ($EngineHome) { $bootArgs.EngineHome = $EngineHome }
            if ($Model) { $bootArgs.Model = $Model }
            if ($Customise) { $bootArgs.Customise = $true }
            if ($stage) { $bootArgs.ReleaseStage = $stage }
            & $block @bootArgs
            $code = $LASTEXITCODE
        }
    } finally {
        Remove-WncStage
        if ($null -ne $oldEncoding) {
            try { [Console]::OutputEncoding = $oldEncoding } catch { Write-Verbose 'console encoding not restored' }
        }
    }
    if ($WncScriptPath) { exit $code }
    $global:LASTEXITCODE = $code
}
