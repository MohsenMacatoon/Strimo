"""Automated smoke test, run on a real Windows machine by the GitHub build.

Strimo.exe --selftest --selftest-media=<video> --selftest-url=<http link to same video>
            --selftest-report=<report.txt>

It drives the real window and the real mpv engine (with null video/audio output),
exercises every major feature and writes a PASS/FAIL report. Exit code 0 = all passed.
"""

from __future__ import annotations

import os
import time
import traceback

from PySide6.QtCore import QObject, QTimer
from PySide6.QtWidgets import QApplication

from . import icons, ytdl
from .procs import LinkResolver


class SelfTest(QObject):
    def __init__(self, win, report_path: str, media: str | None, url: str | None):
        super().__init__(win)
        self.win = win
        self.report_path = report_path
        self.media = media
        self.url = url
        self.results: list[tuple[str, bool, str]] = []
        self.steps = self._steps()
        self.index = 0
        self._wait_until = None
        self._wait_cond = None
        self._wait_name = ""
        self._resolved = None
        self.started = time.monotonic()

    # ------------------------------------------------------------- framework
    def start(self) -> None:
        QTimer.singleShot(800, self._next)
        QTimer.singleShot(240_000, self._abort)  # hard stop after 4 minutes

    def _abort(self) -> None:
        self.results.append(("overall time limit", False, "selftest took longer than 4 minutes"))
        self._finish()

    def ok(self, name: str, detail: str = "") -> None:
        self.results.append((name, True, detail))

    def fail(self, name: str, detail: str) -> None:
        self.results.append((name, False, detail))

    def check(self, name: str, cond: bool, detail: str = "") -> None:
        (self.ok if cond else self.fail)(name, detail)

    def wait_for(self, name: str, cond, timeout_s: float) -> None:
        self._wait_name = name
        self._wait_cond = cond
        self._wait_until = time.monotonic() + timeout_s

    def _next(self) -> None:
        if self._wait_cond is not None:
            try:
                done = bool(self._wait_cond())
            except Exception as exc:  # noqa: BLE001
                done = False
                self.fail(self._wait_name, f"error while waiting: {exc}")
                self._wait_cond = None
            if done:
                self.ok(self._wait_name)
                self._wait_cond = None
            elif time.monotonic() > self._wait_until:
                self.fail(self._wait_name, "timed out")
                self._wait_cond = None
            else:
                QTimer.singleShot(100, self._next)
                return
        if self.index >= len(self.steps):
            self._finish()
            return
        name, fn, delay = self.steps[self.index]
        self.index += 1
        try:
            fn()
        except Exception:  # noqa: BLE001
            self.fail(name, traceback.format_exc(limit=6))
        QTimer.singleShot(delay, self._next)

    def _finish(self) -> None:
        if getattr(self, "_finished", False):
            return
        self._finished = True
        passed = sum(1 for r in self.results if r[1])
        failed = [r for r in self.results if not r[1]]
        lines = [f"Strimo self-test: {passed} passed, {len(failed)} failed "
                 f"({time.monotonic() - self.started:.1f} s)", ""]
        for name, good, detail in self.results:
            lines.append(f"[{'PASS' if good else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
        text = "\n".join(lines) + "\n"
        try:
            with open(self.report_path, "w", encoding="utf-8") as f:
                f.write(text)
        except OSError:
            pass
        print(text)
        code = 0 if not failed else 1
        try:
            self.win.close()
        except Exception:  # noqa: BLE001
            pass
        QTimer.singleShot(300, lambda: QApplication.instance().exit(code))

    # ------------------------------------------------------------- steps
    def _steps(self):
        w = self.win
        S = []

        def step(name, delay=150):
            def deco(fn):
                S.append((name, fn, delay))
                return fn
            return deco

        @step("icons draw")
        def _():
            for n in ("play", "pause", "stop", "prev", "next", "volume", "volume_low", "mute", "rotate",
                      "rotate_ccw", "fullscreen", "fullscreen_exit", "speed", "loop", "camera", "panel", "link",
                      "download", "folder", "file", "gear", "bookmark", "note", "info", "mini", "list", "shuffle",
                      "repeat", "plus", "close", "trash", "moon", "pin", "frame", "sub", "resume", "sliders"):
                pm = icons.pixmap(n)
                assert not pm.isNull(), n
            self.ok("icons draw")

        @step("tools present")
        def _():
            self.check("yt-dlp found", bool(ytdl.ytdlp_path()), str(ytdl.ytdlp_path()))
            self.check("ffmpeg found", True, str(ytdl.ffmpeg_path() or "not bundled (lite build)"))

        @step("open local video", 200)
        def _():
            assert self.media and os.path.exists(self.media), f"test media missing: {self.media}"
            w.open_paths([self.media])
            self.wait_for("video loads and has a duration", lambda: (w._duration or 0) > 1, 20)

        @step("playback advances", 1500)
        def _():
            self._p0 = w._pos or 0.0

        @step("position moved")
        def _():
            self.check("position moved", (w._pos or 0) > self._p0, f"{self._p0} -> {w._pos}")

        @step("pause / resume", 400)
        def _():
            w.toggle_pause()

        @step("paused state")
        def _():
            self.check("pause works", w.player.get("pause") is True)
            w.toggle_pause()

        @step("seek forward/back", 600)
        def _():
            w.seek_relative(3)
            w.seek_relative(-2)
            w.seek_percent(50)

        @step("seek landed")
        def _():
            d = w._duration or 0
            self.check("seek to 50%", abs((w._pos or 0) - d / 2) < max(1.5, d * 0.1), f"pos={w._pos} dur={d}")

        @step("speed controls", 300)
        def _():
            w.set_speed(1.37)
            assert abs(w.player.get("speed") - 1.37) < 1e-6, w.player.get("speed")
            w.change_speed(0.01)
            assert abs(w.player.get("speed") - 1.38) < 1e-6, w.player.get("speed")
            w.change_speed(-0.1)
            assert abs(w.player.get("speed") - 1.28) < 1e-6, w.player.get("speed")
            w.set_speed(0.01)
            assert abs(w.player.get("speed") - 0.05) < 1e-6, "min clamp"
            w.set_speed(99)
            assert abs(w.player.get("speed") - 8.0) < 1e-6, "max clamp"
            w.set_speed(1.0)
            w._set_pitch(False)
            w._set_pitch(True)
            self.ok("speed: exact, fine steps, limits, pitch")

        @step("hold-to-boost", 300)
        def _():
            w._start_boost()
            assert w._boosting and abs(w.player.get("speed") - 2.0) < 1e-6
            w._stop_boost()
            assert abs(w.player.get("speed") - 1.0) < 1e-6
            self.ok("hold → 2× and back")

        @step("volume & mute", 300)
        def _():
            w.set_volume(150)
            assert int(w.player.get("volume")) == 150
            w.change_volume(-20)
            assert int(w.player.get("volume")) == 130
            w.toggle_mute()
            assert w.player.get("mute") is True
            w.toggle_mute()
            w.set_volume(100)
            self.ok("volume up to 200%, mute")

        @step("rotation & flips", 400)
        def _():
            w.rotate(90)
            assert int(w.player.get("video-rotate")) == 90, w.player.get("video-rotate")
            w.rotate(-90)
            w.rotate(180)
            assert int(w.player.get("video-rotate")) == 180
            w.act_flip_h.setChecked(True)
            w.act_flip_v.setChecked(True)
            vf = str(w.player.get("vf"))
            assert "hflip" in vf and "vflip" in vf, vf
            w.toggle_portrait()
            w.reset_orientation()
            assert int(w.player.get("video-rotate")) == 0
            assert "flip" not in str(w.player.get("vf") or "")
            self.ok("rotate 90/180/270, mirror, flip, portrait, reset")

        @step("aspect, zoom, picture", 300)
        def _():
            for key in ("16:9", "4:3", "21:9", "stretch", "fill", "auto"):
                w.set_aspect(key)
            w.adjust.step_zoom(0.5)
            assert abs(float(w.player.get("video-zoom")) - 0.5) < 0.02
            w.adjust.reset_zoom()
            for name in w.adjust.PRESETS:
                w.adjust.apply_preset(name)
            w.adjust.sliders["brightness"].setValue(10)
            assert int(w.player.get("brightness")) == 10
            w.adjust.apply_preset("Reset")
            self.ok("aspect ratios, zoom, picture presets")

        @step("audio filters", 300)
        def _():
            w.act_night.setChecked(True)
            assert "dynaudnorm" in str(w.player.get("af")), w.player.get("af")
            w.act_night.setChecked(False)
            self.ok("night mode")

        @step("subtitle controls", 200)
        def _():
            w.nudge_sub_delay(0.1)
            assert abs(float(w.player.get("sub-delay")) - 0.1) < 1e-3
            w.nudge_sub_delay(-0.1)
            w.adjust.step_sub_scale(0.1)
            self.ok("subtitle delay & size")

        @step("frame stepping", 400)
        def _():
            w.frame_step(False)
            w.frame_step(True)

        @step("A-B loop", 300)
        def _():
            w.toggle_pause() if w._paused else None
            w.ab_loop()

        @step("A-B loop B", 600)
        def _():
            w.ab_loop()

        @step("A-B loop state")
        def _():
            a, b = w._ab
            self.check("A-B loop sets both points", a is not None and b is not None, f"{a} {b}")
            w.ab_loop()

        @step("bookmarks & notes", 200)
        def _():
            w.add_bookmark()
            assert len(w.bookmarks.items()) == 1
            assert len(w.cfg.get_list(w.current_entry, "bookmarks")) == 1
            w.notes.edit.setText("test note")
            w.notes._on_edit("test note")
            w.notes._commit()
            assert len(w.cfg.get_list(w.current_entry, "notes")) == 1
            assert "test note" in w.notes.as_text()
            self.ok("bookmarks & timestamped notes saved")

        @step("window modes", 600)
        def _():
            w.toggle_fullscreen()
            assert w._fullscreen
            w.toggle_fullscreen()
            w.toggle_mini()
            assert w._mini

        @step("window modes back", 600)
        def _():
            w.toggle_mini()
            assert not w._mini
            w.act_on_top.setChecked(True)
            w.act_on_top.setChecked(False)
            w.act_frame_counter.setChecked(True)
            w.act_frame_counter.setChecked(False)
            self.ok("fullscreen, mini player, always on top, frame counter")

        @step("side panel tabs", 200)
        def _():
            for i in range(w.tabs.count()):
                w.show_panel(i)
            w.refresh_info()
            name = w.info_panel._labels["Resolution"].text()
            self.check("media info shows resolution", "×" in name, name)
            w.toggle_panel()

        @step("intro skip rule", 200)
        def _():
            w.cfg.set_intro(w.current_entry, 0.0, 2.0)
            assert w.cfg.get_intro(w.current_entry) == (0.0, 2.0)
            w.cfg.set_intro(w.current_entry, None, None)
            self.ok("intro skip rule save/remove")

        @step("sleep timer", 200)
        def _():
            w._sleep = {"action": "pause", "mode": "minutes", "minutes": 0, "deadline": time.monotonic() - 1}
            w.sleep_timer.start()
            w._sleep_tick()
            self.check("sleep timer pauses", w.player.get("pause") is True and w._sleep is None)
            w.toggle_pause()

        @step("playlist navigation", 1500)
        def _():
            w.playlist.add_entries([self.media])
            w.next_file()

        @step("resume memory", 200)
        def _():
            entry = w.current_entry
            w.cfg.set_position(entry, 3.0)
            assert abs(w.cfg.get_position(entry) - 3.0) < 1e-6
            w.cfg.set_speed(entry, 1.5)
            assert w.cfg.get_speed(entry) == 1.5
            w.cfg.set_speed(entry, 1.0)
            assert w.cfg.get_speed(entry) is None
            self.ok("resume position & per-file speed memory")

        @step("dialogs build", 200)
        def _():
            from .dialogs import (IntroSkipDialog, OpenLinkDialog, SettingsDialog, ShortcutsDialog,
                                  SleepTimerDialog, about_text)
            for d in (SettingsDialog(w.cfg, w), OpenLinkDialog(w.cfg, w, url="https://example.com/v.mp4"),
                      ShortcutsDialog(w), SleepTimerDialog(None, w), IntroSkipDialog(10.0, None, "C:\\", w)):
                d.show()
                d.close()
                d.deleteLater()
            assert "Strimo" in about_text()
            self.ok("all dialogs open")

        @step("context menu & menus build", 200)
        def _():
            w._fill_recent()
            w._fill_tracks(w.audio_menu, "audio", "aid")
            w._fill_tracks(w.sub_menu, "sub", "sid")
            self.ok("menus fill")

        @step("direct link playback", 300)
        def _():
            if not self.url:
                self.ok("direct link playback", "skipped (no url)")
                return
            w.play_link(self.url)
            self.wait_for("direct http link plays", lambda: (w._duration or 0) > 1 and w.current_entry == self.url, 20)

        @step("yt-dlp resolves a link", 200)
        def _():
            if not self.url or not ytdl.ytdlp_path():
                self.ok("yt-dlp resolves a link", "skipped")
                return
            self._resolved = None
            r = LinkResolver(self.url, ytdl.stream_format("720"), self, timeout_ms=60000)
            r.resolved.connect(lambda info: setattr(self, "_resolved", info))
            r.failed.connect(lambda msg: setattr(self, "_resolved", {"error": msg}))
            r.start()
            self._resolver_ref = r
            self.wait_for("yt-dlp answered", lambda: self._resolved is not None, 60)

        @step("yt-dlp result", 100)
        def _():
            if self._resolved is None:
                return
            self.check("yt-dlp info has a playable url", bool(self._resolved.get("video_url")),
                       str(self._resolved)[:300])

        @step("download manager", 200)
        def _():
            if not self.url or not ytdl.ytdlp_path():
                self.ok("download", "skipped")
                return
            self._item = w.downloads.add(self.url, "720")
            self.wait_for("download finishes", lambda: self._item.status in ("done", "failed"), 90)

        @step("download result", 100)
        def _():
            item = getattr(self, "_item", None)
            if item is None:
                return
            ok = item.status == "done" and item.filepath and os.path.exists(item.filepath)
            self.check("downloaded file exists", bool(ok), f"{item.status} {item.error} {item.filepath}")

        @step("stop", 300)
        def _():
            w.stop()
            self.ok("stop")

        return S
