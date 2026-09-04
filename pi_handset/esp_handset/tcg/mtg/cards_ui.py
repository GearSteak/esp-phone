"""MTG card search — auto-sync DB, search list, then detail (text | art)."""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Callable, List, Optional

from PyQt5.QtCore import Qt, QTimer, QThread, pyqtSignal
from PyQt5.QtGui import QFont, QPixmap
from PyQt5.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QProgressBar,
    QPushButton,
    QStackedWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from esp_handset.pages import page_chrome
from esp_handset.tcg.mtg import cards_db, sync
from esp_handset.ui_font import font_family

_STYLE = """
QLineEdit {
    font-size: 13px; padding: 6px; background: #1a2430; color: #e8eef5;
    border: 2px solid #3a5068; border-radius: 4px;
}
QLineEdit[digiFocus="1"] { border: 2px solid #FFE600; }
QListWidget {
    font-size: 13px; background: #121820; color: #e8eef5;
    border: 1px solid #3a5068;
}
QListWidget[digiFocus="1"] { border: 2px solid #FFE600; }
QListWidget::item { padding: 6px 4px; }
QListWidget::item:selected { background: #2a4a68; }
QTextEdit {
    font-size: 11px; background: #0e1620; color: #e8eef5;
    border: 1px solid #3a5068; padding: 4px;
}
QLabel#mtgArt {
    background: #0a1018; border: 2px solid #3a5068;
}
QLabel#mtgStatus { font-size: 11px; color: #9ab; }
QLabel#mtgHint { font-size: 12px; color: #6a7a8a; }
QFrame#mtgStatBox, QWidget#mtgStatBox {
    background: #121820; border: 2px solid #3a5068;
}
QLabel#mtgName {
    font-size: 13px; font-weight: bold; color: #FFE600;
}
QLabel#mtgMana { font-size: 12px; color: #c8d8e8; }
QLabel#mtgType { font-size: 11px; color: #9ab; }
QLabel#mtgStats {
    font-size: 14px; font-weight: bold; color: #e8eef5;
}
"""


class _DbWorker(QThread):
    progress = pyqtSignal(str, int)
    finished_ok = pyqtSignal(int)
    finished_err = pyqtSignal(str)

    def __init__(self, parent=None, *, force: bool = False) -> None:
        super().__init__(parent)
        self._force = force

    def run(self) -> None:
        try:

            def _prog(msg: str, pct: int) -> None:
                self.progress.emit(msg, int(pct))

            n = sync.ensure_database(progress=_prog, force=self._force)
            self.finished_ok.emit(int(n))
        except Exception as e:
            self.finished_err.emit(str(e))


class _DownloadOverlay(QWidget):
    dismissed = pyqtSignal()

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("mtgDlOverlay")
        self.setStyleSheet(
            "#mtgDlOverlay { background: #0a1018; border: 3px solid #FFE600; }"
            "QLabel { color: #e8eef5; background: transparent; }"
            "QProgressBar {"
            "  border: 2px solid #3a5068; background: #121820;"
            "  text-align: center; color: #fff; min-height: 22px;"
            "}"
            "QProgressBar::chunk { background: #FFE600; }"
            "QPushButton {"
            "  font-size: 13px; padding: 10px; background: #2a4a68; color: #fff;"
            "  border: 2px solid #FFE600;"
            "}"
            "QPushButton[digiFocus='1'] {"
            "  background: #FFE600; color: #000; border: 2px solid #000;"
            "}"
        )
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 14, 12, 12)
        lay.setSpacing(8)

        title = QLabel("Card database")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-size: 14px; font-weight: bold; color: #FFE600;")
        lay.addWidget(title)

        self._pct = QLabel("0%")
        self._pct.setAlignment(Qt.AlignCenter)
        self._pct.setStyleSheet("font-size: 36px; font-weight: bold; color: #fff;")
        lay.addWidget(self._pct)

        self._bar = QProgressBar()
        self._bar.setRange(0, 100)
        self._bar.setValue(0)
        self._bar.setTextVisible(False)
        self._bar.setFocusPolicy(Qt.NoFocus)
        lay.addWidget(self._bar)

        self._msg = QLabel("Starting…")
        self._msg.setWordWrap(True)
        self._msg.setAlignment(Qt.AlignCenter)
        self._msg.setStyleSheet("font-size: 12px;")
        self._msg.setMinimumHeight(56)
        lay.addWidget(self._msg, 1)

        self._ok = QPushButton("OK")
        self._ok.setFocusPolicy(Qt.StrongFocus)
        self._ok.hide()
        self._ok.clicked.connect(self._dismiss)
        self._ok.digi_confirm = self._dismiss  # type: ignore[attr-defined]
        lay.addWidget(self._ok)
        self.hide()

    def _dismiss(self) -> bool:
        self.hide()
        self.dismissed.emit()
        return True

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        if self.parentWidget() is not None:
            self.setGeometry(self.parentWidget().rect())

    def show_over(self) -> None:
        p = self.parentWidget()
        if p is not None:
            self.setGeometry(p.rect())
        self.raise_()
        self.show()

    def set_progress(self, message: str, percent: int) -> None:
        pct = max(0, min(100, int(percent)))
        self._bar.setValue(pct)
        self._pct.setText(f"{pct}%")
        self._pct.setStyleSheet("font-size: 36px; font-weight: bold; color: #fff;")
        self._msg.setText(message)
        self._ok.hide()

    def set_success(self, count: int) -> None:
        self._bar.setValue(100)
        self._pct.setText("100%")
        self._pct.setStyleSheet("font-size: 36px; font-weight: bold; color: #fff;")
        self._msg.setText(f"Ready — {count:,} cards")
        self._ok.hide()

    def set_error(self, message: str) -> None:
        self._pct.setText("FAIL")
        self._pct.setStyleSheet("font-size: 28px; font-weight: bold; color: #ff6b6b;")
        self._msg.setText(message[:220])
        self._ok.setText("OK")
        self._ok.show()
        self._ok.setFocus(Qt.OtherFocusReason)
        self._ok.setProperty("digiFocus", "1")
        self._ok.style().unpolish(self._ok)
        self._ok.style().polish(self._ok)


