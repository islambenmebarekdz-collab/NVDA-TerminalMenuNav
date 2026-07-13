# Builds TerminalMenuNav.nvda-addon (a zip of the addon/ folder contents).
# Compiles locale .po files to .mo first, then zips with forward-slash entry
# names (required so NVDA resolves nested paths) excluding __pycache__/*.pyc.
# Usage:  powershell -ExecutionPolicy Bypass -File build.ps1
$ErrorActionPreference = "Stop"
$root  = $PSScriptRoot
$addon = Join-Path $root "addon"
$out   = Join-Path $root "TerminalMenuNav.nvda-addon"

if (-not (Test-Path (Join-Path $addon "manifest.ini"))) {
    throw "manifest.ini not found under $addon"
}

# Compile translations.
python (Join-Path $root "tools\build_mo.py")
if ($LASTEXITCODE -ne 0) { throw "Translation compilation failed" }

if (Test-Path $out) { Remove-Item $out -Force }

Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem

$fs  = [System.IO.File]::Open($out, [System.IO.FileMode]::CreateNew)
$zip = New-Object System.IO.Compression.ZipArchive($fs, [System.IO.Compression.ZipArchiveMode]::Create)
try {
    $addonFull = (Resolve-Path $addon).Path.TrimEnd('\') + '\'
    Get-ChildItem -Path $addon -Recurse -File | Where-Object {
        $_.FullName -notmatch '\\__pycache__\\' -and $_.Extension -ne '.pyc'
    } | ForEach-Object {
        $rel = $_.FullName.Substring($addonFull.Length) -replace '\\', '/'
        $entry = $zip.CreateEntry($rel, [System.IO.Compression.CompressionLevel]::Optimal)
        $es = $entry.Open()
        $bytes = [System.IO.File]::ReadAllBytes($_.FullName)
        $es.Write($bytes, 0, $bytes.Length)
        $es.Dispose()
        Write-Host "  + $rel"
    }
} finally {
    $zip.Dispose()
    $fs.Dispose()
}
Write-Host "Built: $out"
