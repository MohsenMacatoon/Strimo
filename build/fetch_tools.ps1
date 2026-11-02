# Downloads the playback engine (libVLC), yt-dlp and FFmpeg into .\vendor
# Used by the GitHub build and by build_local.ps1.
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
Set-Location (Split-Path -Parent $PSScriptRoot)

New-Item -ItemType Directory -Force vendor, vendor\tools, vendor\tmp | Out-Null

# ---- libVLC (playback engine, the same engine as the VLC app) ----------------
if (-not (Test-Path vendor\vlc\libvlc.dll)) {
    $base = 'https://download.videolan.org/pub/videolan/vlc'
    $versions = @()
    try {
        $listing = (Invoke-WebRequest -UseBasicParsing "$base/").Content
        $versions = [regex]::Matches($listing, 'href="(3\.0\.\d+)/"') | ForEach-Object { $_.Groups[1].Value } |
            Sort-Object { [version]$_ } -Descending -Unique
    } catch { Write-Warning "Could not list VLC versions: $_" }
    $versions = @($versions) + @('3.0.21', '3.0.20') | Select-Object -Unique
    $ok = $false
    foreach ($v in $versions) {
        $url = "$base/$v/win64/vlc-$v-win64.7z"
        try {
            Write-Host "Downloading VLC $v ..."
            Invoke-WebRequest -UseBasicParsing $url -OutFile vendor\tmp\vlc.7z
            $ok = $true
            break
        } catch { Write-Warning "VLC $v not available: $_" }
    }
    if (-not $ok) { throw 'Could not download VLC.' }
    & 7z x vendor\tmp\vlc.7z -ovendor\tmp\vlcx -y | Out-Null
    $src = (Get-ChildItem vendor\tmp\vlcx -Directory | Select-Object -First 1).FullName
    New-Item -ItemType Directory -Force vendor\vlc | Out-Null
    Copy-Item "$src\libvlc.dll", "$src\libvlccore.dll" vendor\vlc
    Copy-Item "$src\plugins" vendor\vlc\plugins -Recurse
    # leave out parts Strimo never uses (VLC's own interface, scripts, visualisations ...)
    foreach ($d in 'gui', 'lua', 'control', 'visualization', 'video_splitter', 'services_discovery', 'keystore') {
        Remove-Item -Recurse -Force "vendor\vlc\plugins\$d" -ErrorAction SilentlyContinue
    }
    # plugin cache = faster start-up
    Copy-Item "$src\vlc-cache-gen.exe" vendor\vlc
    & vendor\vlc\vlc-cache-gen.exe vendor\vlc\plugins
    Remove-Item vendor\vlc\vlc-cache-gen.exe
    if (-not (Test-Path vendor\vlc\plugins\plugins.dat)) { Write-Warning 'plugins.dat was not created (start-up will be a bit slower)' }
}
$vlcMB = (Get-ChildItem vendor\vlc -Recurse -File | Measure-Object Length -Sum).Sum / 1MB
Write-Host ('VLC engine: {0:N1} MB' -f $vlcMB)

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