class _CardDetailPage(QWidget):
    """Left: name / cost / type / stats / rules. Right: art."""

    def __init__(self) -> None:
        super().__init__()
        self._card: Optional[cards_db.Card] = None
        self._image_busy = False
        self._image_token = 0

        root = QHBoxLayout(self)
        root.setContentsMargins(2, 2, 2, 2)
        root.setSpacing(4)

        left = QVBoxLayout()
        left.setSpacing(4)

        self._name = QLabel("")
        self._name.setObjectName("mtgName")
        self._name.setWordWrap(True)
        left.addWidget(self._name)

        self._mana = QLabel("")
        self._mana.setObjectName("mtgMana")
        self._mana.setWordWrap(True)
        left.addWidget(self._mana)

        self._type = QLabel("")
        self._type.setObjectName("mtgType")
        self._type.setWordWrap(True)
        left.addWidget(self._type)

        self._stats = QLabel("")
        self._stats.setObjectName("mtgStats")
        left.addWidget(self._stats)

        self._oracle = QTextEdit()
        self._oracle.setReadOnly(True)
        self._oracle.setFocusPolicy(Qt.StrongFocus)
        self._oracle.setLineWrapMode(QTextEdit.WidgetWidth)
        self._oracle.setFont(QFont(font_family(), 10))
        left.addWidget(self._oracle, 1)

        root.addLayout(left, 11)

        self._art = QLabel("Art")
        self._art.setObjectName("mtgArt")
        self._art.setAlignment(Qt.AlignCenter)
        self._art.setMinimumWidth(112)
        self._art.setScaledContents(False)
        self._art.setFocusPolicy(Qt.NoFocus)
        root.addWidget(self._art, 10)

    def show_card(self, card: cards_db.Card) -> None:
        self._card = card
        self._image_token += 1
        token = self._image_token

        self._name.setText(card.name)
        self._mana.setText(card.mana_cost or "—")
        self._type.setText(card.type_line or "")
        bits = []
        if card.power or card.toughness:
            bits.append(f"{card.power or '*'}/{card.toughness or '*'}")
        if card.loyalty:
            bits.append(f"Loyalty {card.loyalty}")
        self._stats.setText(" · ".join(bits) if bits else "")
        self._oracle.setPlainText(card.oracle_text or "")

        local = cards_db.image_file_for(card)
        if local:
            self._set_art(local)
            return
        if not card.image_url:
            self._art.setPixmap(QPixmap())
            self._art.setText("No art")
            return
        self._art.setText("…")
        if self._image_busy:
            return
        self._image_busy = True

        def work() -> None:
            path = sync.download_card_image(card.id, card.image_url)
            QTimer.singleShot(0, lambda: self._on_image_ready(path, token))

        threading.Thread(target=work, name="mtg-art", daemon=True).start()

    def _on_image_ready(self, path: Optional[Path], token: int) -> None:
        self._image_busy = False
        if token != self._image_token:
            return
        if path and path.is_file():
            self._set_art(path)
            return
        self._art.setPixmap(QPixmap())
        self._art.setText("Art\nfailed")

    def _set_art(self, path: Path) -> None:
        pix = QPixmap(str(path))
        if pix.isNull():
            self._art.setText("Bad image")
            return
        scaled = pix.scaled(
            max(64, self._art.width() - 4),
            max(64, self._art.height() - 4),
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation,
        )
        self._art.setPixmap(scaled)
        self._art.setText("")

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        if self._card:
            local = cards_db.image_file_for(self._card)
            if local:
                self._set_art(local)


