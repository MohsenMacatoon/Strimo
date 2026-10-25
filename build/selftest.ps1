# Runs Strimo.exe --selftest against a generated test video, on the build machine.
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path -Parent $PSScriptRoot)

$work = Join-Path $PWD 'selftest'
New-Item -ItemType Directory -Force $work | Out-Null
$video = Join-Path $work 'test.mp4'
& vendor\tools\ffmpeg.exe -hide_banner -loglevel error -y `
    -f lavfi -i 'testsrc2=duration=12:size=640x360:rate=30' `
    -f lavfi -i 'sine=frequency=440:duration=12' `
    -shortest -c:v libx264 -pix_fmt yuv420p -c:a aac $video
if (-not (Test-Path $video)) { throw 'could not create the test video' }

# tools next to the exe, only for the test (the installer adds them itself)
$toolsDir = 'dist\Strimo\tools'
New-Item -ItemType Directory -Force $toolsDir | Out-Null
Copy-Item vendor\tools\*.exe $toolsDir

$server = Start-Process python -ArgumentList '-m', 'http.server', '8765', '--bind', '127.0.0.1', '--directory', $work -PassThru -WindowStyle Hidden
Start-Sleep -Seconds 3
$report = Join-Path $work 'report.txt'
try {
    $p = Start-Process 'dist\Strimo\Strimo.exe' -PassThru -ArgumentList @(
        '--selftest', "--selftest-media=$video", '--selftest-url=http://127.0.0.1:8765/test.mp4', "--selftest-report=$report")
    if (-not $p.WaitForExit(300000)) { $p.Kill(); throw 'self-test hung (5 minutes)' }
    $code = $p.ExitCode
} finally {
    Stop-Process -Id $server.Id -Force -ErrorAction SilentlyContinue
    Remove-Item -Recurse -Force $toolsDir -ErrorAction SilentlyContinue
}

if (Test-Path $report) { Get-Content $report } else { Write-Warning 'no report was written' }
$log = Join-Path $env:APPDATA 'Strimo\strimo.log'
if (Test-Path $log) { Write-Host '---- strimo.log ----'; Get-Content $log -Tail 80 }
if ($code -ne 0) { throw "Self-test failed (exit code $code)" }
Write-Host 'Self-test passed.'
