$ErrorActionPreference = 'Stop'
$workspace = (Resolve-Path '.').Path
$bootstrap = Join-Path $workspace '.gsd\tuning-reports\2026-11-18-evidence\windows-bootstrap-under-test.ps1'
$testRoot = Join-Path $workspace 'logs\gsd-tune-20261118-bootstrap-copies'
if (Test-Path -LiteralPath $testRoot) { throw 'Refusing to overwrite an existing test fixture' }
New-Item -ItemType Directory -Path $testRoot | Out-Null
$sourceExe = Join-Path $workspace '.gsd\gsd.exe'
$sourceBundle = Join-Path $workspace '.gsd\gsd-assets-v1.6.0.zip'
$sourceManifest = Join-Path $workspace '.gsd\runtime-manifest.json'
$expectedRelease = 'https://github.com/softwaresalt/GSD/releases/download/v1.6.0'
$global:GsdTuneDownloads = [Collections.Generic.List[string]]::new()
$global:GsdTuneSources = @{
    "$expectedRelease/gsd-windows-amd64.exe" = $sourceExe
    "$expectedRelease/gsd-assets.zip" = $sourceBundle
}

# Offline downloader stub: only the two approved URLs are accepted. Successful
# fixture downloads copy verified local bytes into new files, never hardlinks.
function Invoke-WebRequest {
    param([string]$Uri, [string]$OutFile)
    $global:GsdTuneDownloads.Add($Uri)
    if (-not $global:GsdTuneSources.ContainsKey($Uri)) { throw "Unapproved download URL: $Uri" }
    if (Test-Path -LiteralPath $OutFile) { throw "Refusing to overwrite fixture: $OutFile" }
    Copy-Item -LiteralPath $global:GsdTuneSources[$Uri] -Destination $OutFile
}

$results = @()
foreach ($case in @('cached', 'fresh', 'bad-exe', 'bad-alias', 'bad-manifest')) {
    $caseRoot = Join-Path $testRoot $case
    $tools = Join-Path $caseRoot '.gsd'
    New-Item -ItemType Directory -Path $tools | Out-Null
    if ($case -ne 'fresh') {
        foreach ($asset in @(
            @{ Name = 'gsd.exe'; Source = $sourceExe },
            @{ Name = 'gsd-assets-v1.6.0.zip'; Source = $sourceBundle },
            @{ Name = 'gsd-assets.zip'; Source = $sourceBundle }
        )) {
            $destination = Join-Path $tools $asset.Name
            if (($case -eq 'bad-exe' -and $asset.Name -eq 'gsd.exe') -or
                ($case -eq 'bad-alias' -and $asset.Name -eq 'gsd-assets.zip')) {
                [IO.File]::WriteAllText($destination, 'untrusted fixture')
            } else {
                Copy-Item -LiteralPath $asset.Source -Destination $destination
            }
        }
        if ($case -eq 'bad-manifest') {
            [IO.File]::WriteAllText((Join-Path $tools 'runtime-manifest.json'), '{"active_version":"0.0.0"}')
        } else {
            Copy-Item -LiteralPath $sourceManifest -Destination (Join-Path $tools 'runtime-manifest.json')
        }
    }
    $env:GITHUB_PATH = Join-Path $caseRoot 'github-path.txt'
    $global:GsdTuneDownloads.Clear()
    $observedError = $null
    Push-Location -LiteralPath $caseRoot
    try {
        & $bootstrap
    } catch {
        $observedError = $_.Exception.Message
    } finally {
        Pop-Location
    }
    $expectedFailure = switch ($case) {
        'bad-exe' { 'SHA-256 mismatch: gsd.exe' }
        'bad-alias' { 'SHA-256 mismatch: gsd-assets.zip' }
        'bad-manifest' { 'Existing runtime-manifest.json does not match the pinned Windows runtime' }
        default { $null }
    }
    if ($observedError -ne $expectedFailure) {
        throw "Unexpected result for ${case}: $observedError (expected $expectedFailure)"
    }
    if ($null -eq $expectedFailure) {
        if (-not (Test-Path -LiteralPath $env:GITHUB_PATH)) { throw "PATH not exported for $case" }
        $manifest = Get-Content -LiteralPath (Join-Path $tools 'runtime-manifest.json') -Raw | ConvertFrom-Json
        if ($manifest.active_version -ne '1.6.0') { throw "Manifest version mismatch for $case" }
        if ((Get-Content -LiteralPath $env:GITHUB_PATH).Trim() -ne $tools) { throw "PATH mismatch for $case" }
    } elseif (Test-Path -LiteralPath $env:GITHUB_PATH) {
        throw "An unverified runtime exported PATH for $case"
    }
    $expectedDownloads = if ($case -eq 'fresh') { 2 } else { 0 }
    if ($global:GsdTuneDownloads.Count -ne $expectedDownloads) { throw "Unexpected download attempts for $case" }
    $results += @{
        case = $case
        passed = $true
        expected_error = $expectedFailure
        offline_download_calls = $global:GsdTuneDownloads.ToArray()
    }
}
$record = @{
    verified_at = [DateTime]::UtcNow.ToString("yyyy-MM-ddTHH:mm:ss'Z'")
    bootstrap_sha256 = (Get-FileHash -LiteralPath $bootstrap -Algorithm SHA256).Hash.ToLowerInvariant()
    network_calls = 0
    test_root = $testRoot
    cases = $results
    hosted_ci_executed = $false
}
$json = ($record | ConvertTo-Json -Depth 6) -replace "`r`n", "`n"
[IO.File]::WriteAllText(
    (Join-Path $workspace '.gsd\tuning-reports\2026-11-18-evidence\windows-bootstrap-test-results.json'),
    $json + "`n",
    [Text.UTF8Encoding]::new($false)
)
Write-Output $json
