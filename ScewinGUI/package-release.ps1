param(
    [string]$BundlePath = 'dist\ScewinGUI',
    [string]$Version = '',
    [string]$OutputDirectory = 'releases'
)

$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem

if (-not $Version) {
    $config = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'scewin_gui\config.py') -Raw
    $Version = [regex]::Match($config, 'app_version: str = "([0-9.]+)"').Groups[1].Value
}
if ($Version -notmatch '^\d+\.\d+\.\d+$') { throw 'Version must have the form X.Y.Z.' }

$bundle = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot $BundlePath))
$output = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot $OutputDirectory))
$workspacePrefix = $PSScriptRoot.TrimEnd('\') + '\'
foreach ($target in @($bundle, $output)) {
    if (-not $target.StartsWith($workspacePrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw 'Release paths must be inside this project directory.'
    }
}
$requiredFiles = @('ScewinGUI.exe', 'SCEWIN_64.exe', 'amifldrv64.sys', 'amigendrv64.sys')
foreach ($name in $requiredFiles) {
    if (-not (Test-Path -LiteralPath (Join-Path $bundle $name) -PathType Leaf)) {
        throw "Missing bundle file: $name"
    }
}
$internal = Join-Path $bundle '_internal'
if (-not (Test-Path -LiteralPath $internal -PathType Container)) { throw 'Missing _internal runtime directory.' }
$releaseDirectory = Join-Path $output "v$Version"
New-Item -ItemType Directory -Path $releaseDirectory -Force | Out-Null
$zipPath = Join-Path $releaseDirectory 'ScewinGUI-windows-x64.zip'
if (Test-Path -LiteralPath $zipPath) { throw "Archive already exists: $zipPath" }

# An explicit allowlist excludes BIOS dumps, backups, settings, logs and caches.
$archive = [System.IO.Compression.ZipFile]::Open($zipPath, [System.IO.Compression.ZipArchiveMode]::Create)
try {
    foreach ($name in $requiredFiles) {
        [System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile(
            $archive, (Join-Path $bundle $name), "ScewinGUI/$name",
            [System.IO.Compression.CompressionLevel]::Optimal
        ) | Out-Null
    }
    foreach ($file in Get-ChildItem -LiteralPath $internal -File -Recurse) {
        $relative = $file.FullName.Substring($bundle.Length + 1).Replace('\', '/')
        if ($relative -match '(^|/)(__pycache__|node_modules|\.vite)(/|$)') { continue }
        [System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile(
            $archive, $file.FullName, "ScewinGUI/$relative",
            [System.IO.Compression.CompressionLevel]::Optimal
        ) | Out-Null
    }
    [System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile(
        $archive, (Join-Path $PSScriptRoot 'LICENSE'), 'ScewinGUI/LICENSE',
        [System.IO.Compression.CompressionLevel]::Optimal
    ) | Out-Null
    $entry = $archive.CreateEntry('ScewinGUI/README.txt')
    $writer = New-Object System.IO.StreamWriter($entry.Open())
    try {
        $writer.WriteLine("Scewin GUI $Version - Windows x64")
        $writer.WriteLine('Extract the entire ScewinGUI folder before starting ScewinGUI.exe.')
        $writer.WriteLine('Keep the _internal folder and bundled SCEWIN files beside the application.')
        $writer.WriteLine('Microsoft Edge WebView2 Runtime is required. Python and Node.js are not required.')
        $writer.WriteLine('Administrator privileges are required for BIOS operations.')
        $writer.WriteLine('Always keep backups before changing BIOS settings.')
        $writer.WriteLine('Source, documentation and releases: https://github.com/cat-fire1/Scewin-GUI')
    }
    finally { $writer.Dispose() }
}
finally { $archive.Dispose() }

$hash = (Get-FileHash -LiteralPath $zipPath -Algorithm SHA256).Hash.ToLowerInvariant()
$checksumPath = Join-Path $releaseDirectory 'SHA256SUMS.txt'
[System.IO.File]::WriteAllText($checksumPath, "$hash  ScewinGUI-windows-x64.zip`n", [System.Text.Encoding]::ASCII)
Write-Host "Archive: $zipPath"
Write-Host "SHA256: $hash"