class MtgCardsPage(QWidget):
    def __init__(self, on_back: Callable[[], None]) -> None:
        super().__init__()
        self._on_back = on_back
        self.setProperty("digiTitle", "MTG Cards")
        self.setStyleSheet(_STYLE)
        self._cards: List[cards_db.Card] = []
        self._db_worker: Optional[_DbWorker] = None
        self._auto_sync_started = False
        self._chrome: Optional[QWidget] = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self._stack = QStackedWidget()
        outer.addWidget(self._stack, 1)

        # --- Search screen ---
        search_page = QWidget()
        root = QVBoxLayout(search_page)
        root.setContentsMargins(4, 2, 4, 4)
        root.setSpacing(4)

        self._status = QLabel("Checking card database…")
        self._status.setObjectName("mtgStatus")
        self._status.setWordWrap(True)
        root.addWidget(self._status)

        self._search = QLineEdit()
        self._search.setPlaceholderText("Search name or rules…")
        self._search.setFocusPolicy(Qt.StrongFocus)
        self._search.textChanged.connect(self._on_search_changed)
        root.addWidget(self._search)

        self._hint = QLabel("Confirm a result to open the card.")
        self._hint.setObjectName("mtgHint")
        self._hint.setWordWrap(True)
        root.addWidget(self._hint)

        self._results = QListWidget()
        self._results.setFocusPolicy(Qt.StrongFocus)
        self._results.itemActivated.connect(self._on_result_activate)
        self._results.digi_confirm = self._confirm_result  # type: ignore[attr-defined]
        root.addWidget(self._results, 1)

        self._stack.addWidget(search_page)

        # --- Detail screen ---
        self._detail = _CardDetailPage()
        self._stack.addWidget(self._detail)

        self._overlay = _DownloadOverlay(self)
        self._overlay.dismissed.connect(self._on_overlay_dismissed)

        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(280)
        self._search_timer.timeout.connect(self._run_search)

    def bind_chrome(self, chrome: QWidget) -> None:
        self._chrome = chrome

    def on_hardware_back(self) -> bool:
        if self._stack.currentIndex() != 0:
            self._show_search()
            return True
        return False

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        if not self._auto_sync_started:
            self._auto_sync_started = True
            QTimer.singleShot(50, self._auto_sync)
        elif self._stack.currentIndex() == 0:
            QTimer.singleShot(0, self._ensure_focus)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        if self._overlay.isVisible():
            self._overlay.setGeometry(self.rect())

    def _set_title(self, title: str) -> None:
        self.setProperty("digiTitle", title)
        if self._chrome is not None:
            self._chrome.setProperty("digiTitle", title)
        try:
            win = self.window()
            sync_title = getattr(win, "_sync_title", None)
            if callable(sync_title):
                sync_title()
        except Exception:
            pass

    def _show_search(self) -> None:
        self._stack.setCurrentIndex(0)
        self._set_title("MTG Cards")
        self._ensure_focus()

    def _show_detail(self, card: cards_db.Card) -> None:
        self._detail.show_card(card)
        self._stack.setCurrentIndex(1)
        self._set_title(card.name[:28])
        try:
            from esp_handset import digi_nav

            digi_nav.clear_highlights(self)
            self._detail._oracle.setFocus(Qt.OtherFocusReason)
            digi_nav._highlight(self._detail._oracle, True)
        except Exception:
            self._detail._oracle.setFocus(Qt.OtherFocusReason)

    def _ensure_focus(self) -> None:
        try:
            from esp_handset import digi_nav

            if self._overlay.isVisible() and self._overlay._ok.isVisible():
                digi_nav.clear_highlights(self)
                self._overlay._ok.setFocus(Qt.OtherFocusReason)
                digi_nav._highlight(self._overlay._ok, True)
                return
            if self._stack.currentIndex() != 0:
                return
            digi_nav.clear_highlights(self.window() if self.window() else self)
            target = self._search if self._search.isEnabled() else self._results
            if self._results.count() > 0 and self._results.hasFocus():
                target = self._results
            target.setFocus(Qt.OtherFocusReason)
            digi_nav._highlight(target, True)
        except Exception:
            if self._search.isEnabled():
                self._search.setFocus(Qt.OtherFocusReason)

    def _on_overlay_dismissed(self) -> None:
        self._refresh_status()
        self._ensure_focus()

    def _refresh_status(self) -> None:
        ready = cards_db.is_ready()
        downloading = self._db_worker is not None and self._db_worker.isRunning()
        self._search.setEnabled(ready and not downloading)
        self._results.setEnabled(not downloading)
        if downloading:
            return
        if ready:
            n = cards_db.card_count()
            self._status.setText(f"{n:,} cards · type to search")
            self._hint.setText("Confirm a result to open the card.")
        else:
            self._status.setText("No card database yet")
            self._hint.setText("Need Wi‑Fi once to download cards.")

    def _auto_sync(self) -> None:
        """On open: check Scryfall updated_at and download/index if needed."""
        if self._db_worker is not None and self._db_worker.isRunning():
            self._overlay.show_over()
            return
        ready = cards_db.is_ready()
        # Always check when opening; overlay only if work is needed / in progress
        self._search.setEnabled(False)
        self._results.setEnabled(False)
        if not ready:
            self._status.setText("Downloading card database…")
            self._overlay.set_progress("Checking…", 0)
            self._overlay.show_over()
        else:
            self._status.setText("Checking for updates…")
            # Quiet check — show overlay once progress moves past "up to date"
            self._overlay.set_progress("Checking for updates…", 1)
            self._overlay.show_over()

        QApplication.processEvents()
        print("[mtg-cards] auto-sync start", flush=True)
        self._db_worker = _DbWorker(self, force=False)
        self._db_worker.progress.connect(self._on_db_progress)
        self._db_worker.finished_ok.connect(self._on_db_ok)
        self._db_worker.finished_err.connect(self._on_db_err)
        self._db_worker.start()

    def _on_db_progress(self, message: str, percent: int) -> None:
        self._status.setText(f"{message} ({percent}%)")
        # Hide overlay for instant "already up to date" / offline-use-local
        quiet = percent >= 100 and (
            message.startswith("Up to date") or message.startswith("Offline")
        )
        if quiet:
            self._overlay.hide()
            return
        if not self._overlay.isVisible():
            self._overlay.show_over()
        self._overlay.set_progress(message, percent)

    def _on_db_ok(self, count: int) -> None:
        self._db_worker = None
        self._status.setText(f"{count:,} cards · type to search")
        if self._overlay.isVisible():
            self._overlay.set_success(count)
            QTimer.singleShot(600, self._overlay._dismiss)
        self._refresh_status()
        self._ensure_focus()
        print(f"[mtg-cards] auto-sync OK count={count}", flush=True)

    def _on_db_err(self, message: str) -> None:
        self._db_worker = None
        self._status.setText(f"Sync failed: {message[:60]}")
        if cards_db.is_ready():
            # Keep using local data
            self._overlay.hide()
            self._refresh_status()
            self._status.setText(
                f"{cards_db.card_count():,} cards · sync failed (using local)"
            )
            self._ensure_focus()
        else:
            self._overlay.set_error(message)
            self._ensure_focus()
        print(f"[mtg-cards] auto-sync FAIL {message}", flush=True)

    def _on_search_changed(self, _text: str) -> None:
        self._search_timer.start()

    def _run_search(self) -> None:
        q = self._search.text().strip()
        self._results.clear()
        self._cards = []
        if not q:
            self._hint.setText("Confirm a result to open the card.")
            return
        if not cards_db.is_ready():
            self._hint.setText("Database not ready yet.")
            return
        self._cards = cards_db.search(q, limit=40)
        for card in self._cards:
            item = QListWidgetItem(card.name)
            item.setData(Qt.UserRole, card.id)
            self._results.addItem(item)
        if self._cards:
            self._results.setCurrentRow(0)
            self._hint.setText(f"{len(self._cards)} hits · Confirm to open")
        else:
            self._hint.setText(f"No cards match “{q}”.")

    def _confirm_result(self) -> bool:
        item = self._results.currentItem()
        if item is None:
            return False
        self._open_item(item)
        return True

    def _on_result_activate(self, item: QListWidgetItem) -> None:
        self._open_item(item)

    def _open_item(self, item: QListWidgetItem) -> None:
        cid = item.data(Qt.UserRole)
        card = cards_db.get_card(str(cid))
        if card:
            self._show_detail(card)


def make_mtg_cards_page(on_back: Callable[[], None]) -> QWidget:
    body = MtgCardsPage(on_back)
    chrome = page_chrome("MTG Cards", body, on_back, scroll=False)
    body.bind_chrome(chrome)
    chrome.on_hardware_back = body.on_hardware_back  # type: ignore[attr-defined]
    return chrome
