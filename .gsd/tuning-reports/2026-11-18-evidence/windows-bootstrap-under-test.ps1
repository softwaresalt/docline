$ErrorActionPreference = 'Stop'
$version = '1.6.0'
$release = "https://github.com/softwaresalt/GSD/releases/download/v$version"
$toolDir = Join-Path $PWD '.gsd'
New-Item -ItemType Directory -Path $toolDir -Force | Out-Null
$exeHash = 'df8a29d5a9f7f1306a9abe2ca1ae5e314e638ebfa0d9ac8a1ec4524cea27470e'
$bundleHash = 'b170652c9d83786cde8e988ef8d4c9cf47fb7039373383645b2a7ad7d053ebc1'
$assets = @(
  @{ Name = 'gsd.exe'; Asset = 'gsd-windows-amd64.exe'; Hash = $exeHash },
  @{ Name = "gsd-assets-v$version.zip"; Asset = 'gsd-assets.zip'; Hash = $bundleHash }
)
foreach ($asset in $assets) {
  $path = Join-Path $toolDir $asset.Name
  if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
    Invoke-WebRequest -Uri "$release/$($asset.Asset)" -OutFile $path
  }
  if ((Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash -ne $asset.Hash) {
    throw "SHA-256 mismatch: $($asset.Name)"
  }
}
$bundleName = "gsd-assets-v$version.zip"
$compatBundle = Join-Path $toolDir 'gsd-assets.zip'
if (-not (Test-Path -LiteralPath $compatBundle -PathType Leaf)) {
  Copy-Item -LiteralPath (Join-Path $toolDir $bundleName) -Destination $compatBundle
}
if ((Get-FileHash -LiteralPath $compatBundle -Algorithm SHA256).Hash -ne $bundleHash) {
  throw 'SHA-256 mismatch: gsd-assets.zip'
}
$manifestPath = Join-Path $toolDir 'runtime-manifest.json'
if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) {
  $now = [DateTime]::UtcNow.ToString("yyyy-MM-ddTHH:mm:ss'Z'")
  $manifest = @{
    schema_version = '1.0.0'
    last_op_id = "ci-bootstrap-$version"
    active_version = $version
    release_tag = "v$version"
    executable_path = 'gsd.exe'
    executable_sha256 = $exeHash
    bundle_path = $bundleName
    bundle_sha256 = $bundleHash
    installed_bundles = @(@{
      version = $version; path = $bundleName
      sha256 = $bundleHash; installed_at_utc = $now
    })
    updated_at_utc = $now
  }
  [IO.File]::WriteAllText(
    $manifestPath,
    ($manifest | ConvertTo-Json -Depth 5),
    [Text.UTF8Encoding]::new($false)
  )
} else {
  $manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
  if ($manifest.active_version -ne $version -or
      $manifest.executable_path -ne 'gsd.exe' -or
      $manifest.executable_sha256 -ne $exeHash -or
      $manifest.bundle_path -ne $bundleName -or
      $manifest.bundle_sha256 -ne $bundleHash) {
    throw 'Existing runtime-manifest.json does not match the pinned Windows runtime'
  }
}
$toolDir | Out-File -FilePath $env:GITHUB_PATH -Encoding utf8 -Append
& "$toolDir\gsd.exe" version --no-update-check
if ($LASTEXITCODE -ne 0) { throw 'GSD version check failed' }
