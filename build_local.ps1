# Build Strimo on your own Windows PC (instead of GitHub).
# Needs: Python 3.11+ (python.org, tick "Add to PATH") and 7-Zip.  Uses about 250 MB of internet data.
# Run from this folder:   powershell -ExecutionPolicy Bypass -File build_local.ps1
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot

python -m pip install --upgrade pip
pip install -r requirements.txt -r requirements-build.txt
python tests\test_logic.py

if (-not (Get-Command 7z -ErrorAction SilentlyContinue)) {
    $sevenZip = 'C:\Program Files\7-Zip'
    if (Test-Path "$sevenZip\7z.exe") { $env:PATH = "$sevenZip;$env:PATH" } else { throw 'Please install 7-Zip (7-zip.org) first.' }
}
& .\build\fetch_tools.ps1
pyinstaller --noconfirm strimo.spec
& .\build\selftest.ps1

$iscc = Join-Path ${env:ProgramFiles(x86)} 'Inno Setup 6\ISCC.exe'
if (Test-Path $iscc) {
    & .\build\make_installers.ps1
    Write-Host "`nDone! Installers are in the 'output' folder."
} else {
    Copy-Item vendor\tools -Destination dist\Strimo\tools -Recurse -Force
    Write-Host "`nDone! Strimo is in dist\Strimo (run Strimo.exe)."
    Write-Host 'Install Inno Setup 6 (jrsoftware.org) and run build\make_installers.ps1 to get a Setup.exe.'
}
