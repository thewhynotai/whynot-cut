# WhyNot Cut installer for Windows 10/11 x64 - per user, no admin rights.
#
# From the extracted WhyNot Cut zip (PowerShell, in the extracted folder):
#     powershell -ExecutionPolicy Bypass -File whynot-cut\installer\install.ps1
# One line (once the files are hosted, H3):
#     irm https://thewhynot.ai/install.ps1 | iex
# With options, one line:
#     & ([scriptblock]::Create((irm https://thewhynot.ai/install.ps1))) -Source <zip or https url> -SourceSha256 <hex>
#
# Where the plugin comes from: this script's folder's parent when it holds setup\components.json (the zip layout
# whynot-cut\installer\install.ps1). Otherwise (irm | iex, or this file copied alone) the release zip given by -Source
# (a path or an https URL) and -SourceSha256 is copied or downloaded into ~\.whynot-cut\downloads\release-<sha8>\,
# verified, and extracted; its whynot-cut-marketplace\whynot-cut folder is the plugin. Without -Source the release
# index is used - until it is hosted (H3) the script says so and stops with exit code 2.
# Then installer\core\bootstrap.ps1 (uv + Python) runs and hands over to the Python installer core. Every option is
# described in installer\README.md. Exit code: the installer's (0 done, 1 a step failed, 2 cannot start, 3 a download
# or bootstrap step failed).
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
    [string]$Source,
    [string]$SourceSha256
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

    function Get-WncFullPath([string]$Path) {
        return $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($Path)
    }

    function Get-WncArabic([string]$Base64) {
        return [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($Base64))
    }

    function Get-WncEngineHome {
        if ($SandboxHome) { return Join-Path (Get-WncFullPath $SandboxHome) '.whynot-cut' }
        if ($env:WHYNOT_HOME) { return Get-WncFullPath $env:WHYNOT_HOME }
        $h = $env:USERPROFILE
        if (-not $h) { $h = $env:HOME }
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
        $dir = Join-Path (Get-WncEngineHome) ('downloads\release-' + $sha.Substring(0, 8))
        if ($DryRun) {
            Write-Host "dry run: would fetch $src, check its sha256 $sha, extract it into $dir and run its installer"
            return @{ Code = 0 }
        }
        $zip = Join-Path $dir $name
        $x = Join-Path $dir 'x'
        $plugin = Join-Path $x 'whynot-cut-marketplace\whynot-cut'
        $ready = (Test-Path -LiteralPath $zip -PathType Leaf) -and ((Get-WncSha $zip) -eq $sha)
        if (-not $ready) {
            $null = New-Item -ItemType Directory -Force -Path $dir
            $part = "$zip.part"
            if (Test-Path -LiteralPath $part) { Remove-Item -LiteralPath $part -Force }
            Write-Host "fetching $src"
            if ($isUrl) {
                Invoke-WebRequest -UseBasicParsing -Uri $src -OutFile $part
            } else {
                Copy-Item -LiteralPath $src -Destination $part -Force
            }
            $got = Get-WncSha $part
            if ($got -ne $sha) {
                Remove-Item -LiteralPath $part -Force
                throw "sha256 mismatch for $name (expected $sha, got $got); the file was deleted"
            }
            Move-Item -LiteralPath $part -Destination $zip -Force
            if (Test-Path -LiteralPath $x) { Remove-Item -LiteralPath $x -Recurse -Force }
        }
        Write-Host "verified $name (sha256 ok)"
        if (-not (Test-Path -LiteralPath (Join-Path $plugin 'setup\components.json') -PathType Leaf)) {
            $tmp = "$x.tmp"
            if (Test-Path -LiteralPath $tmp) { Remove-Item -LiteralPath $tmp -Recurse -Force }
            if (Test-Path -LiteralPath $x) { Remove-Item -LiteralPath $x -Recurse -Force }
            Expand-Archive -LiteralPath $zip -DestinationPath $tmp -Force
            Rename-Item -LiteralPath $tmp -NewName 'x'
        }
        if (-not (Test-Path -LiteralPath (Join-Path $plugin 'installer\core\bootstrap.ps1') -PathType Leaf)) {
            throw "$name is not a WhyNot Cut release zip (no whynot-cut-marketplace\whynot-cut\installer)"
        }
        Write-Host "WhyNot Cut files: $plugin"
        return @{ Code = 0; Root = $plugin }
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
        if ($WncScriptPath) {
            $candidate = Split-Path (Split-Path $WncScriptPath -Parent) -Parent
            if (Test-Path -LiteralPath (Join-Path $candidate 'setup\components.json') -PathType Leaf) { $root = $candidate }
        }
        if (-not $root) {
            try {
                $release = Get-WncRelease
                $code = $release.Code
                if ($release.ContainsKey('Root')) { $root = $release.Root }
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
            & $block @bootArgs
            $code = $LASTEXITCODE
        }
    } finally {
        if ($null -ne $oldEncoding) {
            try { [Console]::OutputEncoding = $oldEncoding } catch { Write-Verbose 'console encoding not restored' }
        }
    }
    if ($WncScriptPath) { exit $code }
    $global:LASTEXITCODE = $code
}
