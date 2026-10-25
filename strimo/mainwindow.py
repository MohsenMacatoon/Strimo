"""Strimo main window: wires the player, controls, panels, menus and shortcuts together."""

from __future__ import annotations

import os
import subprocess
import time

from PySide6.QtCore import QByteArray, QEvent, QKeyCombination, QPoint, QSize, Qt, QTimer
from PySide6.QtGui import QAction, QActionGroup, QCursor, QGuiApplication, QIcon, QKeySequence
from PySide6.QtWidgets import (
    QAbstractSpinBox, QApplication, QComboBox, QDockWidget, QFileDialog, QInputDialog, QLineEdit,
    QMainWindow, QMenu, QMessageBox, QPlainTextEdit, QTabWidget, QTextEdit, QVBoxLayout, QWidget,
)

from . import APP_NAME, icons, paths, ytdl
from .controls import SPEED_PRESETS, ControlBar
from .dialogs import (
    CountdownDialog, IntroSkipDialog, OpenLinkDialog, SettingsDialog, ShortcutsDialog, SleepTimerDialog,
    about_text,
)
from .downloads import DownloadManager, DownloadsPanel
from .panels import AdjustPanel, BookmarksPanel, InfoPanel, NotesPanel, PlaylistPanel
from .player import LOG, Player
from .procs import CommandRunner, LinkResolver
from .util import (
    ASPECT_CHOICES, MEDIA_EXTS, display_name, fmt_speed, fmt_time, folder_media_files, is_direct_media_url, is_media_file,
    is_sub_file, is_url, normalize_url, parse_time, safe_filename, unique_path,
)
from .video_widget import GLVideoWidget, NativeVideoWidget, NullVideoWidget

TAB_PLAYLIST, TAB_BOOKMARKS, TAB_NOTES, TAB_DOWNLOADS, TAB_ADJUST, TAB_INFO = range(6)
HIDE_DELAY_MS = 2500
CREATE_NO_WINDOW = 0x08000000


def _num_or_none(v):
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


