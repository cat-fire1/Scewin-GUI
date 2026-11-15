param(
    [switch]$SkipInstall,
    [string]$DistPath = 'dist'
)

$ErrorActionPreference = 'Stop'
Push-Location $PSScriptRoot
try {
    $outputRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot $DistPath))
    $workspacePrefix = $PSScriptRoot.TrimEnd('\') + '\'
    if (-not $outputRoot.StartsWith($workspacePrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw 'Build output must be inside this project directory.'
    }
    $bundlePath = Join-Path $outputRoot 'ScewinGUI'
    $runtimeData = @('nvram.txt', 'nvram_new.txt', 'settings.ini', 'backups')
    foreach ($runtimeName in $runtimeData) {
        if (Test-Path -LiteralPath (Join-Path $bundlePath $runtimeName)) {
            throw "Build output contains local data ($runtimeName). Use a different -DistPath to preserve it."
        }
    }
    if (-not $SkipInstall) {
        & npm ci --prefix frontend
        if ($LASTEXITCODE -ne 0) { throw 'npm ci failed' }
    }
    & npm run build --prefix frontend
    if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed' }

    & python -m PyInstaller --noconfirm --windowed --onedir `
        --name ScewinGUI --icon icon.ico --distpath $outputRoot `
        --add-data 'frontend/dist;frontend/dist' `
        --add-data 'scewin_gui/translations;translations' `
        --add-data 'icon.ico;.' `
        --exclude-module PyQt5 --exclude-module PyQt6 `
        --exclude-module PySide2 --exclude-module PySide6 `
        --exclude-module qtpy --exclude-module qfluentwidgets main.py
    if ($LASTEXITCODE -ne 0) { throw 'Desktop build failed' }

    foreach ($vendorFile in @('SCEWIN_64.exe', 'amifldrv64.sys', 'amigendrv64.sys')) {
        Copy-Item -LiteralPath (Join-Path $PSScriptRoot $vendorFile) -Destination $bundlePath
    }
    Write-Host "Built: $bundlePath\ScewinGUI.exe"
}
finally {
    Pop-Location
}
