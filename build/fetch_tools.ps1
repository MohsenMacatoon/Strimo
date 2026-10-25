# Downloads the playback engine (libmpv), yt-dlp and FFmpeg into .\vendor
# Used by the GitHub build and by build_local.ps1.
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
Set-Location (Split-Path -Parent $PSScriptRoot)

New-Item -ItemType Directory -Force vendor, vendor\tools, vendor\tmp | Out-Null
$headers = @{ 'User-Agent' = 'strimo-build' }
if ($env:GITHUB_TOKEN) { $headers['Authorization'] = "Bearer $($env:GITHUB_TOKEN)" }

function Get-Asset($repo, $pattern) {
    $rel = Invoke-RestMethod -Headers $headers "https://api.github.com/repos/$repo/releases/latest"
    return $rel.assets | Where-Object { $_.name -match $pattern } | Select-Object -First 1
}

# ---- libmpv (playback engine) -------------------------------------------
if (-not ((Test-Path vendor\libmpv-2.dll) -or (Test-Path vendor\mpv-2.dll))) {
    $asset = $null
    foreach ($repo in @('shinchiro/mpv-winbuild-cmake', 'zhongfly/mpv-winbuild')) {
        try {
            $asset = Get-Asset $repo '^mpv-dev-x86_64-\d{8}-git-[0-9a-f]+\.7z$'
            if ($asset) { Write-Host "libmpv from $repo : $($asset.name)"; break }
        } catch { Write-Warning "Could not read releases of $repo : $_" }
    }
    if (-not $asset) { throw 'Could not find a libmpv (mpv-dev-x86_64) download.' }
    Invoke-WebRequest $asset.browser_download_url -OutFile vendor\tmp\mpv-dev.7z
    & 7z x vendor\tmp\mpv-dev.7z -ovendor\tmp\mpv -y | Out-Null
    $dll = Get-ChildItem vendor\tmp\mpv -Recurse -Filter 'libmpv-2.dll' | Select-Object -First 1
    if (-not $dll) { $dll = Get-ChildItem vendor\tmp\mpv -Recurse -Filter 'mpv-2.dll' | Select-Object -First 1 }
    if (-not $dll) { throw 'libmpv-2.dll was not inside the mpv-dev archive.' }
    Copy-Item $dll.FullName vendor\libmpv-2.dll
}

# python-mpv looks for libmpv-2.dll on new versions and mpv-2.dll on older ones
      $mpvpy = (python -c "import importlib.util; print(importlib.util.find_spec('mpv').origin)").Trim()
if ((Test-Path vendor\libmpv-2.dll) -and -not (Select-String -Path $mpvpy -Pattern 'libmpv-2.dll' -Quiet)) {
    Write-Host 'python-mpv expects mpv-2.dll - renaming'
    Move-Item -Force vendor\libmpv-2.dll vendor\mpv-2.dll
}

# ---- yt-dlp (link support) ---------------------------------------------------
if (-not (Test-Path vendor\tools\yt-dlp.exe)) {
    Invoke-WebRequest 'https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe' -OutFile vendor\tools\yt-dlp.exe
}
& vendor\tools\yt-dlp.exe --version

# ---- FFmpeg (joins video+audio for HD downloads, MP3 conversion) -------------
if (-not (Test-Path vendor\tools\ffmpeg.exe)) {
    try {
        Invoke-WebRequest 'https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip' -OutFile vendor\tmp\ffmpeg.zip
    } catch {
        Write-Warning "gyan.dev unavailable ($_), using yt-dlp's FFmpeg build"
        Invoke-WebRequest 'https://github.com/yt-dlp/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip' -OutFile vendor\tmp\ffmpeg.zip
    }
    Expand-Archive vendor\tmp\ffmpeg.zip vendor\tmp\ffmpeg -Force
    $ff = Get-ChildItem vendor\tmp\ffmpeg -Recurse -Filter 'ffmpeg.exe' | Select-Object -First 1
    Copy-Item $ff.FullName vendor\tools\ffmpeg.exe
}
& vendor\tools\ffmpeg.exe -hide_banner -version | Select-Object -First 1

Remove-Item -Recurse -Force vendor\tmp -ErrorAction SilentlyContinue
Get-ChildItem vendor -Recurse -File | ForEach-Object { '{0,8:N1} MB  {1}' -f ($_.Length / 1MB), $_.FullName }
