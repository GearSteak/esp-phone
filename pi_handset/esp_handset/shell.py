"""Digivice shell — two-row home → radial submenu → app (240×320 default)."""

from __future__ import annotations

from datetime import datetime
from typing import Callable, Dict, List, Optional

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMainWindow,
    QPlainTextEdit,
    QStackedWidget,
    QTextEdit,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)

from esp_handset import digi_nav
from esp_handset import theme as handset_theme
from esp_handset.digivice_home import DigiviceHome
from esp_handset.radial_menu import RadialMenu
from esp_handset.shell_data import (
    CALLS_APPS,
    CLOCK_APPS,
    COMM_APPS,
    FOLDER_MAP,
    GAMES_APPS,
    HOME_APPS,
    MEDIA_APPS,
    SETTINGS_APPS,
    SETUP_APPS,
    SMS_APPS,
    TOOLS_APPS,
    AppEntry,
)
from esp_handset.toasts import ToastHost

_GAME_PAGES = {e.key for e in GAMES_APPS}
# Live boards (timers + own keys) — not button-driven solitaire/uno
_ARCADE_PAGES = {"snake", "pong", "tetris"}
# In-UI GB (PyBoy) also eats pad keys while playing
_GAMEPAD_PAGES = _ARCADE_PAGES | {"gb"}

__all__ = [
    "PhoneShell",
    "AppEntry",
    "HOME_APPS",
    "CALLS_APPS",
    "SMS_APPS",
    "COMM_APPS",
    "CLOCK_APPS",
    "TOOLS_APPS",
    "SETTINGS_APPS",
    "SETUP_APPS",
    "MEDIA_APPS",
    "GAMES_APPS",
]


