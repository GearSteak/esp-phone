"""Digivice shell — two-row home → radial submenu → app (240×320 default)."""

from __future__ import annotations

from datetime import datetime
from typing import Callable, Dict, List, Optional

from PyQt5.QtCore import QEasingCurve, QPropertyAnimation, Qt, QTimer, pyqtProperty, pyqtSignal
from PyQt5.QtGui import QColor, QPainter, QPixmap
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
    APPS_APPS,
    ACCOUNTS_APPS,
    CALLS_APPS,
    CAMERA_APPS,
    CLOCK_APPS,
    COMM_APPS,
    DEBUG_APPS,
    EMU_PAGE_KEYS,
    FOLDER_MAP,
    GAMES_APPS,
    HOME_APPS,
    MEDIA_APPS,
    SETTINGS_APPS,
    SETUP_APPS,
    SMS_APPS,
    SYSTEM_APPS,
    DISPLAY_APPS,
    TOOLS_APPS,
    AppEntry,
)
from esp_handset.toasts import ToastHost
from esp_handset.incoming_call import IncomingCallOverlay
from esp_handset.call_ui import CallOverlay

_GAME_PAGES = {e.key for e in GAMES_APPS}
# Live boards (timers + own keys) — not button-driven solitaire/uno
_ARCADE_PAGES = {"snake", "pong", "tetris"}
_CARD_GAME_PAGES = {"solitaire", "uno"}
# Arcade/cards always use the pad. Emulators only while a ROM is running.
_GAMEPAD_PAGES = _ARCADE_PAGES | _CARD_GAME_PAGES

__all__ = [
    "PhoneShell",
    "AppEntry",
    "HOME_APPS",
    "APPS_APPS",
    "CALLS_APPS",
    "CAMERA_APPS",
    "SMS_APPS",
    "COMM_APPS",
    "CLOCK_APPS",
    "TOOLS_APPS",
    "SETTINGS_APPS",
    "SETUP_APPS",
    "MEDIA_APPS",
    "GAMES_APPS",
    "DEBUG_APPS",
    "ACCOUNTS_APPS",
    "SYSTEM_APPS",
    "DISPLAY_APPS",
]


