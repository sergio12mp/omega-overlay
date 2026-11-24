# Compila Omega Overlay para Windows: dist\OmegaOverlay\OmegaOverlay.exe (+ instalador si hay Inno Setup)
#   powershell -ExecutionPolicy Bypass -File build\build.ps1
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

if (-not (Test-Path ".venv\Scripts\python.exe")) { python -m venv .venv }
& .venv\Scripts\python.exe -m pip install --quiet --upgrade pip
& .venv\Scripts\python.exe -m pip install --quiet -r build\requirements-build.txt

& .venv\Scripts\python.exe -m PyInstaller --noconfirm --clean --windowed --onedir `
    --name OmegaOverlay --icon build\icon.ico `
    --distpath dist --workpath build\out `
    --add-data "overlay;overlay" --add-data "data;data" --add-data "mgba;mgba" `
    --add-data "pokedata.json;." --add-data "build\icon.ico;." `
    --add-data "LICENSE;." --add-data "NOTICE.md;." `
    app.py
if ($LASTEXITCODE -ne 0) { throw "PyInstaller falló" }

$iscc = @("${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe", "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
          "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe") | Where-Object { Test-Path $_ } | Select-Object -First 1
if ($iscc) {
    $ver = (Select-String -Path app.py -Pattern '^VERSION = "(.+)"').Matches[0].Groups[1].Value
    & $iscc "/DAppVersion=$ver" build\installer.iss
    if ($LASTEXITCODE -ne 0) { throw "Inno Setup falló" }
} else {
    Write-Host "Inno Setup no encontrado: solo se genera dist\OmegaOverlay\ (sin instalador)."
}