class MainWindow(QMainWindow):
    def __init__(self, cfg, open_args=None, selftest: bool = False):
        super().__init__()
        self.cfg = cfg
        self.selftest = selftest
        self.setWindowTitle(APP_NAME)
        self.setAcceptDrops(True)
        self.setMinimumSize(QSize(480, 300))
        icon_path = paths.asset("strimo.ico")
        self.setWindowIcon(QIcon(icon_path) if os.path.exists(icon_path) else icons.icon("play"))

        # ---- playback state
        self.player: Player | None = None
        self.video = None
        self.current_entry: str | None = None
        self.current_title = ""
        self._resolver: LinkResolver | None = None
        self._pos = None
        self._duration = None
        self._paused = True
        self._idle = True
        self._has_video = False
        self._video_dims = None   # (w, h) before rotation
        self._meta_rotate = 0
        self._intro_rule = None
        self._intro_done = False
        self._ab = (None, None)
        self._boosting = False
        self._boost_prev = 1.0
        self._right_down_at = None
        self._fullscreen = False
        self._mini = False
        self._mini_restore = None
        self._fs_restore = None
        self._sleep = None
        self._last_backend_switch = -1e9
        self._loading = False
        self._record_path = None
        self._press_pos = None
        self._drag_offset = None
        self._dragged = False
        self._ignore_release = False
        self._frame_osd = False
        self._gl_check_timer = None
        self._runners = []

        self.downloads = DownloadManager(cfg, self)

        # ---- layout
        central = QWidget()
        self.central_layout = QVBoxLayout(central)
        self.central_layout.setContentsMargins(0, 0, 0, 0)
        self.central_layout.setSpacing(0)
        self.controls = ControlBar()
        self.central_layout.addWidget(self.controls)
        self.setCentralWidget(central)

        self._build_panels()
        self._build_video(cfg.get("video_backend"))
        self._connect_controls()
        self._build_actions()
        self._build_menus()

        # ---- timers
        self.hide_timer = QTimer(self)
        self.hide_timer.setSingleShot(True)
        self.hide_timer.setInterval(HIDE_DELAY_MS)
        self.hide_timer.timeout.connect(self._auto_hide)
        self.click_timer = QTimer(self)
        self.click_timer.setSingleShot(True)
        self.click_timer.setInterval(max(180, QApplication.styleHints().mouseDoubleClickInterval()))
        self.click_timer.timeout.connect(self._single_click)
        self.save_timer = QTimer(self)
        self.save_timer.setInterval(10_000)
        self.save_timer.timeout.connect(self._periodic_save)
        self.save_timer.start()
        self.sleep_timer = QTimer(self)
        self.sleep_timer.setInterval(1000)
        self.sleep_timer.timeout.connect(self._sleep_tick)

        QApplication.instance().installEventFilter(self)

        # ---- restore window
        self.resize(1100, 680)
        geo = cfg.get("window_geometry")
        if geo and not selftest:
            try:
                self.restoreGeometry(QByteArray.fromBase64(geo.encode("ascii")))
            except Exception:  # noqa: BLE001
                pass
        self.playlist.set_loop_mode(cfg.get("loop_mode"))
        for act, key in ((self.act_on_top, "always_on_top"), (self.act_frame_counter, "show_frame_counter")):
            act.blockSignals(True)
            act.setChecked(bool(cfg.get(key)))
            act.blockSignals(False)
        if cfg.get("show_frame_counter"):
            self.controls.set_frame_text("Frame –")
        self.loop_actions.get(cfg.get("loop_mode"), self.loop_actions["none"]).setChecked(True)
        self.controls.show_remaining = bool(cfg.get("show_remaining"))
        self.controls.set_volume(int(cfg.get("volume")), bool(cfg.get("muted")))
        self.controls.set_speed(1.0)
        self.controls.set_playing(False)
        self.controls.speed_popup.set_pitch(bool(cfg.get("pitch_correction")))
        if cfg.get("panel_visible"):
            self.dock.show()
            self.tabs.setCurrentIndex(int(cfg.get("panel_tab") or 0))
        else:
            self.dock.hide()
        self._pending_args = list(open_args or [])
        QTimer.singleShot(0, self._after_show)

    # ================================================================ construction
    def _build_panels(self) -> None:
        self.dock = QDockWidget("Side panel", self)
        self.dock.setObjectName("sidePanel")
        self.dock.setFeatures(QDockWidget.DockWidgetFeature.DockWidgetClosable |
                              QDockWidget.DockWidgetFeature.DockWidgetMovable)
        self.dock.setAllowedAreas(Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea)
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.playlist = PlaylistPanel()
        self.bookmarks = BookmarksPanel()
        self.notes = NotesPanel(lambda: self._pos)
        self.downloads_panel = DownloadsPanel(self.downloads, self.cfg)
        self.adjust = AdjustPanel(lambda: self.player, self.cfg)
        self.info_panel = InfoPanel()
        for w, name, ic in ((self.playlist, "Playlist", "list"), (self.bookmarks, "Marks", "bookmark"),
                            (self.notes, "Notes", "note"), (self.downloads_panel, "Downloads", "download"),
                            (self.adjust, "Adjust", "sliders"), (self.info_panel, "Info", "info")):
            self.tabs.addTab(w, icons.icon(ic), name)
        self.tabs.setIconSize(QSize(15, 15))
        self.tabs.setMinimumWidth(330)
        self.dock.setWidget(self.tabs)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.dock)
        self.dock.visibilityChanged.connect(self._dock_visibility)
        self.tabs.currentChanged.connect(lambda i: self.cfg.set("panel_tab", int(i)))

        self.playlist.play_requested.connect(self.play_index)
        self.playlist.add_files_requested.connect(lambda: self.open_file_dialog(append=True))
        self.playlist.add_folder_requested.connect(lambda: self.open_folder_dialog(append=True))
        self.playlist.loop_mode_changed.connect(self._set_loop_mode)
        self.bookmarks.jump_requested.connect(self.seek_to)
        self.bookmarks.add_requested.connect(self.add_bookmark)
        self.bookmarks.items_changed.connect(self._bookmarks_changed)
        self.notes.jump_requested.connect(self.seek_to)
        self.notes.items_changed.connect(lambda items: self._save_list("notes", items))
        self.downloads_panel.play_file.connect(lambda fp: self.open_paths([fp]))
        self.downloads_panel.add_link_requested.connect(lambda: self.open_link_dialog(mode="download"))
        self.downloads.item_done.connect(self._download_done)
        self.adjust.load_sub_requested.connect(self.load_subtitle_dialog)
        self.info_panel.refresh_requested.connect(self.refresh_info)

    def _build_video(self, backend: str) -> None:
        """Create (or re-create) the video widget and the mpv player."""
        if self.player is not None:
            self.player.terminate()
            self.player = None
        if self.video is not None:
            self.video.free_context()
            self.central_layout.removeWidget(self.video)
            self.video.hide()
            self.video.deleteLater()
            self.video = None

        if self.selftest:
            video = NullVideoWidget(self)
            self.central_layout.insertWidget(0, video, 1)
            player = Player(self.cfg, "native", null_output=True)
        elif backend == "native":
            video = NativeVideoWidget(self)
            self.central_layout.insertWidget(0, video, 1)
            player = Player(self.cfg, "native", wid=video.wid())
        else:
            video = GLVideoWidget(self)
            self.central_layout.insertWidget(0, video, 1)
            player = Player(self.cfg, "opengl")
            video.gl_failed.connect(self._gl_failed)
        video.attach(player)
        self.video = video
        self.player = player
        self.backend = "null" if self.selftest else backend
        player.prop_changed.connect(self._on_prop)
        player.file_loaded.connect(self._on_file_loaded)
        player.load_failed.connect(self._on_load_failed)
        player.render_error.connect(self._render_error)
        LOG.write(f"video backend: {self.backend}")

    def _connect_controls(self) -> None:
        c = self.controls
        c.play_clicked.connect(self.toggle_pause)
        c.prev_clicked.connect(self.prev_file)
        c.next_clicked.connect(self.next_file)
        c.stop_clicked.connect(self.stop)
        c.mute_clicked.connect(self.toggle_mute)
        c.volume_changed.connect(lambda v: self.set_volume(v, osd=False))
        c.fullscreen_clicked.connect(self.toggle_fullscreen)
        c.panel_clicked.connect(self.toggle_panel)
        c.screenshot_clicked.connect(self.screenshot)
        c.ab_clicked.connect(self.ab_loop)
        c.mini_clicked.connect(self.toggle_mini)
        c.sleep_clicked.connect(self.sleep_timer_dialog)
        c.seekbar.seek_requested.connect(lambda t, exact: self.seek_to(t, exact, osd=False))
        c.speed_popup.speed_set.connect(lambda s: self.set_speed(s))
        c.speed_popup.pitch_toggled.connect(self._set_pitch)

    def _act(self, text: str, slot, shortcut=None, checkable=False, icon=None, add_to_window=True) -> QAction:
        a = QAction(text, self)
        if icon:
            a.setIcon(icons.icon(icon))
        if shortcut:
            if isinstance(shortcut, (list, tuple)):
                a.setShortcuts([QKeySequence(s) for s in shortcut])
            else:
                a.setShortcut(QKeySequence(shortcut))
        a.setCheckable(checkable)
        if checkable:
            a.toggled.connect(slot)
        else:
            a.triggered.connect(lambda _checked=False: slot())
        if add_to_window:
            self.addAction(a)
        return a

    def _build_actions(self) -> None:
        A = self._act
        skip = int(self.cfg.get("skip_seconds"))
        self.act_open = A("Open file…", self.open_file_dialog, "Ctrl+O", icon="file")
        self.act_open_folder = A("Open folder…", self.open_folder_dialog, "Ctrl+Shift+O", icon="folder")
        self.act_open_link = A("Open link…", self.open_link_dialog, "Ctrl+U", icon="link")
        self.act_download_link = A("Download a link…", lambda: self.open_link_dialog(mode="download"), icon="download")
        self.act_paste = A("Play copied link or file", self.paste_and_play, "Ctrl+V")
        self.act_screenshot = A("Take screenshot", self.screenshot, "S", icon="camera")
        self.act_shots_folder = A("Open screenshots folder", self.open_screenshot_folder)
        self.act_quit = A("Exit", self.close, "Ctrl+Q")

        self.act_play = A("Play / Pause", self.toggle_pause,
                          ["Space", QKeySequence(QKeyCombination(Qt.Key.Key_MediaTogglePlayPause)), QKeySequence(QKeyCombination(Qt.Key.Key_MediaPlay))],
                          icon="play")
        self.act_stop = A("Stop", self.stop, QKeySequence(QKeyCombination(Qt.Key.Key_MediaStop)), icon="stop")
        self.act_prev = A("Previous file", self.prev_file, ["PgUp", QKeySequence(QKeyCombination(Qt.Key.Key_MediaPrevious))], icon="prev")
        self.act_next = A("Next file", self.next_file, ["PgDown", QKeySequence(QKeyCombination(Qt.Key.Key_MediaNext))], icon="next")
        self.act_back = A(f"Back {skip} s\t←", lambda: self.seek_relative(-self.cfg.get("skip_seconds")), add_to_window=False)
        self.act_fwd = A(f"Forward {skip} s\t→", lambda: self.seek_relative(self.cfg.get("skip_seconds")), add_to_window=False)
        self.act_start = A("Go to start", lambda: self.seek_to(0.0), "Home")
        self.act_goto = A("Jump to time…", self.jump_to_time_dialog, "Ctrl+G")
        self.act_faster = A("Faster (+0.1×)", lambda: self.change_speed(0.1), "]")
        self.act_slower = A("Slower (−0.1×)", lambda: self.change_speed(-0.1), "[")
        self.act_faster_fine = A("Slightly faster (+0.01×)", lambda: self.change_speed(0.01), ["}", "Ctrl+]"])
        self.act_slower_fine = A("Slightly slower (−0.01×)", lambda: self.change_speed(-0.01), ["{", "Ctrl+["])
        self.act_speed_reset = A("Normal speed (1×)", lambda: self.set_speed(1.0), "Backspace")
        self.act_speed_exact = A("Set exact speed…", self.exact_speed_dialog, "Ctrl+E")
        self.act_frame_next = A("Next frame", lambda: self.frame_step(False), ".")
        self.act_frame_prev = A("Previous frame", lambda: self.frame_step(True), ",")
        self.act_ab = A("A-B repeat", self.ab_loop, "L", icon="loop")
        self.act_bookmark = A("Bookmark this moment", self.add_bookmark, "Ctrl+B", icon="bookmark")
        self.act_intro = A("Auto-skip intro for this folder…", self.intro_dialog)
        for n in range(10):
            A(f"Jump to {n * 10}%", lambda n=n: self.seek_percent(n * 10), str(n))

        self.act_rotate = A("Rotate 90° clockwise", lambda: self.rotate(90), "R", icon="rotate")
        self.act_rotate_ccw = A("Rotate 90° counter-clockwise", lambda: self.rotate(-90), "Shift+R", icon="rotate_ccw")
        self.act_rotate_180 = A("Rotate 180°", lambda: self.rotate(180))
        self.act_flip_h = A("Flip horizontal (mirror)", self.flip_horizontal, "H", checkable=True)
        self.act_flip_v = A("Flip vertical", self.flip_vertical, "V", checkable=True)
        self.act_portrait = A("Portrait mode", self.toggle_portrait, "P")
        self.act_orient_reset = A("Reset orientation", self.reset_orientation, "Ctrl+Shift+R")
        self.act_fullscreen = A("Fullscreen", self.toggle_fullscreen, ["F", "F11"], icon="fullscreen")
        self.act_escape = A("Leave fullscreen", self.escape_pressed, "Esc")
        self.act_mini = A("Mini player", self.toggle_mini, "Ctrl+M", icon="mini")
        self.act_on_top = A("Always on top", self._set_on_top, "T", checkable=True, icon="pin")
        self.act_zoom_in = A("Zoom in", lambda: self.adjust.step_zoom(0.1), ["Ctrl+=", "Ctrl++"])
        self.act_zoom_out = A("Zoom out", lambda: self.adjust.step_zoom(-0.1), "Ctrl+-")
        self.act_zoom_reset = A("Reset zoom", self.adjust.reset_zoom, "Ctrl+0")
        self.act_frame_counter = A("Show frame counter", self._set_frame_counter, checkable=True, icon="frame")
        self.act_adjust = A("Picture & sound adjustments…", lambda: self.show_panel(TAB_ADJUST), "Ctrl+J", icon="sliders")

        self.act_vol_up = A("Volume up\t↑", lambda: self.change_volume(5), add_to_window=False)
        self.act_vol_down = A("Volume down\t↓", lambda: self.change_volume(-5), add_to_window=False)
        self.act_mute = A("Mute", self.toggle_mute, "M", icon="mute")
        self.act_night = A("Night mode (even out loud and quiet parts)", self._set_night_mode, "N", checkable=True, icon="moon")

        self.act_load_sub = A("Load subtitle file…", self.load_subtitle_dialog, icon="sub")
        self.act_sub_earlier = A("Subtitles earlier (−0.1 s)", lambda: self.nudge_sub_delay(-0.1), "Z")
        self.act_sub_later = A("Subtitles later (+0.1 s)", lambda: self.nudge_sub_delay(0.1), "X")
        self.act_sub_bigger = A("Bigger subtitles", lambda: self.adjust.step_sub_scale(0.1), "Alt+Up")
        self.act_sub_smaller = A("Smaller subtitles", lambda: self.adjust.step_sub_scale(-0.1), "Alt+Down")

        self.act_panel = A("Show side panel", self.toggle_panel, "Ctrl+P", icon="panel")
        self.act_playlist = A("Playlist", lambda: self.show_panel(TAB_PLAYLIST), icon="list")
        self.act_bookmarks = A("Bookmarks", lambda: self.show_panel(TAB_BOOKMARKS), icon="bookmark")
        self.act_notes = A("Notes", lambda: self.show_panel(TAB_NOTES), icon="note")
        self.act_downloads = A("Downloads", lambda: self.show_panel(TAB_DOWNLOADS), "Ctrl+D", icon="download")
        self.act_info = A("Media information", lambda: (self.show_panel(TAB_INFO), self.refresh_info()), "I", icon="info")
        self.act_sleep = A("Sleep timer…", self.sleep_timer_dialog, "Ctrl+T", icon="moon")
        self.act_settings = A("Settings…", self.settings_dialog, "Ctrl+,", icon="gear")
        self.act_update = A("Update link support (yt-dlp)…", self.update_ytdlp)
        self.act_shortcuts = A("Keyboard shortcuts", lambda: ShortcutsDialog(self).exec(), "F1")
        self.act_about = A(f"About {APP_NAME}", lambda: QMessageBox.about(self, f"About {APP_NAME}", about_text()))

        self.loop_group = QActionGroup(self)
        self.loop_actions = {}
        for mode, label in (("none", "Repeat off"), ("all", "Repeat playlist"), ("one", "Repeat this file")):
            a = QAction(label, self, checkable=True)
            a.triggered.connect(lambda _c=False, m=mode: self._set_loop_mode(m))
            self.loop_group.addAction(a)
            self.loop_actions[mode] = a
        self.aspect_group = QActionGroup(self)
        self.aspect_actions = {}
        for key, label in ASPECT_CHOICES:
            a = QAction(label, self, checkable=True)
            a.triggered.connect(lambda _c=False, k=key: self.set_aspect(k))
            self.aspect_group.addAction(a)
            self.aspect_actions[key] = a
        self.aspect_actions["auto"].setChecked(True)
        self.adjust.aspect.currentIndexChanged.connect(
            lambda _i: self.aspect_actions.get(self.adjust.aspect.currentData(), self.aspect_actions["auto"]).setChecked(True))

    def _build_menus(self) -> None:
        mb = self.menuBar()
        m = mb.addMenu("&File")
        for a in (self.act_open, self.act_open_folder, self.act_open_link, self.act_download_link, self.act_paste):
            m.addAction(a)
        self.recent_menu = m.addMenu("Recent")
        self.recent_menu.aboutToShow.connect(self._fill_recent)
        m.addSeparator()
        m.addAction(self.act_screenshot)
        m.addAction(self.act_shots_folder)
        m.addSeparator()
        m.addAction(self.act_quit)

        m = mb.addMenu("&Playback")
        for a in (self.act_play, self.act_stop, self.act_prev, self.act_next):
            m.addAction(a)
        m.addSeparator()
        for a in (self.act_back, self.act_fwd, self.act_start, self.act_goto):
            m.addAction(a)
        m.addSeparator()
        self.speed_menu = m.addMenu(icons.icon("speed"), "Speed")
        self._fill_speed_menu(self.speed_menu)
        m.addAction(self.act_frame_next)
        m.addAction(self.act_frame_prev)
        m.addSeparator()
        m.addAction(self.act_ab)
        m.addAction(self.act_bookmark)
        m.addAction(self.act_intro)
        loop = m.addMenu(icons.icon("repeat"), "Repeat")
        for a in self.loop_actions.values():
            loop.addAction(a)

        m = mb.addMenu("&Video")
        self.rotate_menu = m.addMenu(icons.icon("rotate"), "Rotate && flip")
        self._fill_rotate_menu(self.rotate_menu)
        self.controls.rotate_btn.setMenu(self._make_rotate_menu())
        aspect = m.addMenu("Aspect ratio")
        for a in self.aspect_actions.values():
            aspect.addAction(a)
        zoom = m.addMenu("Zoom")
        for a in (self.act_zoom_in, self.act_zoom_out, self.act_zoom_reset):
            zoom.addAction(a)
        presets = m.addMenu("Picture presets")
        for name in AdjustPanel.PRESETS:
            presets.addAction(name, lambda n=name: self.adjust.apply_preset(n))
        m.addAction(self.act_adjust)
        m.addSeparator()
        for a in (self.act_fullscreen, self.act_mini, self.act_on_top, self.act_frame_counter):
            m.addAction(a)

        m = mb.addMenu("&Audio")
        for a in (self.act_vol_up, self.act_vol_down, self.act_mute, self.act_night):
            m.addAction(a)
        self.audio_menu = m.addMenu("Audio track")
        self.audio_menu.aboutToShow.connect(lambda: self._fill_tracks(self.audio_menu, "audio", "aid"))

        m = mb.addMenu("&Subtitles")
        m.addAction(self.act_load_sub)
        self.sub_menu = m.addMenu("Subtitle track")
        self.sub_menu.aboutToShow.connect(lambda: self._fill_tracks(self.sub_menu, "sub", "sid"))
        for a in (self.act_sub_earlier, self.act_sub_later, self.act_sub_bigger, self.act_sub_smaller):
            m.addAction(a)

        m = mb.addMenu("&Tools")
        for a in (self.act_panel, self.act_playlist, self.act_bookmarks, self.act_notes, self.act_downloads,
                  self.act_info):
            m.addAction(a)
        m.addSeparator()
        m.addAction(self.act_sleep)
        m.addAction(self.act_update)
        m.addAction(self.act_settings)

        m = mb.addMenu("&Help")
        m.addAction(self.act_shortcuts)
        m.addAction(self.act_about)

    def _fill_speed_menu(self, menu: QMenu) -> None:
        for a in (self.act_faster, self.act_slower, self.act_faster_fine, self.act_slower_fine,
                  self.act_speed_reset, self.act_speed_exact):
            menu.addAction(a)
        menu.addSeparator()
        for s in SPEED_PRESETS:
            menu.addAction(f"{s:g}×", lambda v=s: self.set_speed(v))

    def _fill_rotate_menu(self, menu: QMenu) -> None:
        for a in (self.act_rotate, self.act_rotate_ccw, self.act_rotate_180, self.act_flip_h, self.act_flip_v,
                  self.act_portrait, self.act_orient_reset):
            menu.addAction(a)

    def _make_rotate_menu(self) -> QMenu:
        menu = QMenu(self)
        self._fill_rotate_menu(menu)
        return menu

    # ================================================================ startup
    def _after_show(self) -> None:
        if self.cfg.get("always_on_top"):
            self._apply_window_flags()
        if self._pending_args:
            args, self._pending_args = self._pending_args, []
            self.open_paths(args)

    # ================================================================ opening things
    def open_paths(self, items: list[str], append: bool = False) -> None:
        """Open files, folders and links (from the command line, drops, or the panel)."""
        media, subs, links = [], [], []
        had_folder = False
        for raw in items:
            item = (raw or "").strip().strip('"')
            if not item:
                continue
            if is_url(item):
                links.append(item)
            elif os.path.isdir(item):
                had_folder = True
                media += folder_media_files(item)
            elif os.path.isfile(item):
                if is_sub_file(item):
                    subs.append(item)
                else:
                    media.append(os.path.abspath(item))  # mpv tries anything that isn't a subtitle
        if subs and self.current_entry:
            for s in subs:
                self.player.cmd("sub-add", s, "select")
            self.osd("Subtitles loaded")
        if media:
            if append:
                first = self.playlist.add_entries(media)
                if self.current_entry is None:
                    self.play_index(first)
            elif len(media) == 1 and not had_folder:
                # one file: the rest of its folder becomes the playlist (next/previous episode)
                folder = folder_media_files(os.path.dirname(media[0]))
                norm = [os.path.normcase(p) for p in folder]
                if os.path.normcase(media[0]) in norm and is_media_file(media[0]):
                    idx = norm.index(os.path.normcase(media[0]))
                else:
                    folder, idx = [media[0]], 0
                self.playlist.set_entries(folder)
                self.play_index(idx)
            else:
                self.playlist.set_entries(media)
                self.play_index(0)
        for i, link in enumerate(links):
            if i == 0 and not media and not append:
                self.play_link(link)
            else:
                self.playlist.add_entries([link])

    def open_file_dialog(self, append: bool = False) -> None:
        start = os.path.dirname(self.current_entry) if self.current_entry and not is_url(self.current_entry) else ""
        exts = " ".join(f"*.{e}" for e in sorted(MEDIA_EXTS))
        files, _ = QFileDialog.getOpenFileNames(self, "Open video or audio", start,
                                                f"Media files ({exts});;All files (*)")
        if files:
            self.open_paths(files, append=append)

    def open_folder_dialog(self, append: bool = False) -> None:
        d = QFileDialog.getExistingDirectory(self, "Open a folder of videos")
        if d:
            files = folder_media_files(d)
            if not files:
                QMessageBox.information(self, APP_NAME, "No video or audio files were found in that folder.")
                return
            if append:
                self.open_paths(files, append=True)
            else:
                self.playlist.set_entries(files)
                self.play_index(0)

    def load_subtitle_dialog(self) -> None:
        if not self.current_entry:
            QMessageBox.information(self, APP_NAME, "Open a video first, then load its subtitles.")
            return
        start = os.path.dirname(self.current_entry) if not is_url(self.current_entry) else ""
        f, _ = QFileDialog.getOpenFileName(self, "Load subtitles", start,
                                           "Subtitles (*.srt *.ass *.ssa *.vtt *.sub *.idx *.sup *.smi);;All files (*)")
        if f:
            self.player.cmd("sub-add", f, "select")
            self.osd("Subtitles loaded")
            QTimer.singleShot(500, self.adjust.refresh_tracks)

    def open_link_dialog(self, mode: str = "play", url: str = "") -> None:
        dlg = OpenLinkDialog(self.cfg, self, url=url, mode=mode)
        if not dlg.exec() or not dlg.action:
            return
        link = dlg.current_url()
        self.cfg.add_link(link)
        if dlg.action == "download":
            title = (dlg.info or {}).get("title", "")
            self.downloads.add(link, dlg.chosen_quality, dlg.subs.isChecked(), title)
            self.show_panel(TAB_DOWNLOADS)
            self.osd("Added to downloads")
        else:
            self.play_link(link, quality=dlg.chosen_quality, record=dlg.action == "record")

    def paste_and_play(self) -> None:
        cb = QGuiApplication.clipboard()
        md = cb.mimeData()
        if md is not None and md.hasUrls():
            items = [u.toLocalFile() if u.isLocalFile() else u.toString() for u in md.urls()]
            self.open_paths(items)
            return
        text = (cb.text() or "").strip().strip('"')
        if not text:
            return
        if os.path.exists(text):
            self.open_paths([text])
            return
        url = normalize_url(text)
        if url:
            self.play_link(url)
        else:
            self.osd("Clipboard doesn't contain a link or file")

    def play_link(self, url: str, quality: str | None = None, record: bool = False) -> None:
        self.cfg.add_link(url)
        idx = self.playlist.index_of(url)
        if idx < 0:
            idx = self.playlist.add_entries([url])
        self.playlist.set_current(idx)
        self._start_entry(url, quality=quality, record=record)

    def play_index(self, index: int) -> None:
        entry = self.playlist.entry_at(index)
        if entry is None:
            return
        self.playlist.set_current(index)
        self._start_entry(entry)

    def _start_entry(self, entry: str, quality: str | None = None, record: bool = False) -> None:
        self._remember_position()
        self._stop_boost()
        if self._resolver is not None:
            self._resolver.cancel()
            self._resolver = None
        self.current_entry = entry
        self.current_title = display_name(entry)
        self._pos = None
        self._duration = None
        self._has_video = False
        self._intro_rule = self.cfg.get_intro(entry)
        self._intro_done = False
        self._record_path = None
        self.controls.reset_time()
        self.controls.seekbar.set_marks([])
        self.controls.seekbar.set_intro(self._intro_rule)
        self.video.has_video = False
        self._update_title()
        if is_url(entry):
            self._open_url(entry, quality or self.cfg.get("stream_quality"), record)
        else:
            self.video.set_placeholder(True, "Opening…", display_name(entry))
            self._loading = True
            self.player.play(entry)

    def _record_target(self, title: str) -> str:
        out_dir = self.cfg.get("download_dir") or paths.default_download_dir()
        os.makedirs(out_dir, exist_ok=True)
        return unique_path(os.path.join(out_dir, safe_filename(title) + ".mkv"))

    def _open_url(self, url: str, quality: str, record: bool) -> None:
        self._loading = True
        self.video.set_placeholder(True, "Loading link…", url if len(url) < 90 else url[:87] + "…")
        if is_direct_media_url(url) or not ytdl.ytdlp_path():
            rec = self._record_target(display_name(url).rsplit(".", 1)[0]) if record else None
            self._record_path = rec
            self.player.play(url, record_path=rec)
            if rec:
                self.osd("Playing and saving a copy")
            return
        fmt = ytdl.single_file_format(quality) if record else ytdl.stream_format(quality)
        resolver = LinkResolver(url, fmt, self)
        self._resolver = resolver

        def resolved(info: dict, url=url, record=record) -> None:
            if self._resolver is not resolver or self.current_entry != url:
                return
            self._resolver = None
            title = info.get("title") or display_name(url)
            self.current_title = title
            self._update_title()
            target = info.get("video_url") or url
            rec = self._record_target(title) if record else None
            self._record_path = rec
            self.player.play(target, audio_url=None if record else info.get("audio_url"),
                             headers=info.get("headers"), title=title, record_path=rec)
            if rec:
                self.osd("Playing and saving a copy")

        def failed(msg: str, url=url) -> None:
            if self._resolver is not resolver or self.current_entry != url:
                return
            self._resolver = None
            LOG.write(f"yt-dlp could not resolve {url}: {msg}")
            if "isn't supported" in msg:
                # maybe mpv can still play it directly
                self.player.play(url)
            else:
                self._show_error(msg)

        resolver.resolved.connect(resolved)
        resolver.failed.connect(failed)
        resolver.start()

    def _show_error(self, msg: str) -> None:
        self._loading = False
        self.video.set_placeholder(True, "Couldn't play this", msg)
        self.controls.set_playing(False)
        if self.selftest:
            print("PLAYBACK ERROR:", msg)

    # ================================================================ player events
    def _on_prop(self, name: str, value) -> None:  # noqa: C901 - simple dispatch
        if name == "time-pos":
            self._pos = _num_or_none(value)
            if self._pos is not None:
                self.controls.set_time(self._pos)
                self._check_intro()
        elif name == "duration":
            self._duration = _num_or_none(value)
            self.controls.set_time(None, self._duration or 0.0)
        elif name == "pause":
            self._paused = bool(value)
            self.controls.set_playing(not self._paused and not self._idle)
            self._update_autohide()
        elif name == "volume":
            v = int(round(_num_or_none(value) or 0))
            self.cfg.set("volume", v)
            self.controls.set_volume(v, bool(self.cfg.get("muted")))
        elif name == "mute":
            self.cfg.set("muted", bool(value))
            self.controls.set_volume(int(self.cfg.get("volume")), bool(value))
        elif name == "speed":
            s = _num_or_none(value) or 1.0
            self.controls.set_speed(s)
            if not self._boosting and self.current_entry and self.cfg.get("remember_speed") and not self._loading:
                self.cfg.set_speed(self.current_entry, s)
        elif name == "media-title":
            if value and self.current_entry and not is_url(self.current_entry):
                self.current_title = str(value)
                self._update_title()
        elif name == "eof-reached":
            if value is True:
                self._on_eof()
        elif name == "idle-active":
            self._idle = bool(value)
            if self._idle:
                self.controls.set_playing(False)
                if not self._loading and self.current_entry is None:
                    self.video.set_placeholder(True, "Drop a video here",
                                               "Ctrl+O to open a file  ·  Ctrl+U to open a link")
        elif name == "demuxer-cache-time":
            self.controls.seekbar.set_buffered(_num_or_none(value) or 0.0)
        elif name == "paused-for-cache":
            if value:
                self.osd("Buffering…", 60000)
            else:
                self.player.cmd("show-text", "", 1)
        elif name == "video-params":
            if isinstance(value, dict) and value.get("w"):
                w = value.get("dw") or value.get("w")
                h = value.get("dh") or value.get("h")
                self._video_dims = (int(w), int(h))
                self._meta_rotate = int(value.get("rotate") or 0)
                self._has_video = True
                self.video.has_video = True
                self.video.set_placeholder(False)
        elif name == "vid":
            if (value in (False, None, "no") and self.current_entry and not self._loading
                    and not self.player.get("idle-active", True)):
                self._has_video = False
                self.video.has_video = False
                self.video.set_placeholder(True, self.current_title, "Audio only")
        elif name == "track-list":
            self.adjust.refresh_tracks()
        elif name in ("ab-loop-a", "ab-loop-b"):
            a, b = self._ab
            if name == "ab-loop-a":
                a = _num_or_none(value)
            else:
                b = _num_or_none(value)
            self._ab = (a, b)
            self.controls.set_ab(a, b)
        elif name == "estimated-frame-number":
            if self.cfg.get("show_frame_counter") or self._frame_osd:
                fps = _num_or_none(self.player.get("container-fps"))
                n = int(value) if isinstance(value, (int, float)) else None
                if n is not None:
                    text = f"Frame {n}" + (f" · {fps:.3f} fps" if fps else "")
                    if self.cfg.get("show_frame_counter"):
                        self.controls.set_frame_text(text)
                    if self._frame_osd:
                        self._frame_osd = False
                        self.osd(f"Frame {n}  ·  {fmt_time(self._pos)}")

    def _on_file_loaded(self) -> None:
        entry = self.current_entry
        self._loading = False
        self._idle = False
        if entry is None:
            return
        # placeholder: hide it for video, show the title for audio-only files
        vp = self.player.get("video-params")
        if self.player.get("vid", False) and isinstance(vp, dict) and vp.get("w"):
            self._on_prop("video-params", vp)
        elif self.player.get("vid", False):
            self.video.has_video = True
            self._has_video = True
            self.video.set_placeholder(False)
        else:
            self.video.set_placeholder(True, self.current_title, "Audio only")
        # read values directly: property notifications are skipped when the new file
        # happens to have the same duration / size as the previous one
        dur = _num_or_none(self.player.get("duration"))
        self._duration = dur
        self.controls.set_time(None, dur or 0.0)
        self._paused = bool(self.player.get("pause", False))
        self.controls.set_playing(not self._paused)
        # resume / speed
        if self.cfg.get("resume"):
            pos = self.cfg.get_position(entry)
            if pos and pos > 5 and (dur is None or pos < dur - 10):
                self.player.seek(pos, "absolute", exact=True)
                self.osd(f"Continuing from {fmt_time(pos)}  ·  press Home to start over", 2500)
        if self.cfg.get("remember_speed"):
            stored = self.cfg.get_speed(entry)
            if stored:
                self.player.set_speed(stored)
                self.osd(f"Speed {fmt_speed(stored)} (remembered for this file)", 1800)
        self.player.set("loop-file", "inf" if self.cfg.get("loop_mode") == "one" else "no")
        # per-file memory
        self.bookmarks.set_items(self.cfg.get_list(entry, "bookmarks"))
        self.notes.set_items(self.cfg.get_list(entry, "notes"))
        self.notes.title = self.current_title
        self.controls.seekbar.set_marks([b.get("t", 0) for b in self.bookmarks.items()])
        self.adjust.refresh_from_player()
        self.cfg.add_recent(entry)
        self._update_title()
        if self.tabs.currentIndex() == TAB_INFO and self.dock.isVisible():
            QTimer.singleShot(400, self.refresh_info)
        if self.backend == "opengl":
            QTimer.singleShot(4000, self._check_gl_frames)

    def _on_load_failed(self, msg: str) -> None:
        if self._resolver is not None:
            return
        name = display_name(self.current_entry) if self.current_entry else ""
        self._show_error(f"{msg}\n{name}")

    def _on_eof(self) -> None:
        if self.current_entry:
            self.cfg.set_position(self.current_entry, None)
        if self._sleep and self._sleep["mode"] == "file":
            self._fire_sleep()
            return
        if self.cfg.get("loop_mode") == "one":
            return
        nxt = self.playlist.next_index(wrap=self.cfg.get("loop_mode") == "all")
        if nxt >= 0 and nxt != self.playlist.current_index():
            self.play_index(nxt)
        elif nxt >= 0 and self.cfg.get("loop_mode") == "all":
            self.seek_to(0.0)
            self.player.set("pause", False)
        else:
            if self._sleep and self._sleep["mode"] == "playlist":
                self._fire_sleep()
            self._update_autohide()

    def _check_intro(self) -> None:
        rule = self._intro_rule
        if not rule or self._intro_done or self._pos is None:
            return
        start, end = rule
        if start <= self._pos < end - 0.5:
            self._intro_done = True
            self.player.seek(end, "absolute", exact=False)
            self.osd("Skipped intro")
        elif self._pos >= end:
            self._intro_done = True

    # ================================================================ video backend safety net
    def _gl_failed(self, msg: str) -> None:
        LOG.write(f"OpenGL video failed ({msg}); switching to compatibility mode")
        QTimer.singleShot(0, lambda: self._switch_backend("native"))

    def _render_error(self, msg: str) -> None:
        if self.backend == "opengl" and self.video is not None and self.video.frames == 0 and self._has_video:
            self._gl_failed(msg)

    def _check_gl_frames(self) -> None:
        if (self.backend == "opengl" and self._has_video and self.video is not None and self.video.frames == 0
                and self.isVisible() and not self.isMinimized() and self.video.isVisible()):
            self._gl_failed("no frames were drawn")

    def _switch_backend(self, backend: str) -> None:
        if self.backend == backend or time.monotonic() - self._last_backend_switch < 5:
            return
        self._last_backend_switch = time.monotonic()
        entry, pos = self.current_entry, self._pos
        self.cfg.set("video_backend", backend)
        self._build_video(backend)
        if entry:
            if pos and not is_url(entry):
                self.cfg.set_position(entry, pos)
            self._start_entry(entry)
        self.osd("Switched to compatibility video mode")

    # ================================================================ playback commands
    def osd(self, text: str, ms: int = 1300) -> None:
        if self.player is not None:
            self.player.osd(text, ms)

    def toggle_pause(self) -> None:
        if self.current_entry is None:
            self.open_file_dialog()
            return
        if self._idle and not self._loading:
            self._start_entry(self.current_entry)
            return
        self.player.toggle_pause()
        self._show_controls()

    def stop(self) -> None:
        self._remember_position()
        if self._resolver is not None:
            self._resolver.cancel()
            self._resolver = None
        self.player.stop()
        self._loading = False
        self.controls.reset_time()
        self.video.has_video = False
        self.video.set_placeholder(True, "Stopped", "Press Space to play again")

    def next_file(self) -> None:
        nxt = self.playlist.next_index(wrap=self.cfg.get("loop_mode") == "all")
        if nxt >= 0:
            self.play_index(nxt)
        else:
            self.osd("This is the last file")

    def prev_file(self) -> None:
        if self._pos and self._pos > 5:
            self.seek_to(0.0)
            return
        prv = self.playlist.prev_index(wrap=self.cfg.get("loop_mode") == "all")
        if prv >= 0:
            self.play_index(prv)
        else:
            self.seek_to(0.0)

    def seek_relative(self, seconds: float) -> None:
        if self.current_entry is None or self._idle:
            return
        self.player.seek(seconds, "relative", exact=True)
        target = (self._pos or 0) + seconds
        if self._duration:
            target = max(0.0, min(self._duration, target))
        sign = "+" if seconds > 0 else "−"
        self.osd(f"{sign}{abs(seconds):g} s   {fmt_time(max(0.0, target))} / {fmt_time(self._duration)}")

    def seek_to(self, seconds: float, exact: bool = True, osd: bool = True) -> None:
        if self.current_entry is None or self._idle:
            return
        self.player.seek(max(0.0, float(seconds)), "absolute", exact=exact)
        if osd:
            self.osd(f"{fmt_time(seconds)} / {fmt_time(self._duration)}")

    def seek_percent(self, pct: float) -> None:
        if self._duration:
            self.seek_to(self._duration * pct / 100.0)

    def frame_step(self, back: bool) -> None:
        if self._idle:
            return
        self._frame_osd = True
        self.player.frame_step(back)

    def set_speed(self, speed: float, osd: bool = True) -> None:
        s = self.player.set_speed(speed)
        if osd:
            self.osd(f"Speed {fmt_speed(s)}")

    def change_speed(self, delta: float) -> None:
        cur = _num_or_none(self.player.get("speed")) or 1.0
        self.set_speed(round(cur + delta, 2))

    def _set_pitch(self, on: bool) -> None:
        self.cfg.set("pitch_correction", bool(on))
        self.player.set("audio-pitch-correction", bool(on))
        self.osd("Pitch correction " + ("on" if on else "off"))

    def set_volume(self, vol: int, osd: bool = True) -> None:
        v = self.player.set_volume(vol)
        self.cfg.set("volume", v)
        if v > 0 and self.player.get("mute", False):
            self.player.set("mute", False)
        if osd:
            self.osd(f"Volume {v}%" + ("  (boosted)" if v > 100 else ""))

    def change_volume(self, delta: int) -> None:
        # read mpv directly: the property notification may not have arrived yet
        cur = _num_or_none(self.player.get("volume"))
        self.set_volume((cur if cur is not None else int(self.cfg.get("volume"))) + delta)

    def toggle_mute(self) -> None:
        muted = not bool(self.player.get("mute", False))
        self.player.set("mute", muted)
        self.osd("Muted" if muted else f"Volume {int(self.cfg.get('volume'))}%")

    def ab_loop(self) -> None:
        if self._idle:
            return
        a, b = self._ab
        self.player.cmd("ab-loop")
        if a is None:
            self.osd(f"Loop start (A) at {fmt_time(self._pos)} — press L again to set B", 2500)
        elif b is None:
            self.osd(f"Repeating {fmt_time(a)} → {fmt_time(self._pos)}  ·  L to turn off", 2500)
        else:
            self.osd("A-B repeat off")

    def _set_loop_mode(self, mode: str) -> None:
        self.cfg.set("loop_mode", mode)
        self.playlist.set_loop_mode(mode)
        if mode in self.loop_actions:
            self.loop_actions[mode].setChecked(True)
        if self.player is not None:
            self.player.set("loop-file", "inf" if mode == "one" else "no")
        self.osd({"none": "Repeat off", "all": "Repeat playlist", "one": "Repeat this file"}[mode])

    # ---- orientation / picture
    def rotate(self, delta: int) -> None:
        r = self.player.set_rotation(self.player.rotation + delta)
        self.osd(f"Rotation {r}°")

    def flip_horizontal(self, on: bool) -> None:
        self.player.set_flip(horizontal=on)
        self.osd("Mirrored" if on else "Mirror off")

    def flip_vertical(self, on: bool) -> None:
        self.player.set_flip(vertical=on)
        self.osd("Flipped vertically" if on else "Vertical flip off")

    def reset_orientation(self) -> None:
        self.player.reset_orientation()
        for a in (self.act_flip_h, self.act_flip_v):
            a.blockSignals(True)
            a.setChecked(False)
            a.blockSignals(False)
        self.osd("Orientation reset")
        self._fit_window_to_video()

    def _displayed_dims(self):
        if not self._video_dims:
            return None
        w, h = self._video_dims
        if (self._meta_rotate + self.player.rotation) % 180 == 90:
            w, h = h, w
        return w, h

    def toggle_portrait(self) -> None:
        dims = self._displayed_dims()
        if dims is None:
            self.osd("Open a video first")
            return
        w, h = dims
        if w > h:
            self.player.set_rotation(self.player.rotation + 90)
            self.osd("Portrait mode")
        else:
            self.player.set_rotation(self.player.rotation - 90)
            self.osd("Landscape mode")
        QTimer.singleShot(150, self._fit_window_to_video)

    def _fit_window_to_video(self) -> None:
        if self._fullscreen or self._mini or self.isMaximized():
            return
        dims = self._displayed_dims()
        if not dims:
            return
        w, h = dims
        screen = self.screen().availableGeometry()
        chrome_h = self.height() - self.video.height()
        chrome_w = self.width() - self.video.width()
        max_w = screen.width() * 0.9 - chrome_w
        max_h = screen.height() * 0.88 - chrome_h
        scale = min(max_w / w, max_h / h, 1.0 if w > 640 else 2.0)
        vw, vh = int(w * scale), int(h * scale)
        new_w = max(self.minimumWidth(), vw + chrome_w)
        new_h = max(self.minimumHeight(), vh + chrome_h)
        self.resize(new_w, new_h)
        self.move(screen.center().x() - new_w // 2, screen.center().y() - new_h // 2)

    def set_aspect(self, key: str) -> None:
        self.player.set_aspect(key)
        self.adjust.set_aspect_choice(key)
        self.osd("Aspect: " + dict(ASPECT_CHOICES).get(key, key))

    def _set_night_mode(self, on: bool) -> None:
        self.player.set_night_mode(on)
        self.adjust.night.blockSignals(True)
        self.adjust.night.setChecked(on)
        self.adjust.night.blockSignals(False)
        self.osd("Night mode on" if on else "Night mode off")

    def nudge_sub_delay(self, delta: float) -> None:
        v = self.adjust.nudge_sub_delay(delta)
        self.osd(f"Subtitle delay {v:+.1f} s")

    def screenshot(self) -> None:
        if self.current_entry is None or not self._has_video:
            self.osd("Nothing to capture")
            return
        folder = self.cfg.get("screenshot_dir") or paths.default_screenshot_dir()
        os.makedirs(folder, exist_ok=True)
        stem = safe_filename(os.path.splitext(self.current_title)[0], 60)
        stamp = fmt_time(self._pos or 0, True).replace(":", "-")
        path = unique_path(os.path.join(folder, f"{stem} {stamp}.png"))
        if self.player.cmd("screenshot-to-file", path, "subtitles"):
            self.osd(f"Screenshot saved: {os.path.basename(path)}", 2000)
            self._last_screenshot = path

    def open_screenshot_folder(self) -> None:
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices

        folder = self.cfg.get("screenshot_dir") or paths.default_screenshot_dir()
        os.makedirs(folder, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(folder))

    # ---- bookmarks / notes
    def add_bookmark(self) -> None:
        if self.current_entry is None or self._pos is None:
            self.osd("Open a video first")
            return
        items = self.bookmarks.items()
        items.append({"t": round(self._pos, 2), "label": f"Bookmark {len(items) + 1}"})
        self.bookmarks.set_items(items)
        self._bookmarks_changed(self.bookmarks.items())
        self.osd(f"Bookmarked {fmt_time(self._pos)}  ·  rename it in the Marks tab")

    def _bookmarks_changed(self, items: list) -> None:
        self._save_list("bookmarks", items)
        self.controls.seekbar.set_marks([b.get("t", 0) for b in items])

    def _save_list(self, name: str, items: list) -> None:
        if self.current_entry:
            self.cfg.set_list(self.current_entry, name, items)

    def _remember_position(self) -> None:
        if not self.current_entry or not self.cfg.get("resume"):
            return
        pos, dur = self._pos, self._duration
        if pos is None:
            return
        if pos > 10 and (not dur or pos < dur - 15):
            self.cfg.set_position(self.current_entry, pos)
        elif dur and pos >= dur - 15:
            self.cfg.set_position(self.current_entry, None)

    # ================================================================ dialogs
    def jump_to_time_dialog(self) -> None:
        if self._idle:
            return
        text, ok = QInputDialog.getText(self, "Jump to time", "Time (e.g. 1:23, 1:02:03, 90s or 50%):",
                                        QLineEdit.EchoMode.Normal, fmt_time(self._pos))
        if not ok or not text.strip():
            return
        t = text.strip()
        if t.endswith("%"):
            try:
                self.seek_percent(float(t[:-1]))
            except ValueError:
                pass
            return
        secs = parse_time(t)
        if secs is not None:
            self.seek_to(secs)

    def exact_speed_dialog(self) -> None:
        cur = _num_or_none(self.player.get("speed")) or 1.0
        val, ok = QInputDialog.getDouble(self, "Exact speed", "Speed (0.05 – 8.00):", cur, 0.05, 8.0, 2)
        if ok:
            self.set_speed(val)

    def intro_dialog(self) -> None:
        if not self.current_entry or is_url(self.current_entry):
            QMessageBox.information(self, APP_NAME, "Auto-skip intro works for videos saved on your PC.\n"
                                                    "Open an episode from the folder first.")
            return
        dlg = IntroSkipDialog(self._pos or 0.0, self.cfg.get_intro(self.current_entry),
                              os.path.dirname(self.current_entry), self)
        if not dlg.exec():
            return
        if dlg.remove:
            self.cfg.set_intro(self.current_entry, None, None)
            self.osd("Intro skip removed for this folder")
        elif dlg.result_rule:
            self.cfg.set_intro(self.current_entry, *dlg.result_rule)
            self.osd(f"Intro {fmt_time(dlg.result_rule[0])}–{fmt_time(dlg.result_rule[1])} will be skipped")
        self._intro_rule = self.cfg.get_intro(self.current_entry)
        self._intro_done = True  # don't jump right now
        self.controls.seekbar.set_intro(self._intro_rule)

    def settings_dialog(self) -> None:
        dlg = SettingsDialog(self.cfg, self)
        if not dlg.exec():
            return
        ch = dlg.changed
        if "pitch_correction" in ch:
            self.player.set("audio-pitch-correction", bool(self.cfg.get("pitch_correction")))
            self.controls.speed_popup.set_pitch(bool(self.cfg.get("pitch_correction")))
        if "download_dir" in ch:
            self.downloads_panel.refresh_folder()
        if {"skip_seconds"} & ch:
            s = int(self.cfg.get("skip_seconds"))
            self.act_back.setText(f"Back {s} s\t←")
            self.act_fwd.setText(f"Forward {s} s\t→")
        self._update_autohide()
        self.cfg.save()
        if ch & SettingsDialog.RESTART_KEYS:
            QMessageBox.information(self, APP_NAME, "Some changes will apply the next time you start Strimo.")

    def sleep_timer_dialog(self) -> None:
        dlg = SleepTimerDialog(self._sleep_text(), self)
        if not dlg.exec():
            return
        if dlg.turn_off:
            self._sleep = None
            self.sleep_timer.stop()
            self.controls.set_sleep_text(None)
            self.osd("Sleep timer off")
            return
        d = dlg.result_data
        if not d:
            return
        self._sleep = dict(d)
        if d["mode"] == "minutes":
            self._sleep["deadline"] = time.monotonic() + d["minutes"] * 60
            self.sleep_timer.start()
        self._sleep_tick()
        self.osd("Sleep timer set: " + (self._sleep_text() or ""))

    def _sleep_text(self):
        s = self._sleep
        if not s:
            return None
        label = dict(SleepTimerDialog.ACTIONS).get(s["action"], s["action"])
        if s["mode"] == "minutes":
            left = max(0, int(s["deadline"] - time.monotonic()))
            return f"{label} in {left // 60}:{left % 60:02d}"
        return f"{label} when the {'video' if s['mode'] == 'file' else 'playlist'} ends"

    def _sleep_tick(self) -> None:
        s = self._sleep
        if not s:
            self.sleep_timer.stop()
            self.controls.set_sleep_text(None)
            return
        if s["mode"] == "minutes":
            left = int(s["deadline"] - time.monotonic())
            if left <= 0:
                self._fire_sleep()
                return
            self.controls.set_sleep_text(f"⏾ {left // 60}:{left % 60:02d}")
        else:
            self.controls.set_sleep_text("⏾ end of " + ("video" if s["mode"] == "file" else "list"))

    def _fire_sleep(self) -> None:
        s = self._sleep
        self._sleep = None
        self.sleep_timer.stop()
        self.controls.set_sleep_text(None)
        if not s:
            return
        action = s["action"]
        if action == "pause":
            self.player.set("pause", True)
        elif action == "stop":
            self.stop()
        elif action == "quit":
            self.close()
        elif action in ("sleep", "shutdown"):
            self.player.set("pause", True)
            what = "Putting the PC to sleep" if action == "sleep" else "Shutting down the PC"
            if self.selftest:
                return
            dlg = CountdownDialog(what, 30, self)
            if dlg.exec():
                self._remember_position()
                self.cfg.save()
                if os.name == "nt":
                    cmd = (["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"] if action == "sleep"
                           else ["shutdown", "/s", "/t", "0"])
                    subprocess.Popen(cmd, creationflags=CREATE_NO_WINDOW)

    def update_ytdlp(self) -> None:
        if not ytdl.ytdlp_path():
            QMessageBox.warning(self, APP_NAME, "yt-dlp wasn't found. Reinstall Strimo to restore link support.")
            return
        r = QMessageBox.question(
            self, "Update link support",
            "This downloads the newest yt-dlp (about 18 MB) so that video sites keep working.\n\nUpdate now?")
        if r != QMessageBox.StandardButton.Yes:
            return
        runner = CommandRunner(ytdl.update_args(), self)
        self._runners.append(runner)
        self.osd("Updating link support…", 5000)

        def done(code: int, out: str) -> None:
            if runner in self._runners:
                self._runners.remove(runner)
            tail = "\n".join(out.strip().splitlines()[-6:])
            if code == 0:
                QMessageBox.information(self, APP_NAME, "Link support is up to date.\n\n" + tail)
            else:
                QMessageBox.warning(self, APP_NAME, "The update didn't finish.\n\n" + tail)

        runner.done.connect(done)
        runner.start()

    def _download_done(self, item) -> None:
        self.osd(f"Download finished: {item.name}", 2500)
        QApplication.alert(self, 3000)

    # ================================================================ panel / tracks / info
    def show_panel(self, tab: int) -> None:
        if self._mini:
            self.toggle_mini()
        if self._fullscreen:
            self.toggle_fullscreen()
        self.dock.show()
        self.tabs.setCurrentIndex(tab)
        self.dock.raise_()

    def toggle_panel(self) -> None:
        if self.dock.isVisible():
            self.dock.hide()
        else:
            if self._fullscreen:
                self.toggle_fullscreen()
            self.dock.show()

    def _dock_visibility(self, visible: bool) -> None:
        self.controls.panel_btn.setChecked(visible)
        if not self._fullscreen and not self._mini:
            self.cfg.set("panel_visible", bool(visible))

    def refresh_info(self) -> None:
        self.info_panel.show_info(self.player.media_info() if self.current_entry and not self._idle else None)

    def _fill_tracks(self, menu: QMenu, kind: str, prop: str) -> None:
        menu.clear()
        group = QActionGroup(menu)
        off = menu.addAction("Off")
        off.setCheckable(True)
        group.addAction(off)
        any_selected = False
        for t in self.player.tracks(kind):
            a = menu.addAction(self.player.track_label(t))
            a.setCheckable(True)
            a.setChecked(bool(t.get("selected")))
            any_selected = any_selected or bool(t.get("selected"))
            a.triggered.connect(lambda _c=False, tid=t.get("id"): (self.player.set(prop, str(tid)),
                                                                  QTimer.singleShot(200, self.adjust.refresh_tracks)))
            group.addAction(a)
        off.setChecked(not any_selected)
        off.triggered.connect(lambda _c=False: (self.player.set(prop, "no"),
                                                QTimer.singleShot(200, self.adjust.refresh_tracks)))
        if kind == "sub":
            menu.addSeparator()
            menu.addAction(self.act_load_sub)

    def _fill_recent(self) -> None:
        self.recent_menu.clear()
        recent = self.cfg.get("recent", [])
        for entry in recent:
            label = display_name(entry)
            a = self.recent_menu.addAction(("🌐  " if is_url(entry) else "") + label)
            a.setToolTip(entry)
            a.triggered.connect(lambda _c=False, e=entry: self.play_link(e) if is_url(e) else self.open_paths([e]))
        if not recent:
            a = self.recent_menu.addAction("Nothing yet")
            a.setEnabled(False)
        else:
            self.recent_menu.addSeparator()
            self.recent_menu.addAction("Clear list", lambda: self.cfg.set("recent", []))

    def _update_title(self) -> None:
        if self.current_entry:
            self.setWindowTitle(f"{self.current_title} — {APP_NAME}")
        else:
            self.setWindowTitle(APP_NAME)

    def _set_frame_counter(self, on: bool) -> None:
        self.cfg.set("show_frame_counter", bool(on))
        if not on:
            self.controls.set_frame_text(None)
        else:
            n = self.player.get("estimated-frame-number") if self.player else None
            self.controls.set_frame_text(f"Frame {n}" if n is not None else "Frame –")

    # ================================================================ window modes
    def _apply_window_flags(self) -> None:
        frameless = self._mini
        on_top = self._mini or bool(self.cfg.get("always_on_top"))
        base = self.windowFlags() & ~(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        flags = base
        if frameless:
            flags |= Qt.WindowType.FramelessWindowHint
        if on_top:
            flags |= Qt.WindowType.WindowStaysOnTopHint
        handle = self.windowHandle()
        if handle is not None and os.name == "nt":
            # change the native window in place (keeps the video surface alive)
            handle.setFlags(flags)
            if not handle.isVisible():
                handle.setVisible(True)
        else:
            geo = self.geometry()
            self.setWindowFlags(flags)
            self.setGeometry(geo)
            self.show()

    def _set_on_top(self, on: bool) -> None:
        self.cfg.set("always_on_top", bool(on))
        self._apply_window_flags()
        self.osd("Always on top" if on else "Always on top: off")

    def toggle_fullscreen(self) -> None:
        if self._mini:
            self.toggle_mini()
            return
        if self._fullscreen:
            self._fullscreen = False
            restore = self._fs_restore or {}
            if restore.get("maximized"):
                self.showMaximized()
            else:
                self.showNormal()
            self.menuBar().show()
            if restore.get("panel"):
                self.dock.show()
        else:
            self._fs_restore = {"maximized": self.isMaximized(), "panel": self.dock.isVisible()}
            self._fullscreen = True
            self.menuBar().hide()
            self.dock.hide()
            self.showFullScreen()
        self.controls.set_fullscreen(self._fullscreen)
        self._show_controls()

    def toggle_mini(self) -> None:
        if self._fullscreen:
            self.toggle_fullscreen()
        if not self._mini:
            self._mini_restore = {
                "geometry": self.saveGeometry(),
                "panel": self.dock.isVisible(),
                "maximized": self.isMaximized(),
            }
            self._mini = True
            self.menuBar().hide()
            self.dock.hide()
            if self.isMaximized():
                self.showNormal()
            self._apply_window_flags()
            dims = self._displayed_dims() or (16, 9)
            w = 440
            h = int(w * dims[1] / max(1, dims[0]))
            h = max(150, min(h, 560))
            self.setMinimumSize(QSize(220, 124))
            screen = self.screen().availableGeometry()
            self.resize(w, h)
            self.move(screen.right() - w - 24, screen.bottom() - h - 24)
            self.osd("Mini player · drag to move · double-click to go back", 2000)
        else:
            self._mini = False
            restore = self._mini_restore or {}
            self.setMinimumSize(QSize(480, 300))
            self._apply_window_flags()
            if restore.get("geometry") is not None:
                self.restoreGeometry(restore["geometry"])
            if restore.get("maximized"):
                self.showMaximized()
            self.menuBar().show()
            if restore.get("panel"):
                self.dock.show()
        self._show_controls()

    def escape_pressed(self) -> None:
        if self._mini:
            self.toggle_mini()
        elif self._fullscreen:
            self.toggle_fullscreen()

    # ---- auto-hide controls
    def _should_autohide(self) -> bool:
        if self.current_entry is None or self._idle:
            return False
        if self._fullscreen or self._mini:
            return True
        return bool(self.cfg.get("autohide_windowed")) and not self._paused

    def _update_autohide(self) -> None:
        if self._should_autohide():
            self.hide_timer.start()
        else:
            self.hide_timer.stop()
            self._show_controls(restart=False)

    def _show_controls(self, restart: bool = True) -> None:
        if not self.controls.isVisible():
            self.controls.show()
        if self.video is not None:
            self.video.unsetCursor()
        if restart and self._should_autohide():
            self.hide_timer.start()

    def _auto_hide(self) -> None:
        if not self._should_autohide():
            return
        if self.controls.underMouse() or QApplication.activePopupWidget() is not None:
            self.hide_timer.start()
            return
        if self._mini or self._fullscreen or self.cfg.get("autohide_windowed"):
            self.controls.hide()
        if self.video is not None and self.video.underMouse():
            self.video.setCursor(Qt.CursorShape.BlankCursor)

    # ================================================================ mouse on video
    def video_mouse_press(self, e) -> None:
        if e.button() == Qt.MouseButton.LeftButton:
            self._press_pos = e.globalPosition().toPoint()
            self._dragged = False
            if self._mini:
                self._drag_offset = self._press_pos - self.frameGeometry().topLeft()

    def video_mouse_move(self, e) -> None:
        self._show_controls()
        if self._mini and self._drag_offset is not None and e.buttons() & Qt.MouseButton.LeftButton:
            gp = e.globalPosition().toPoint()
            if self._press_pos is not None and (gp - self._press_pos).manhattanLength() > 4:
                self._dragged = True
            if self._dragged:
                self.move(gp - self._drag_offset)

    def video_mouse_release(self, e) -> None:
        if e.button() != Qt.MouseButton.LeftButton:
            return
        self._drag_offset = None
        if self._ignore_release:
            self._ignore_release = False
            return
        if not self._dragged:
            self.click_timer.start()
        self._dragged = False

    def video_double_click(self, _e) -> None:
        self.click_timer.stop()
        self._ignore_release = True
        self.toggle_fullscreen()

    def _single_click(self) -> None:
        if self.current_entry is None:
            self.open_file_dialog()
        else:
            self.toggle_pause()

    def video_wheel(self, e, width: int) -> None:
        steps = e.angleDelta().y() / 120.0
        if not steps:
            return
        if self.cfg.get("wheel_gestures") and e.position().x() < width / 2 and self._has_video:
            s = self.adjust.sliders["brightness"]
            s.setValue(int(s.value() + 3 * steps))
            self.osd(f"Brightness {s.value():+d}")
        else:
            self.change_volume(int(round(5 * steps)))

    def video_context_menu(self, global_pos: QPoint) -> None:
        m = QMenu(self)
        m.addAction(self.act_play)
        m.addAction(self.act_open)
        m.addAction(self.act_open_link)
        m.addSeparator()
        speed = m.addMenu(icons.icon("speed"), "Speed")
        self._fill_speed_menu(speed)
        rot = m.addMenu(icons.icon("rotate"), "Rotate && flip")
        self._fill_rotate_menu(rot)
        audio = m.addMenu("Audio track")
        self._fill_tracks(audio, "audio", "aid")
        subs = m.addMenu("Subtitles")
        self._fill_tracks(subs, "sub", "sid")
        m.addSeparator()
        for a in (self.act_screenshot, self.act_bookmark, self.act_ab, self.act_fullscreen, self.act_mini,
                  self.act_on_top, self.act_panel, self.act_info, self.act_settings):
            m.addAction(a)
        m.exec(global_pos)

    # ================================================================ keyboard (arrows) & events
    @staticmethod
    def _focus_is_text() -> bool:
        fw = QApplication.focusWidget()
        if isinstance(fw, (QLineEdit, QTextEdit, QPlainTextEdit, QAbstractSpinBox)):
            return True
        return isinstance(fw, QComboBox) and fw.isEditable()

    def eventFilter(self, obj, ev):
        t = ev.type()
        if t in (QEvent.Type.KeyPress, QEvent.Type.KeyRelease):
            if (isinstance(obj, QWidget) and obj.window() is self and QApplication.activePopupWidget() is None
                    and QApplication.activeModalWidget() is None and not self._focus_is_text()):
                key = ev.key()
                mods = ev.modifiers() & ~Qt.KeyboardModifier.KeypadModifier
                if key in (Qt.Key.Key_Left, Qt.Key.Key_Right, Qt.Key.Key_Up, Qt.Key.Key_Down) and mods in (
                        Qt.KeyboardModifier.NoModifier, Qt.KeyboardModifier.ShiftModifier):
                    shift = mods == Qt.KeyboardModifier.ShiftModifier
                    if t == QEvent.Type.KeyPress:
                        self._arrow_press(key, shift, ev.isAutoRepeat())
                    else:
                        self._arrow_release(key, shift, ev.isAutoRepeat())
                    return True
                if t == QEvent.Type.KeyPress:
                    self._show_controls()
        return super().eventFilter(obj, ev)

    def _arrow_press(self, key, shift: bool, repeat: bool) -> None:
        skip = float(self.cfg.get("skip_seconds"))
        long_skip = float(self.cfg.get("long_skip_seconds"))
        if key == Qt.Key.Key_Up:
            self.change_volume(1 if shift else 5)
        elif key == Qt.Key.Key_Down:
            self.change_volume(-1 if shift else -5)
        elif key == Qt.Key.Key_Left:
            self.seek_relative(-(long_skip if shift else skip))
        elif key == Qt.Key.Key_Right:
            if shift:
                self.seek_relative(long_skip)
            elif not self.cfg.get("hold_to_boost") or self._idle:
                self.seek_relative(skip)
            elif not repeat:
                self._right_down_at = time.monotonic()
            elif not self._boosting and self._right_down_at is not None and \
                    time.monotonic() - self._right_down_at > 0.35:
                self._start_boost()

    def _arrow_release(self, key, shift: bool, repeat: bool) -> None:
        if key != Qt.Key.Key_Right or repeat or shift:
            return
        if not self.cfg.get("hold_to_boost") or self._idle:
            return
        if self._boosting:
            self._stop_boost()
        elif self._right_down_at is not None:
            self.seek_relative(float(self.cfg.get("skip_seconds")))
        self._right_down_at = None

    def _start_boost(self) -> None:
        if self._paused or self._idle:
            return
        self._boosting = True
        self._boost_prev = _num_or_none(self.player.get("speed")) or 1.0
        self.player.set_speed(float(self.cfg.get("boost_speed")))
        self.osd(f"» {fmt_speed(self.cfg.get('boost_speed'))}  (release to go back)", 60000)

    def _stop_boost(self) -> None:
        if not self._boosting:
            return
        self._boosting = False
        self.player.set_speed(self._boost_prev)
        self.osd(f"Speed {fmt_speed(self._boost_prev)}", 800)
        self._right_down_at = None

    def changeEvent(self, e):
        if e.type() == QEvent.Type.ActivationChange and not self.isActiveWindow():
            self._stop_boost()
            self._right_down_at = None
        super().changeEvent(e)

    # ---- drag & drop
    def dragEnterEvent(self, e):
        md = e.mimeData()
        if md.hasUrls() or md.hasText():
            e.acceptProposedAction()

    def dropEvent(self, e):
        md = e.mimeData()
        items = []
        if md.hasUrls():
            for u in md.urls():
                items.append(u.toLocalFile() if u.isLocalFile() else u.toString())
        elif md.hasText():
            url = normalize_url(md.text())
            if url:
                items.append(url)
        if items:
            e.acceptProposedAction()
            self.activateWindow()
            self.open_paths(items)

    # ================================================================ saving / closing
    def _periodic_save(self) -> None:
        if not self._idle and self._pos is not None:
            self._remember_position()
        if self.cfg.dirty:
            self.cfg.save()

    def closeEvent(self, e):
        if self.downloads.has_active() and not self.selftest:
            r = QMessageBox.question(
                self, APP_NAME, "A download is still running.\n\nClose Strimo anyway? "
                                "It will be paused and you can resume it next time.")
            if r != QMessageBox.StandardButton.Yes:
                e.ignore()
                return
        self._remember_position()
        if self._mini:
            self.toggle_mini()
        if self._fullscreen:
            self.toggle_fullscreen()
        if not self.selftest:
            self.cfg.set("window_geometry", self.saveGeometry().toBase64().data().decode("ascii"))
        self.cfg.set("show_remaining", bool(self.controls.show_remaining))
        self.downloads.shutdown()
        for r in list(self._runners):
            try:
                r.proc.kill()
            except Exception:  # noqa: BLE001
                pass
        if self._resolver is not None:
            self._resolver.cancel()
        QApplication.instance().removeEventFilter(self)
        if self.video is not None:
            self.video.free_context()
        if self.player is not None:
            self.player.terminate()
        self.cfg.save()
        super().closeEvent(e)

    # helper used by the self-test
    def current_cursor_pos(self):
        return QCursor.pos()