class _FadeVeil(QWidget):
    """Soft blackout used for page transitions (cheap on SPI / Pi)."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._alpha = 0
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self.hide()

    def _get_alpha(self) -> int:
        return int(self._alpha)

    def _set_alpha(self, v: int) -> None:
        a = max(0, min(220, int(v)))
        if a == self._alpha:
            return
        self._alpha = a
        if a <= 0:
            self.hide()
        else:
            if not self.isVisible():
                self.show()
            self.update()

    veil_alpha = pyqtProperty(int, _get_alpha, _set_alpha)

    def paintEvent(self, _event) -> None:  # noqa: N802
        if self._alpha <= 0:
            return
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(6, 12, 20, self._alpha))


class PhoneShell(QMainWindow):
    """Digivice: two-row home, radial folders, hard-button nav apps."""

    # Emitted from worker threads → slots update glyphs on the UI thread
    net_status = pyqtSignal(bool, int, bool, bool)  # wifi, bars, known, bt

    def __init__(self):
        super().__init__()
        self.setWindowTitle("ESP Digivice")
        self.pages: Dict[str, QWidget] = {}
        self._nav: List[str] = ["home"]
        self._radials: Dict[str, RadialMenu] = {}
        self._home: Optional[DigiviceHome] = None
        self.on_linux_desktop: Optional[Callable[[], None]] = None
        self.on_linux_desktop_now: Optional[Callable[[], None]] = None
        self.on_browser: Optional[Callable[[], None]] = None
        self._net_busy = False
        self.net_status.connect(self._apply_net_status)
        self._trans_busy = False
        self._trans_anim: Optional[QPropertyAnimation] = None
        self._trans_pending: Optional[str] = None
        self._trans_phase = ""

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
        self.status.setFixedHeight(22)
        self.status.setStyleSheet(
            "background: rgba(0,0,0,0.55); border-bottom: 1px solid rgba(255,255,255,0.08);"
        )
        s_lay = QHBoxLayout(self.status)
        s_lay.setContentsMargins(3, 0, 3, 0)
        s_lay.setSpacing(3)

        # Left: time + date
        left = QHBoxLayout()
        left.setSpacing(3)
        left.setContentsMargins(0, 0, 0, 0)
        self.clock_lab = QLabel("--:--")
        self.clock_lab.setStyleSheet(
            "font-weight: 700; font-size: 10px; color:#e8eef5; font-family: monospace;"
        )
        self.date_lab = QLabel("")
        self.date_lab.setStyleSheet(
            "font-size: 9px; font-weight:700; color:#e8eef5; font-family: monospace;"
        )
        left.addWidget(self.clock_lab)
        left.addWidget(self.date_lab)
        s_lay.addLayout(left)

        self.title_lab = QLabel("")
        self.title_lab.setAlignment(Qt.AlignCenter)
        self.title_lab.setStyleSheet("font-weight: 700; font-size: 10px; color: #e8eef5;")
        s_lay.addWidget(self.title_lab, 1)

        # Right: cart · UPS bat · BT · Wi‑Fi · cellular (no Heltec %)
        from esp_handset.status_icons import BatGlyph, BtGlyph, CellGlyph, WifiGlyph

        self.wifi_glyph = WifiGlyph()
        self.cell_glyph = CellGlyph()
        self.bt_glyph = BtGlyph()
        self.bat_glyph = BatGlyph()
        self.heltec_bat_lab = QLabel("")
        self.heltec_bat_lab.hide()
        self.ups_bat_lab = QLabel("")
        self.ups_bat_lab.hide()
        self.cart_lab = QLabel("")
        self.cart_lab.setStyleSheet(
            "font-size:9px; font-weight:700; color:#5ec4a8; font-family:monospace;"
        )
        self.cart_lab.setToolTip("USB cartridge inserted")
        self.cart_lab.hide()
        self.signal_lab = QLabel("")
        self.signal_lab.hide()
        right = QHBoxLayout()
        right.setSpacing(3)
        right.setContentsMargins(0, 0, 0, 0)
        right.addWidget(self.cart_lab, 0, Qt.AlignVCenter)
        right.addWidget(self.bat_glyph, 0, Qt.AlignVCenter)
        right.addWidget(self.bt_glyph, 0, Qt.AlignVCenter)
        right.addWidget(self.wifi_glyph, 0, Qt.AlignVCenter)
        right.addWidget(self.cell_glyph, 0, Qt.AlignVCenter)
        s_lay.addLayout(right)
        outer.addWidget(self.status)

        self._title_saved = ""
        self._flash_timer = QTimer(self)
        self._flash_timer.setSingleShot(True)
        self._flash_timer.timeout.connect(self._restore_title)

        self._net_timer = QTimer(self)
        self._net_timer.timeout.connect(self._tick_network)
        # Wi‑Fi / cell / BT — keep BT icon responsive after connect/disconnect
        self._net_timer.start(5_000)
        self._modem_signal_fn = None  # optional Callable[[], Optional[str]]
        QTimer.singleShot(800, self._tick_network)

        self.stack = QStackedWidget()
        outer.addWidget(self.stack, 1)

        self.setCentralWidget(root)
        self._fade_veil = _FadeVeil(root)
        self._toasts = ToastHost(root)
        self._toasts.raise_()
        self._incoming = IncomingCallOverlay(root)
        self._incoming.raise_()
        self._active_call = CallOverlay(root)
        self._active_call.raise_()

        self.register_page("home", self._build_home())
        self.go("home", replace=True, animate=False)
        self.apply_wallpaper()
        QTimer.singleShot(0, self._sync_fade_veil_geom)

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

    def show_incoming_call(
        self,
        number: str,
        *,
        name: str = "",
        photo: Optional[str] = None,
        on_answer: Optional[Callable[[], None]] = None,
        on_decline: Optional[Callable[[], None]] = None,
        subtitle: str = "",
    ) -> None:
        self._incoming.setGeometry(self._root.rect())
        self._incoming.show_call(
            number,
            name=name,
            photo=photo,
            on_answer=on_answer,
            on_decline=on_decline,
            subtitle=subtitle,
        )
        self._incoming.raise_()

    def hide_incoming_call(self) -> None:
        self._incoming.hide_call()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        if self._wallpaper.isVisible():
            self._wallpaper.setGeometry(self._root.rect())
            self.apply_wallpaper()
        if hasattr(self, "_toasts"):
            self._toasts.setGeometry(self._root.rect())
            self._toasts.raise_()
        if hasattr(self, "_incoming") and self._incoming.isVisible():
            self._incoming.setGeometry(self._root.rect())
            self._incoming.raise_()
        if hasattr(self, "_active_call") and self._active_call.isVisible():
            self._active_call.setGeometry(self._root.rect())
            self._active_call.raise_()

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
        self._title_saved = self._page_title(key)
        if not self._flash_timer.isActive():
            self.title_lab.setText(self._title_saved)

    def set_status_right(self, text: str) -> None:
        """Brief center flash — does not replace Wi‑Fi / signal glyphs."""
        msg = (text or "").strip()
        if not msg:
            return
        # Keep a hidden text mirror for anything still reading signal_lab
        self.signal_lab.setText(msg[:18])
        self.title_lab.setText(msg[:28])
        self._flash_timer.start(2200)

    def set_heltec_battery(self, percent: int, *, mv: int = 0) -> None:
        """Ignored — Digivice only shows UPS pack %, not Heltec LiPo."""
        del percent, mv

    def set_ups_battery(self, percent: int, *, charging: bool = False) -> None:
        """UPS 3S pack via BatGlyph. percent < 0 → absent / USB power."""
        try:
            self.bat_glyph.set_status(int(percent), charging=charging)
        except Exception:
            try:
                self.bat_glyph.set_status(-1)
            except Exception:
                pass

    def set_cart_label(self, title: str) -> None:
        t = (title or "").strip()
        if not t:
            self.cart_lab.hide()
            return
        short = t if len(t) <= 10 else t[:9] + "…"
        self.cart_lab.setText(short)
        self.cart_lab.setToolTip(f"USB cart: {t}")
        self.cart_lab.show()

    def _restore_title(self) -> None:
        try:
            self.title_lab.setText(self._title_saved)
        except Exception:
            pass

    def set_modem_signal_provider(self, fn) -> None:
        """fn() → AT+CSQ line or None. Polled for cellular bars."""
        self._modem_signal_fn = fn
        QTimer.singleShot(400, self._tick_network)

    def _apply_net_status(
        self, wifi_on: bool, bars: int, known: bool, bt_on: bool = False
    ) -> None:
        try:
            self.wifi_glyph.set_connected(bool(wifi_on))
            self.cell_glyph.set_bars(int(bars), known=bool(known))
            self.bt_glyph.set_connected(bool(bt_on))
        except Exception:
            pass
        finally:
            self._net_busy = False

    def _tick_network(self) -> None:
        """Probe Wi‑Fi + CSQ + BT off the UI thread; apply via net_status signal."""
        if self._net_busy:
            return
        self._net_busy = True
        fn = getattr(self, "_modem_signal_fn", None)

        def _work() -> None:
            wifi_on = False
            bars = 0
            known = False
            bt_on = False
            try:
                from esp_handset.status_icons import (
                    bluetooth_connected,
                    parse_csq_rssi,
                    rssi_to_bars,
                    wifi_is_up,
                )

                try:
                    wifi_on = bool(wifi_is_up())
                except Exception:
                    wifi_on = False
                try:
                    bt_on = bool(bluetooth_connected())
                except Exception:
                    bt_on = False
                line = None
                if callable(fn):
                    try:
                        line = fn()
                    except Exception:
                        line = None
                rssi = parse_csq_rssi(line)
                known = rssi is not None
                bars = rssi_to_bars(rssi) if known else 0
            except Exception:
                pass
            try:
                self.net_status.emit(wifi_on, bars, known, bt_on)
            except TypeError:
                try:
                    self.net_status.emit(wifi_on, bars, known)
                except Exception:
                    self._net_busy = False
            except Exception:
                self._net_busy = False

        import threading

        threading.Thread(target=_work, daemon=True).start()

    def _tick_clock(self) -> None:
        try:
            now = datetime.now()
            self.clock_lab.setText(now.strftime("%H:%M"))
            self.date_lab.setText(now.strftime("%a") + f" {now.day}")
        except Exception:
            pass

    def register_page(self, key: str, widget: QWidget) -> None:
        self.pages[key] = widget
        self.stack.addWidget(widget)

    def _sync_fade_veil_geom(self) -> None:
        try:
            self._fade_veil.setGeometry(self.stack.geometry())
        except Exception:
            pass

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._sync_fade_veil_geom()

    def _raise_overlays(self) -> None:
        try:
            self._fade_veil.raise_()
            self._toasts.raise_()
            self._incoming.raise_()
            self._active_call.raise_()
        except Exception:
            pass

    def _focus_page(self, key: str) -> None:
        if key == "home" and self._home:
            self._home.setFocus(Qt.OtherFocusReason)
        elif key in self._radials:
            self._radials[key].setFocus(Qt.OtherFocusReason)
        elif key in _GAMEPAD_PAGES:
            pass
        elif key in self.pages:
            digi_nav.ensure_page_focus(self.pages[key])

    def _apply_page_now(self, key: str) -> None:
        """Swap stack page + focus + on_page_show (no animation)."""
        if key not in self.pages:
            return
        self.stack.setCurrentWidget(self.pages[key])
        self._focus_page(key)
        page = self.pages[key]
        on_show = getattr(page, "on_page_show", None)
        if callable(on_show):
            try:
                on_show()
            except Exception:
                pass
        self._sync_title()

    def _switch_page(self, key: str, *, animate: bool = True) -> None:
        """Fade through a soft veil when changing Digivice screens."""
        if key not in self.pages:
            return
        if self.stack.currentWidget() is self.pages[key]:
            self._apply_page_now(key)
            return
        # Rapid nav while a fade is running: jump, then queue one more if needed
        if self._trans_busy or not animate:
            self._trans_pending = None
            if self._trans_anim is not None:
                try:
                    self._trans_anim.finished.disconnect()
                except Exception:
                    pass
                self._trans_anim.stop()
                self._trans_anim = None
            self._trans_busy = False
            self._trans_phase = ""
            try:
                self._fade_veil.veil_alpha = 0
            except Exception:
                pass
            self._apply_page_now(key)
            return

        self._trans_busy = True
        self._trans_pending = None
        self._trans_phase = "in"
        self._sync_fade_veil_geom()
        self._raise_overlays()
        target = key

        anim = QPropertyAnimation(self._fade_veil, b"veil_alpha", self)
        anim.setDuration(90)
        anim.setStartValue(0)
        anim.setEndValue(160)
        anim.setEasingCurve(QEasingCurve.InQuad)

        def _mid() -> None:
            self._apply_page_now(target)
            self._trans_phase = "out"
            self._raise_overlays()
            out = QPropertyAnimation(self._fade_veil, b"veil_alpha", self)
            out.setDuration(120)
            out.setStartValue(160)
            out.setEndValue(0)
            out.setEasingCurve(QEasingCurve.OutQuad)

            def _done() -> None:
                self._trans_anim = None
                self._trans_busy = False
                self._trans_phase = ""
                pending = self._trans_pending
                self._trans_pending = None
                if pending and pending in self.pages:
                    self._switch_page(pending, animate=True)

            out.finished.connect(_done)
            self._trans_anim = out
            out.start()

        anim.finished.connect(_mid)
        self._trans_anim = anim
        anim.start()

    def go(self, key: str, replace: bool = False, *, animate: bool = True) -> None:
        if key not in self.pages:
            return
        if replace:
            self._nav = [key]
        else:
            if not self._nav or self._nav[-1] != key:
                self._nav.append(key)
        self._switch_page(key, animate=animate)

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
            self._switch_page(key, animate=True)
        else:
            self.go("home", replace=True)
            return

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

    def _build_home(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        # 5 top + 5 bottom = 10 main icons
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
        try:
            # Keep digi yellow ring so you can see which field is live
            digi_nav.clear_highlights(widget.window() if widget.window() else widget)
            digi_nav._highlight(widget, True)
        except Exception:
            pass
        try:
            self.set_status_right("")
        except Exception:
            pass

    def _emu_play_board(self):
        """In-UI emulator surface when a ROM is running, else None."""
        page_key = self._nav[-1] if self._nav else ""
        if page_key not in EMU_PAGE_KEYS:
            return None
        page = self.pages.get(page_key)
        board = getattr(page, "emu_board", None) if page else None
        if board is None and page is not None:
            board = getattr(page, "gb_board", None)
        if (
            board is not None
            and (
                getattr(board, "capturing_pad", False)
                or getattr(board, "playing", False)
            )
        ):
            return board
        return None

    def keyPressEvent(self, event) -> None:  # noqa: N802
        key = event.key()
        # Active outbound / in-call overlay
        if getattr(self, "_active_call", None) is not None and self._active_call.active:
            self._active_call.keyPressEvent(event)
            event.accept()
            return
        # Incoming call takeover — before everything else
        if getattr(self, "_incoming", None) is not None and self._incoming.active:
            self._incoming.keyPressEvent(event)
            event.accept()
            return
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

        # In-UI emulator: pad stays in game (Back=B, Home=Start); exit = combo on board
        gb_board = self._emu_play_board()
        if gb_board is not None:
            gb_board.keyPressEvent(event)
            if not gb_board.hasFocus():
                gb_board.setFocus(Qt.OtherFocusReason)
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
        if key == Qt.Key_Home:
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
                # Route pad to living game / emu board
                board = getattr(page, "emu_board", None) or getattr(
                    page, "gb_board", None
                )
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
                game_shell = getattr(page, "game_shell", None)
                if game_shell is not None:
                    if key in (Qt.Key_Left, Qt.Key_Right):
                        dx = -1 if key == Qt.Key_Left else 1
                        game_shell.digi_nav(dx, 0)
                        self._nav_click()
                        event.accept()
                        return
                    if key in (Qt.Key_Up, Qt.Key_Down):
                        dy = -1 if key == Qt.Key_Up else 1
                        game_shell.digi_nav(0, dy)
                        self._nav_click()
                        event.accept()
                        return
                    if key in (Qt.Key_Return, Qt.Key_Enter):
                        game_shell.digi_confirm()
                        event.accept()
                        return
                    # Space → restart / board key handler when playing
                    play = getattr(game_shell, "board", None)
                    if play is not None and hasattr(play, "keyPressEvent"):
                        if game_shell.stack.currentWidget() is getattr(
                            game_shell, "play_page", None
                        ):
                            play.keyPressEvent(event)
                            event.accept()
                            return
                    event.accept()
                    return
                for w in page.findChildren(QWidget):
                    mod = getattr(w.__class__, "__module__", "") or ""
                    if mod.endswith("games_ui") and hasattr(w, "tick"):
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
                # Gallery / etc.: L/R seek — never for Alarms/Timer isolation
                if page.property("timeTool"):
                    pass
                else:
                    seek = getattr(page, "digi_seek", None)
                    active = getattr(page, "digi_seek_active", None)
                    if callable(seek) and (active() if callable(active) else False):
                        if seek(delta):
                            self._nav_click()
                            event.accept()
                            return
                if digi_nav.move_focus_xy(page, delta, 0):
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
                if isinstance(cur, (QTextEdit, QPlainTextEdit)):
                    if digi_nav.text_nudge(cur, delta):
                        self._nav_click()
                        event.accept()
                        return
                if isinstance(cur, QListWidget):
                    if digi_nav.list_nudge(cur, delta):
                        self._nav_click()
                        event.accept()
                        return
                if digi_nav.move_focus_xy(page, 0, delta):
                    self._nav_click()
                    event.accept()
                    return
                # No more focus targets that way — scroll any visible scrollbar
                if digi_nav.nudge_scroll(page, delta, from_widget=cur):
                    self._nav_click()
                    event.accept()
                    return
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
        gb_board = self._emu_play_board()
        if gb_board is not None:
            gb_board.keyReleaseEvent(event)
            event.accept()
            return
        page_key = self._nav[-1] if self._nav else "home"
        if page_key in EMU_PAGE_KEYS:
            page = self.pages.get(page_key)
            board = getattr(page, "emu_board", None) if page else None
            if board is None and page is not None:
                board = getattr(page, "gb_board", None)
            if (
                board is not None
                and (
                    getattr(board, "capturing_pad", False)
                    or getattr(board, "playing", False)
                )
            ):
                board.keyReleaseEvent(event)
                event.accept()
                return
        super().keyReleaseEvent(event)
