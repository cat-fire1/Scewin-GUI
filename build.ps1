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
    if (Test-Path -LiteralPath (Join-Path $bundlePath '_internal')) {
        throw 'Build output contains an older directory-based bundle. Use a fresh -DistPath.'
    }
    if (-not $SkipInstall) {
        & npm ci --prefix frontend
        if ($LASTEXITCODE -ne 0) { throw 'npm ci failed' }
    }
    & npm run build --prefix frontend
    if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed' }

    $configText = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'scewin_gui\config.py') -Raw
    $appVersion = [regex]::Match($configText, 'app_version: str = "(\d+\.\d+\.\d+)"').Groups[1].Value
    if (-not $appVersion) { throw 'Application version is missing from config.py.' }
    $versionTuple = ($appVersion.Split('.') + '0') -join ', '
    $versionDirectory = Join-Path $PSScriptRoot 'build'
    New-Item -ItemType Directory -Path $versionDirectory -Force | Out-Null
    $versionPath = Join-Path $versionDirectory 'version_info.txt'
    $versionResource = @"
VSVersionInfo(
    ffi=FixedFileInfo(filevers=($versionTuple), prodvers=($versionTuple),
        mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),
    kids=[StringFileInfo([StringTable('040904B0', [
        StringStruct('CompanyName', 'cat_fire'),
        StringStruct('FileDescription', 'Scewin GUI NVRAM editor'),
        StringStruct('FileVersion', '$appVersion'),
        StringStruct('InternalName', 'ScewinGUI'),
        StringStruct('OriginalFilename', 'ScewinGUI.exe'),
        StringStruct('ProductName', 'Scewin GUI'),
        StringStruct('ProductVersion', '$appVersion')
    ])]), VarFileInfo([VarStruct('Translation', [1033, 1200])])]
)
"@
    [System.IO.File]::WriteAllText($versionPath, $versionResource, (New-Object System.Text.UTF8Encoding($false)))

    & python -m PyInstaller --noconfirm --windowed --onefile --uac-admin `
        --name ScewinGUI --icon icon.ico --distpath $bundlePath `
        --version-file $versionPath `
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
