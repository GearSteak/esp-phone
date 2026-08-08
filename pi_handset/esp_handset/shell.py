"""Digivice shell — two-row home → radial submenu → app (240×320 default)."""

from __future__ import annotations

from datetime import datetime
from typing import Callable, Dict, List, Optional

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont, QPixmap
from PyQt5.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QStackedWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from esp_handset import digi_nav
from esp_handset import theme as handset_theme
from esp_handset.digivice_home import DigiviceHome
from esp_handset.osk import OnScreenKeyboard
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
        self._osk_target: Optional[QWidget] = None
        self.on_linux_desktop: Optional[Callable[[], None]] = None

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
        self.status.setFixedHeight(18)
        self.status.setStyleSheet(
            "background: rgba(0,0,0,0.55); border-bottom: 1px solid rgba(255,255,255,0.08);"
        )
        s_lay = QHBoxLayout(self.status)
        s_lay.setContentsMargins(6, 0, 6, 0)
        self.clock_lab = QLabel("--:--")
        self.clock_lab.setStyleSheet("font-weight: 700; font-size: 10px;")
        self.signal_lab = QLabel("·")
        self.signal_lab.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.signal_lab.setStyleSheet("font-size: 9px; color: #9ab;")
        s_lay.addWidget(self.clock_lab)
        s_lay.addStretch(1)
        s_lay.addWidget(self.signal_lab)
        outer.addWidget(self.status)

        self.stack = QStackedWidget()
        outer.addWidget(self.stack, 1)

        self._osk = OnScreenKeyboard(root)
        self._osk.hide()
        self._osk.commit.connect(self._osk_commit)
        self._osk.closed.connect(lambda: None)
        outer.addWidget(self._osk)

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
        self._root.setStyleSheet(
            """
            #phoneRoot {
                background: qlineargradient(
                    x1:0, y1:0, x2:0.4, y2:1,
                    stop:0 #0b1a2a, stop:0.55 #12263a, stop:1 #0a121c);
            }
            QLabel { color: #e8eef5; }
            QLineEdit, QTextEdit, QListWidget {
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
                border: none;
                border-radius: 6px;
                padding: 6px 8px;
                font-weight: 600;
                font-size: 11px;
            }
            QPushButton:hover { background: #388bfd; }
            QPushButton[digiFocus="1"], QLineEdit[digiFocus="1"],
            QTextEdit[digiFocus="1"], QListWidget[digiFocus="1"],
            QComboBox[digiFocus="1"] {
                border: 2px solid #58a6ff;
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
        self.hide_osk()
        if key == "home" and self._home:
            self._home.setFocus()
        elif key in self._radials:
            self._radials[key].setFocus()
        else:
            digi_nav.ensure_page_focus(self.pages[key])
            self.setFocus()

    def back(self) -> None:
        self.hide_osk()
        if len(self._nav) > 1:
            self._nav.pop()
            key = self._nav[-1]
            self.stack.setCurrentWidget(self.pages[key])
            if key == "home" and self._home:
                self._home.setFocus()
            elif key in self._radials:
                self._radials[key].setFocus()
            else:
                digi_nav.ensure_page_focus(self.pages[key])
        else:
            self.go("home", replace=True)

    def home(self) -> None:
        self.hide_osk()
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
        lay = QVBoxLayout(page)
        lay.setContentsMargins(4, 2, 4, 2)
        lay.setSpacing(0)
        head = QLabel(title)
        head.setAlignment(Qt.AlignCenter)
        head.setFont(QFont("DejaVu Sans", 9, QFont.Bold))
        head.setStyleSheet("color: #9ab;")
        lay.addWidget(head)
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

    def show_osk_for(self, widget: QWidget) -> None:
        self._osk_target = widget
        text = ""
        if isinstance(widget, QLineEdit):
            text = widget.text()
        elif isinstance(widget, QTextEdit):
            text = widget.toPlainText()
        self._osk.set_prefix_from_text(text)
        self._osk.show()
        self._osk.raise_()

    def hide_osk(self) -> None:
        self._osk.hide()
        self._osk_target = None

    def toggle_osk(self) -> None:
        if self._osk.isVisible():
            self.hide_osk()
            return
        w = self.focusWidget()
        if isinstance(w, (QLineEdit, QTextEdit)):
            self.show_osk_for(w)
        else:
            page = self.stack.currentWidget()
            if page:
                for child in page.findChildren((QLineEdit, QTextEdit)):
                    child.setFocus()
                    self.show_osk_for(child)
                    return

    def _osk_commit(self, ch: str) -> None:
        w = self._osk_target
        if w is None:
            return
        if isinstance(w, QLineEdit):
            if ch == "\b":
                w.backspace()
            elif ch == "\n":
                self.hide_osk()
            else:
                w.insert(ch)
            self._osk.set_prefix_from_text(w.text())
        elif isinstance(w, QTextEdit):
            c = w.textCursor()
            if ch == "\b":
                c.deletePreviousChar()
            elif ch == "\n":
                c.insertText("\n")
            else:
                c.insertText(ch)
            w.setTextCursor(c)
            self._osk.set_prefix_from_text(w.toPlainText(), c.position())

    def keyPressEvent(self, event) -> None:  # noqa: N802
        key = event.key()
        if key == Qt.Key_F2:
            self.toggle_osk()
            event.accept()
            return
        if self._osk.isVisible():
            mapping = {
                Qt.Key_Left: "left",
                Qt.Key_Right: "right",
                Qt.Key_Up: "up",
                Qt.Key_Down: "down",
                Qt.Key_Return: "ok",
                Qt.Key_Enter: "ok",
                Qt.Key_Escape: "close",
            }
            if key == Qt.Key_Tab:
                self._osk.nav("pred")
                event.accept()
                return
            name = mapping.get(key)
            if name and self._osk.nav(name):
                event.accept()
                return
            if key == Qt.Key_Escape:
                self.hide_osk()
                event.accept()
                return

        if key == Qt.Key_Escape:
            self.back()
            event.accept()
            return
        if key == Qt.Key_Home:
            self.home()
            event.accept()
            return

        if key in (Qt.Key_Return, Qt.Key_Enter) and not self._osk.isVisible():
            w = self.focusWidget()
            if isinstance(w, (QLineEdit, QTextEdit)):
                self.show_osk_for(w)
                event.accept()
                return

        page_key = self._nav[-1] if self._nav else "home"

        if page_key == "home" and self._home:
            if key == Qt.Key_Left:
                self._home.move_h(-1)
                event.accept()
                return
            if key == Qt.Key_Right:
                self._home.move_h(1)
                event.accept()
                return
            if key == Qt.Key_Up:
                self._home.move_v(-1)
                event.accept()
                return
            if key == Qt.Key_Down:
                self._home.move_v(1)
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
                event.accept()
                return
            if key == Qt.Key_Right:
                radial.move_by(1)
                event.accept()
                return
            if key in (Qt.Key_Return, Qt.Key_Enter):
                radial.activate()
                event.accept()
                return
            event.accept()
            return

        page = self.pages.get(page_key)
        if page is not None and page_key not in self._radials and page_key != "home":
            if page_key in _GAME_PAGES:
                super().keyPressEvent(event)
                return

            fw = self.focusWidget()
            if key in (Qt.Key_Up, Qt.Key_Down):
                delta = -1 if key == Qt.Key_Up else 1
                if isinstance(fw, QListWidget):
                    if digi_nav.list_nudge(fw, delta):
                        event.accept()
                        return
                if digi_nav.move_focus(page, delta):
                    event.accept()
                    return
            if key in (Qt.Key_Left, Qt.Key_Right):
                delta = -1 if key == Qt.Key_Left else 1
                if digi_nav.move_focus(page, delta):
                    event.accept()
                    return
            if key in (Qt.Key_Return, Qt.Key_Enter):
                if digi_nav.activate_focused(fw, self.show_osk_for):
                    event.accept()
                    return
                digi_nav.ensure_page_focus(page)
                if digi_nav.activate_focused(self.focusWidget(), self.show_osk_for):
                    event.accept()
                    return

        super().keyPressEvent(event)
