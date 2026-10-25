# Strimo

An ad-free video player for Windows with **precise speed control**, **free rotation/flipping**, **link streaming** and a **download manager**. No ads, no tracking, no account.

Playback uses the mpv engine (plays MP4, MKV, AVI, MOV, WebM, FLV, TS, MP3, FLAC… almost anything VLC plays). Links use yt-dlp, HD downloads use FFmpeg.

## Features

**Playback** — open files, whole folders, drag & drop or "Open with"; automatic playlist of the folder (next/previous episode); resume where you left off; A-B repeat; frame-by-frame; jump to any time; bookmarks; timestamped notes you can export.

**Speed** — 0.05× to 8× in 0.01× steps, type an exact value (e.g. 1.37×), presets, voice pitch correction, *hold → for 2×*, remembered per file.

**Picture** — rotate 90/180/270°, mirror, vertical flip, one-key portrait mode, zoom & pan, aspect ratios (16:9, 4:3, 21:9, 9:16, stretch, crop), brightness/contrast/saturation/gamma/hue, "Dark video boost" and "Vivid" presets, screenshots.

**Sound** — volume up to 200%, night mode (evens out loud and quiet parts), audio track choice, audio sync delay.

**Subtitles** — auto-loads a matching .srt, load any subtitle file, choose track, size and delay.

**Links** — play direct links (.mp4, .mkv, .m3u8 …) and links from many video sites; choose the streaming quality (240p data saver up to 4K); adjustable buffer for slow connections; buffered part shown on the seek bar; link history.

**Downloads** — queue, pause/resume (also after the internet drops or Strimo closes), speed limit, quality choice, audio only (M4A/MP3), subtitles, *Play & Save* (keeps a copy of what you watch with no extra data).

**Comfort** — dark theme, controls hide in fullscreen, mini player (small, always on top, drag anywhere), always on top, sleep timer (pause / stop / close / sleep PC / shut down PC), auto-skip intros per folder, media info panel, mouse-wheel gestures (left half = brightness, right half = volume).

## Main keyboard shortcuts

| Key | Action |
|---|---|
| Space | Play / pause |
| ← / → | −5 s / +5 s (Shift: 30 s) |
| Hold → | 2× while held |
| ↑ / ↓ | Volume |
| ] / [ | Speed ±0.1× |
| } / { (Shift+] / [) | Speed ±0.01× |
| Backspace | Speed back to 1× |
| R / H / V / P | Rotate / mirror / flip / portrait mode |
| F or double-click | Fullscreen |
| M · N | Mute · Night mode |
| . / , | Next / previous frame |
| L | A-B repeat |
| S | Screenshot |
| Ctrl+O / Ctrl+U | Open file / open link |
| Ctrl+D / Ctrl+T | Downloads / sleep timer |
| F1 | All shortcuts |

## Getting the installer

See **BUILD.md**. The easiest way is to let GitHub build it for free: upload this folder to a GitHub repository and download `Strimo-Setup` from the Actions tab.

## Project layout

```
main.py                 start-up (PyInstaller entry)
strimo/                 the app
  mainwindow.py         window, menus, shortcuts, behaviour
  player.py             mpv engine wrapper
  video_widget.py       video surface (OpenGL, with automatic compatibility fallback)
  controls.py           control bar + speed popup      seekbar.py   seek bar
  panels.py             playlist, bookmarks, notes, adjust, info
  downloads.py          download manager               procs.py     yt-dlp processes
  dialogs.py            open link, sleep timer, settings, shortcuts …
  config.py / util.py / ytdl.py / paths.py   logic without Qt (tested in tests/)
  selftest.py           automatic test run on Windows during the build
installer/strimo.iss    Inno Setup installer script
build/*.ps1             download tools, self-test, make installers
.github/workflows/      GitHub build
```

Settings and memory (positions, bookmarks, notes) are stored in `%APPDATA%\Strimo`.
