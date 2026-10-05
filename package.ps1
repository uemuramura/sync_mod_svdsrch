$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$appName = "TA-syncgitmdsearch"
$source = Join-Path $root $appName
$dist = Join-Path $root "dist"
$stage = Join-Path $dist $appName
$package = Join-Path $dist "$appName-1.1.0.spl"

if (-not (Test-Path $source)) {
    throw "App directory not found: $source"
}

if (Test-Path $dist) {
    Remove-Item -Recurse -Force $dist
}
New-Item -ItemType Directory -Path $stage | Out-Null

Copy-Item -Path (Join-Path $source "*") -Destination $stage -Recurse -Force

Get-ChildItem -Path $stage -Recurse -Directory -Filter "__pycache__" | Remove-Item -Recurse -Force
Get-ChildItem -Path $stage -Recurse -Include "*.pyc", "*.pyo" | Remove-Item -Force
$localDir = Join-Path $stage "local"
if (Test-Path $localDir) {
    Remove-Item -Recurse -Force $localDir
}

if (Test-Path $package) {
    Remove-Item -Force $package
}

Push-Location $dist
try {
    tar -czf $package $appName
} finally {
    Pop-Location
}

Write-Output "Created $package"
