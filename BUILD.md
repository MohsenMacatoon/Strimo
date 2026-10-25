# How to get Strimo-Setup.exe

## Option A — let GitHub build it (recommended, uses the least data)

You upload ~200 KB of source code. GitHub's Windows computer downloads all the heavy tools, builds Strimo, **tests it automatically**, and gives you the finished installer. It's free.

1. **Unzip** `Strimo-source.zip` on your PC.
2. Go to **github.com → New repository**. Name it `strimo`. Private is fine. Click **Create repository**.
3. On the new empty repository page, click **"uploading an existing file"**.
4. Open the unzipped `Strimo` folder, select **everything inside it** (including the `.github` folder) and drag it onto the page. Click **Commit changes**.
5. Open the **Actions** tab. The build "Build Strimo for Windows" starts by itself and takes about 15–20 minutes.
   - If it doesn't start, click it on the left → **Run workflow**.
6. When it shows a green ✓, click the run and scroll to **Artifacts**. Download **one** of these:
   - **Strimo-Setup-Lite** — smaller; links and downloads work, but HD downloads are limited to single-file qualities and MP3 becomes M4A.
   - **Strimo-Setup (full)** — includes FFmpeg for HD downloads (joins video + audio) and MP3.
7. Unzip the download and run `Strimo-Setup-1.0.0.exe`.
   Windows may say *"Windows protected your PC"* → click **More info → Run anyway** (normal for apps without a paid certificate).

**If the build shows a red ✗:** open the failed step and copy the last lines, or download the `selftest-report` artifact, and send it to Claude to fix.

**Updating later:** change or replace files in the repository (Add file → Upload files). Every change builds a new installer.
To get a permanent download link, create a tag/release named `v1.0.0` (Releases → Draft a new release → tag `v1.0.0`) and the installers are attached to the release.

## Option B — build on your own PC

Uses about 250 MB of internet data (Python packages, mpv engine, FFmpeg, Inno Setup).

1. Install **Python 3.12** from python.org (tick *Add python.exe to PATH*), **7-Zip** and **Inno Setup 6**.
2. In the Strimo folder: Shift + right-click → *Open PowerShell window here*, then:

   ```powershell
   powershell -ExecutionPolicy Bypass -File build_local.ps1
   ```
3. The installers appear in the `output` folder.

## Notes

- Strimo installs per user (no admin needed) into `%LOCALAPPDATA%\Programs\Strimo`.
- **Tools → Update link support** refreshes yt-dlp (~18 MB) when a site stops working — no reinstall needed.
- Some sites (for example YouTube) may need a JavaScript runtime such as Deno for every quality to be available. If a site gives fewer qualities than expected, update link support first.
- Settings, resume positions, bookmarks and notes live in `%APPDATA%\Strimo`; the log file there (`strimo.log`) helps with troubleshooting.
- If the picture ever stays black, open **Settings → Advanced → Video output → Compatibility** (Strimo also switches automatically when it detects this).
