# Builds Strimo-Setup-<version>.exe (full) and Strimo-Setup-<version>-Lite.exe with Inno Setup.
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path -Parent $PSScriptRoot)

$iscc = Join-Path ${env:ProgramFiles(x86)} 'Inno Setup 6\ISCC.exe'
if (-not (Test-Path $iscc)) {
    Write-Host 'Installing Inno Setup...'
    choco install innosetup -y --no-progress | Out-Null
}
if (-not (Test-Path $iscc)) { throw 'Inno Setup (ISCC.exe) not found' }

$version = (python -c "import strimo; print(strimo.__version__)").Trim()
& $iscc "/DAppVersion=$version" installer\strimo.iss
if ($LASTEXITCODE -ne 0) { throw 'full installer failed' }
& $iscc "/DAppVersion=$version" /DLITE installer\strimo.iss
if ($LASTEXITCODE -ne 0) { throw 'lite installer failed' }
Get-ChildItem output\*.exe | ForEach-Object { '{0,8:N1} MB  {1}' -f ($_.Length / 1MB), $_.Name }