class PhoneShell(QMainWindow):
    """Digivice: two-row home, radial folders, hard-button nav apps."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("ESP Digivice")
        self.pages: Dict[str, QWidget] = {}
        self._nav: List[str] = ["home"]
        self._radials: Dict[str, RadialMenu] = {}
        self._home: Optional[DigiviceHome] = None
        self.on_linux_desktop: Optional[Callable[[], None]] = None
        self.on_linux_desktop_now: Optional[Callable[[], None]] = None

        root = QWidget()
        root.setObjectName("phoneRoot")
        self._root = root
        self._wallpaper = QLabel(root)
        self._wallpaper.setObjectName("wallpaper")
        self._wallpaper.setAlignment(Qt.AlignCenter)
        self._wallpaper.lower()
        self._apply_base_style()
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self.status = QFrame()
        self.status.setFixedHeight(20)
        self.status.setStyleSheet(
            "background: rgba(0,0,0,0.55); border-bottom: 1px solid rgba(255,255,255,0.08);"
        )
        s_lay = QHBoxLayout(self.status)
        s_lay.setContentsMargins(4, 0, 4, 0)
        s_lay.setSpacing(4)
        self.clock_lab = QLabel("--:--")
        self.clock_lab.setStyleSheet("font-weight: 700; font-size: 10px;")
        self.clock_lab.setFixedWidth(34)
        self.title_lab = QLabel("")
        self.title_lab.setAlignment(Qt.AlignCenter)
        self.title_lab.setStyleSheet("font-weight: 700; font-size: 10px; color: #e8eef5;")
        self.signal_lab = QLabel("·")
        self.signal_lab.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.signal_lab.setStyleSheet("font-size: 9px; color: #9ab;")
        self.signal_lab.setMinimumWidth(36)
        s_lay.addWidget(self.clock_lab)
        s_lay.addWidget(self.title_lab, 1)
        s_lay.addWidget(self.signal_lab)
        outer.addWidget(self.status)

        self.stack = QStackedWidget()
        outer.addWidget(self.stack, 1)

        self.setCentralWidget(root)
        self._toasts = ToastHost(root)
        self._toasts.raise_()

        self.register_page("home", self._build_home())
        self.go("home", replace=True)
        self.apply_wallpaper()

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick_clock)
        self._timer.start(1000)
        self._tick_clock()
        self.setFocusPolicy(Qt.StrongFocus)
        self.setAttribute(Qt.WA_KeyboardFocusChange, True)
        # Escape (Back): navigate back. Triple-Back → desktop ONLY on Digivice home
        # (never while in Calls/SMS/… submenus). Also debounce duplicate Escapes —
        # buttons daemon emits both uinput + xdotool, so one press ≈ two Key_Escape.
        self._esc_exits = 0
        self._esc_last_ms = 0
        QTimer.singleShot(700, self._prime_nav_clicks)

    def _prime_nav_clicks(self) -> None:
        import threading

        def _run() -> None:
            try:
                from esp_handset.audio_out import prime_nav_click

                prime_nav_click()
            except Exception:
                pass

        threading.Thread(target=_run, daemon=True).start()

    def _nav_click(self) -> None:
        try:
            from esp_handset.audio_out import play_nav_click

            play_nav_click()
        except Exception:
            pass

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self.raise_()
        self.activateWindow()
        # Restore digi page focus — do not leave focus only on PhoneShell
        # (that made Confirm click the first Back chrome control).
        key = self._nav[-1] if self._nav else "home"
        if key == "home" and self._home:
            self._home.setFocus(Qt.OtherFocusReason)
        elif key in self._radials:
            self._radials[key].setFocus(Qt.OtherFocusReason)
        elif key in _GAMEPAD_PAGES and key in self.pages:
            pass  # board focuses itself
        elif key in self.pages:
            digi_nav.ensure_page_focus(self.pages[key])
        # Do NOT grabKeyboard — it bricks USB keyboards / Ctrl+Alt+F2 for recovery

    def changeEvent(self, event) -> None:  # noqa: N802
        super().changeEvent(event)

    def _request_desktop(self) -> None:
        handler = self.on_linux_desktop_now or self.on_linux_desktop
        if handler:
            handler()

    def show_toast(self, title: str, body: str, kind: str = "info") -> None:
        del kind
        self._toasts.raise_()
        self._toasts.show_toast(title, body)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        if self._wallpaper.isVisible():
            self._wallpaper.setGeometry(self._root.rect())
            self.apply_wallpaper()
        if hasattr(self, "_toasts"):
            self._toasts.setGeometry(self._root.rect())
            self._toasts.raise_()

    def _apply_base_style(self) -> None:
        # Focus uses yellow/black, not hue near button blue — shade- and
        # color-deficiency friendly (luminance + shape, not blue-on-blue).
        self._root.setStyleSheet(
            """
            #phoneRoot {
                background: qlineargradient(
                    x1:0, y1:0, x2:0.4, y2:1,
                    stop:0 #0b1a2a, stop:0.55 #12263a, stop:1 #0a121c);
            }
            QLabel { color: #e8eef5; }
            QLineEdit, QTextEdit, QListWidget, QPlainTextEdit {
                background: rgba(10, 18, 28, 0.85);
                color: #e8eef5;
                border: 1px solid rgba(255,255,255,0.12);
                border-radius: 6px;
                padding: 4px;
                font-size: 11px;
            }
            QPushButton {
                background: #1f6feb;
                color: white;
                border: 2px solid transparent;
                border-radius: 6px;
                padding: 6px 8px;
                font-weight: 600;
                font-size: 11px;
            }
            QPushButton:hover { background: #388bfd; }
            /* Digi focus: high luminance contrast + thick black frame (not blue outline) */
            QPushButton[digiFocus="1"] {
                background: #FFE600;
                color: #000000;
                border: 2px solid #000000;
            }
            QLineEdit[digiFocus="1"], QTextEdit[digiFocus="1"],
            QPlainTextEdit[digiFocus="1"], QComboBox[digiFocus="1"],
            QListWidget[digiFocus="1"] {
                background: #1a1a00;
                color: #FFE600;
                border: 3px solid #FFE600;
                outline: none;
                font-weight: 700;
            }
            QListWidget::item:selected {
                background: #FFE600;
                color: #000000;
                border: 2px solid #000000;
            }
            QListWidget::item:selected:!active {
                background: #FFE600;
                color: #000000;
            }
            """
        )

    def apply_wallpaper(self) -> None:
        path = handset_theme.resolve_wallpaper()
        if not path:
            self._wallpaper.clear()
            self._wallpaper.hide()
            self._apply_base_style()
            return
        pix = QPixmap(str(path))
        if pix.isNull():
            self._wallpaper.hide()
            return
        self._wallpaper.show()
        self._wallpaper.lower()
        self._wallpaper.setGeometry(self._root.rect())
        scaled = pix.scaled(
            self._root.size(),
            Qt.KeepAspectRatioByExpanding,
            Qt.SmoothTransformation,
        )
        self._wallpaper.setPixmap(scaled)

    def _page_title(self, key: str) -> str:
        if not key or key == "home":
            return ""
        w = self.pages.get(key)
        if w is not None:
            t = w.property("digiTitle")
            if t:
                return str(t)[:18]
        for _fk, (pk, title, _apps) in FOLDER_MAP.items():
            if pk == key:
                return title[:18]
        return ""

    def _sync_title(self) -> None:
        key = self._nav[-1] if self._nav else "home"
        self.title_lab.setText(self._page_title(key))

    def set_status_right(self, text: str) -> None:
        self.signal_lab.setText((text or "")[:18])

    def register_page(self, key: str, widget: QWidget) -> None:
        self.pages[key] = widget
        self.stack.addWidget(widget)

    def go(self, key: str, replace: bool = False) -> None:
        if key not in self.pages:
            return
        if replace:
            self._nav = [key]
        else:
            if not self._nav or self._nav[-1] != key:
                self._nav.append(key)
        self.stack.setCurrentWidget(self.pages[key])
        if key == "home" and self._home:
            self._home.setFocus(Qt.OtherFocusReason)
        elif key in self._radials:
            self._radials[key].setFocus(Qt.OtherFocusReason)
        elif key in _GAMEPAD_PAGES:
            # Game boards take focus themselves on showEvent; don't land on Back chrome
            pass
        else:
            # Keep focus on the page control (do NOT steal to shell — breaks Confirm/lists)
            digi_nav.ensure_page_focus(self.pages[key])
        self._sync_title()

    def back(self) -> None:
        # App pages can consume Back (e.g. SMS thread → inbox)
        page_key = self._nav[-1] if self._nav else "home"
        page = self.pages.get(page_key)
        if page is not None:
            handler = getattr(page, "on_hardware_back", None)
            if callable(handler):
                try:
                    if handler():
                        return
                except Exception:
                    pass
        if len(self._nav) > 1:
            self._nav.pop()
            key = self._nav[-1]
            self.stack.setCurrentWidget(self.pages[key])
            if key == "home" and self._home:
                self._home.setFocus(Qt.OtherFocusReason)
            elif key in self._radials:
                self._radials[key].setFocus(Qt.OtherFocusReason)
            elif key in _GAMEPAD_PAGES:
                pass
            else:
                digi_nav.ensure_page_focus(self.pages[key])
        else:
            self.go("home", replace=True)
            return
        self._sync_title()

    def _leave_current_page(self) -> None:
        """Stop overlays / emulators before ripping the nav stack away (Home)."""
        page_key = self._nav[-1] if self._nav else ""
        if not page_key or page_key == "home":
            return
        page = self.pages.get(page_key)
        if page is None:
            return
        leave = getattr(page, "on_navigate_away", None)
        if callable(leave):
            try:
                leave()
            except Exception:
                pass

    def home(self) -> None:
        self._leave_current_page()
        self.go("home", replace=True)

    def _tick_clock(self) -> None:
        self.clock_lab.setText(datetime.now().strftime("%H:%M"))

    def _build_home(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        # 5 top + 4 bottom = 9 main icons
        self._home = DigiviceHome(HOME_APPS, top_count=5, on_activate=self._on_icon)
        lay.addWidget(self._home, 1)
        return page

    def _build_radial_page(
        self, title: str, entries: List[AppEntry], page_key: str
    ) -> QWidget:
        page = QWidget()
        page.setProperty("digiTitle", title)
        lay = QVBoxLayout(page)
        lay.setContentsMargins(4, 2, 4, 2)
        lay.setSpacing(0)
        radial = RadialMenu(entries, on_activate=self._on_icon)
        self._radials[page_key] = radial
        lay.addWidget(radial, 1)
        return page

    def build_folder(
        self, title: str, subtitle: str, entries: List[AppEntry]
    ) -> QWidget:
        del subtitle
        return self._build_radial_page(title, entries, f"_tmp_{title}")

    def build_folder_keyed(
        self, page_key: str, title: str, entries: List[AppEntry]
    ) -> QWidget:
        return self._build_radial_page(title, entries, page_key)

    def _on_icon(self, key: str) -> None:
        if key in FOLDER_MAP:
            page_key, _title, _apps = FOLDER_MAP[key]
            self.go(page_key)
            return
        if key == "linux":
            handler = self.on_linux_desktop
            if handler:
                handler()
            return
        if key in self.pages:
            self.go(key)
            return
        if "stub" in self.pages:
            stub = self.pages["stub"]
            lab = stub.findChild(QLabel, "stubBody")
            if lab:
                lab.setText(f"“{key}” not wired.")
            self.go("stub")

    def focus_text_field(self, widget: QWidget) -> None:
        """Confirm on a text field → focus for CardKB / Bluetooth typing."""
        if widget is None:
            return
        widget.setFocus(Qt.OtherFocusReason)
        digi_nav.ensure_visible(widget)

    def keyPressEvent(self, event) -> None:  # noqa: N802
        key = event.key()
        # Desktop escapes (must work with hard buttons)
        if key in (Qt.Key_F12, Qt.Key_F10):
            self._request_desktop()
            event.accept()
            return
        if key == Qt.Key_Q and event.modifiers() & Qt.ControlModifier:
            self._request_desktop()
            event.accept()
            return
        # Ctrl+Shift+D also → desktop
        if (
            key == Qt.Key_D
            and event.modifiers() & Qt.ControlModifier
            and event.modifiers() & Qt.ShiftModifier
        ):
            self._request_desktop()
            event.accept()
            return
        # Back / Escape
        if key == Qt.Key_Escape:
            import time as _time

            now = int(_time.time() * 1000)
            # Collapse uinput+xdotool double-fire into one logical press
            if now - self._esc_last_ms < 90:
                event.accept()
                return
            # Reset streak if paused
            if now - self._esc_last_ms > 1500:
                self._esc_exits = 0
            self._esc_last_ms = now

            on_home = (self._nav[-1] if self._nav else "home") == "home" and len(
                self._nav
            ) <= 1

            if on_home:
                # Only from Digivice home: Back×3 leaves to Linux desktop
                self._esc_exits += 1
                if self._esc_exits >= 3:
                    self._esc_exits = 0
                    self._request_desktop()
                    event.accept()
                    return
                # Single/double Back on home — stay (Home button is for home)
                event.accept()
                return

            # In a submenu / app: always just go back one level
            self._esc_exits = 0
            self.back()
            event.accept()
            return
        else:
            # Don't clear esc streak on Home key noise
            if key not in (Qt.Key_Home,):
                self._esc_exits = 0

        # Home = Digivice home screen only (never exit to Linux desktop)
        # Exception: in-UI PyBoy — Home is Start (buttons daemon stays in phone mode)
        if key == Qt.Key_Home:
            page_key = self._nav[-1] if self._nav else "home"
            if page_key == "gb":
                page = self.pages.get("gb")
                board = getattr(page, "gb_board", None) if page else None
                if (
                    board is not None
                    and board.isVisible()
                    and getattr(board, "playing", False)
                ):
                    tap = getattr(board, "_tap", None)
                    if callable(tap):
                        tap("start")
                    event.accept()
                    return
            self.home()
            event.accept()
            return

        page_key = self._nav[-1] if self._nav else "home"

        if page_key == "home" and self._home:
            if key == Qt.Key_Left:
                self._home.move_h(-1)
                self._nav_click()
                event.accept()
                return
            if key == Qt.Key_Right:
                self._home.move_h(1)
                self._nav_click()
                event.accept()
                return
            if key == Qt.Key_Up:
                self._home.move_v(-1)
                self._nav_click()
                event.accept()
                return
            if key == Qt.Key_Down:
                self._home.move_v(1)
                self._nav_click()
                event.accept()
                return
            if key in (Qt.Key_Return, Qt.Key_Enter):
                self._home.activate()
                event.accept()
                return

        radial = self._radials.get(page_key)
        if radial and page_key == self._nav[-1]:
            if key == Qt.Key_Left:
                radial.move_by(-1)
                self._nav_click()
                event.accept()
                return
            if key == Qt.Key_Right:
                radial.move_by(1)
                self._nav_click()
                event.accept()
                return
            if key == Qt.Key_Up:
                radial.move_by(-1)
                self._nav_click()
                event.accept()
                return
            if key == Qt.Key_Down:
                radial.move_by(1)
                self._nav_click()
                event.accept()
                return
            if key in (Qt.Key_Return, Qt.Key_Enter):
                radial.activate()
                event.accept()
                return
            # Do not swallow letters / other keys (USB/BT keyboard typing)
            super().keyPressEvent(event)
            return

        page = self.pages.get(page_key)
        if page is not None and page_key not in self._radials and page_key != "home":
            if page_key in _GAMEPAD_PAGES:
                # Route pad to living game / GB board
                board = getattr(page, "gb_board", None)
                if (
                    board is not None
                    and board.isVisible()
                    and getattr(board, "playing", False)
                    and hasattr(board, "keyPressEvent")
                ):
                    board.keyPressEvent(event)
                    if not board.hasFocus():
                        board.setFocus(Qt.OtherFocusReason)
                    event.accept()
                    return
                for w in page.findChildren(QWidget):
                    mod = getattr(w.__class__, "__module__", "") or ""
                    if mod.endswith("games_ui") and hasattr(w, "keyPressEvent"):
                        w.keyPressEvent(event)
                        if not w.hasFocus():
                            w.setFocus(Qt.OtherFocusReason)
                        event.accept()
                        return
                if page_key in _ARCADE_PAGES:
                    super().keyPressEvent(event)
                    return

            cur = digi_nav.digi_current(page)
            pad_active = getattr(page, "digi_pad_active", None)
            pad_on = bool(pad_active()) if callable(pad_active) else False
            # Nested RadialMenu / ContactsRadial: route pad when focused
            digi_pad = (
                cur
                if cur is not None and bool(cur.property("digiPad"))
                else None
            )
            if key in (Qt.Key_Left, Qt.Key_Right):
                delta = -1 if key == Qt.Key_Left else 1
                if digi_pad is not None:
                    move_h = getattr(digi_pad, "move_h", None) or getattr(
                        digi_pad, "move_by", None
                    )
                    if callable(move_h) and move_h(delta):
                        self._nav_click()
                        event.accept()
                        return
                move_h = getattr(page, "digi_move_h", None)
                if pad_on and callable(move_h) and move_h(delta):
                    self._nav_click()
                    event.accept()
                    return
                # Gallery full-screen viewer: L/R = prev/next photo
                seek = getattr(page, "digi_seek", None)
                active = getattr(page, "digi_seek_active", None)
                if callable(seek) and (active() if callable(active) else False):
                    if seek(delta):
                        self._nav_click()
                        event.accept()
                        return
                if digi_nav.move_focus(page, delta):
                    self._nav_click()
                    event.accept()
                    return
            if key in (Qt.Key_Up, Qt.Key_Down):
                delta = -1 if key == Qt.Key_Up else 1
                if digi_pad is not None:
                    move_v = getattr(digi_pad, "move_v", None) or getattr(
                        digi_pad, "move_by", None
                    )
                    if callable(move_v):
                        if move_v(delta):
                            self._nav_click()
                            event.accept()
                            return
                        # Edge (e.g. contacts letter axis) → fall through to Add
                move_v = getattr(page, "digi_move_v", None)
                if pad_on and callable(move_v) and move_v(delta):
                    self._nav_click()
                    event.accept()
                    return
                if isinstance(cur, QListWidget):
                    if digi_nav.list_nudge(cur, delta):
                        self._nav_click()
                        event.accept()
                        return
                if digi_nav.move_focus(page, delta):
                    self._nav_click()
                    event.accept()
                    return
            if key in (Qt.Key_Return, Qt.Key_Enter):
                # Camera etc.: page.digi_activate() (Confirm = snap)
                digi_act = getattr(page, "digi_activate", None)
                if callable(digi_act):
                    try:
                        if digi_act():
                            event.accept()
                            return
                    except Exception:
                        pass
                if digi_nav.activate_page(page, self.focus_text_field):
                    event.accept()
                    return
                digi_nav.ensure_page_focus(page)
                if digi_nav.activate_page(page, self.focus_text_field):
                    event.accept()
                    return

        super().keyPressEvent(event)

    def keyReleaseEvent(self, event) -> None:  # noqa: N802
        page_key = self._nav[-1] if self._nav else "home"
        if page_key == "gb":
            page = self.pages.get("gb")
            board = getattr(page, "gb_board", None) if page else None
            if (
                board is not None
                and board.isVisible()
                and getattr(board, "playing", False)
            ):
                board.keyReleaseEvent(event)
                event.accept()
                return
        super().keyReleaseEvent(event)
