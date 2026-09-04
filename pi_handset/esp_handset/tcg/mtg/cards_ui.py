"""MTG card search — local Scryfall database, text left / art right."""

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
    QPushButton,
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
    font-size: 12px; background: #121820; color: #e8eef5;
    border: 1px solid #3a5068;
}
QListWidget[digiFocus="1"] { border: 2px solid #FFE600; }
QListWidget::item:selected { background: #2a4a68; }
QTextEdit {
    font-size: 11px; background: #0e1620; color: #e8eef5;
    border: 1px solid #3a5068; padding: 4px;
}
QLabel#mtgArt { background: #0a1018; border: 1px solid #3a5068; }
QPushButton {
    font-size: 12px; padding: 8px; background: #2a4a68; color: #fff;
    border: 2px solid #3a5068; border-radius: 4px;
}
QPushButton[digiFocus="1"] { border: 2px solid #FFE600; background: #3a6a98; }
QPushButton:disabled { background: #2a3038; color: #888; }
QLabel#mtgStatus { font-size: 11px; color: #9ab; }
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


class MtgCardsPage(QWidget):
    def __init__(self, on_back: Callable[[], None]) -> None:
        super().__init__()
        self._on_back = on_back
        self.setProperty("digiTitle", "MTG Cards")
        self.setStyleSheet(_STYLE)
        self._cards: List[cards_db.Card] = []
        self._selected: Optional[cards_db.Card] = None
        self._db_worker: Optional[_DbWorker] = None
        self._image_busy = False

        root = QVBoxLayout(self)
        root.setContentsMargins(4, 2, 4, 4)
        root.setSpacing(4)

        self._status = QLabel("Local card search · Scryfall data")
        self._status.setObjectName("mtgStatus")
        self._status.setWordWrap(True)
        root.addWidget(self._status)

        self._download_btn = QPushButton("Download database (~120 MB)")
        self._download_btn.setFocusPolicy(Qt.StrongFocus)
        self._download_btn.setMinimumHeight(40)
        self._download_btn.clicked.connect(lambda: self._start_download(force=False))
        self._download_btn.digi_confirm = lambda: self._start_download(force=False)  # type: ignore[attr-defined]
        root.addWidget(self._download_btn)

        row = QHBoxLayout()
        self._search = QLineEdit()
        self._search.setPlaceholderText("Search name or rules text…")
        self._search.setFocusPolicy(Qt.StrongFocus)
        self._search.textChanged.connect(self._on_search_changed)
        row.addWidget(self._search, 1)
        self._sync_btn = QPushButton("Re-dl")
        self._sync_btn.setMinimumWidth(52)
        self._sync_btn.setToolTip("Force re-download database")
        self._sync_btn.setFocusPolicy(Qt.StrongFocus)
        self._sync_btn.clicked.connect(lambda: self._start_download(force=True))
        self._sync_btn.digi_confirm = lambda: self._start_download(force=True)  # type: ignore[attr-defined]
        row.addWidget(self._sync_btn)
        root.addLayout(row)

        self._results = QListWidget()
        self._results.setMaximumHeight(88)
        self._results.setFocusPolicy(Qt.StrongFocus)
        self._results.itemClicked.connect(self._on_result_pick)
        self._results.currentItemChanged.connect(self._on_result_current)
        self._results.hide()
        root.addWidget(self._results)

        split = QHBoxLayout()
        split.setSpacing(4)

        self._text = QTextEdit()
        self._text.setReadOnly(True)
        self._text.setFocusPolicy(Qt.NoFocus)
        self._text.setLineWrapMode(QTextEdit.WidgetWidth)
        self._text.setFont(QFont(font_family(), 10))
        split.addWidget(self._text, 11)

        self._art = QLabel("Art")
        self._art.setObjectName("mtgArt")
        self._art.setAlignment(Qt.AlignCenter)
        self._art.setMinimumWidth(108)
        self._art.setScaledContents(False)
        self._art.setFocusPolicy(Qt.NoFocus)
        split.addWidget(self._art, 9)

        root.addLayout(split, 1)

        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(280)
        self._search_timer.timeout.connect(self._run_search)

        self._refresh_ready_state()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._refresh_ready_state()
        QTimer.singleShot(0, self._ensure_focus)

    def _ensure_focus(self) -> None:
        try:
            from esp_handset import digi_nav

            root = self.window() if self.window() else self
            digi_nav.clear_highlights(root)
            target = (
                self._download_btn
                if self._download_btn.isVisible() and self._download_btn.isEnabled()
                else self._search
            )
            target.setFocus(Qt.OtherFocusReason)
            digi_nav._highlight(target, True)
        except Exception:
            if self._download_btn.isVisible() and self._download_btn.isEnabled():
                self._download_btn.setFocus(Qt.OtherFocusReason)
            elif self._search.isEnabled():
                self._search.setFocus(Qt.OtherFocusReason)

    def _refresh_ready_state(self) -> None:
        ready = cards_db.is_ready()
        downloading = self._db_worker is not None and self._db_worker.isRunning()
        self._download_btn.setVisible(not ready)
        self._download_btn.setEnabled(not downloading)
        self._search.setEnabled(ready and not downloading)
        self._sync_btn.setEnabled(not downloading)
        self._sync_btn.setVisible(True)
        if downloading:
            return
        if ready:
            n = cards_db.card_count()
            self._status.setText(
                f"{n:,} cards · Confirm=Search type · Re-dl=refresh"
            )
            if not self._text.toPlainText().strip() or self._text.toPlainText().startswith(
                "Confirm on Download"
            ):
                self._text.setPlainText(
                    "Confirm on Search → type with CardKB.\n"
                    "D-pad moves focus · Confirm activates.\n\n"
                    "Art downloads the first time you open a card."
                )
        else:
            self._status.setText("Needs Wi‑Fi · Confirm Download (~120 MB)")
            self._text.setPlainText(
                "Confirm on Download database.\n\n"
                "Status updates here while it runs\n"
                "(can take several minutes)."
            )

    def _start_download(self, force: bool = False) -> bool:
        if self._db_worker is not None and self._db_worker.isRunning():
            self._status.setText("Already downloading…")
            return True
        self._download_btn.setEnabled(False)
        self._sync_btn.setEnabled(False)
        self._search.setEnabled(False)
        self._status.setText("Starting download…")
        self._text.setPlainText(
            "Download started.\n\n"
            "1) Contact Scryfall\n"
            "2) Pull ~120 MB JSON\n"
            "3) Build search index\n\n"
            "Keep Wi‑Fi on. Do not leave this page."
        )
        QApplication.processEvents()
        print(f"[mtg-cards] download start force={force}", flush=True)

        self._db_worker = _DbWorker(self, force=force)
        self._db_worker.progress.connect(self._on_db_progress)
        self._db_worker.finished_ok.connect(self._on_db_ok)
        self._db_worker.finished_err.connect(self._on_db_err)
        self._db_worker.start()
        return True

    def _on_db_progress(self, message: str, percent: int) -> None:
        line = f"{message} ({percent}%)"
        self._status.setText(line)
        # Keep a short live log in the text pane
        self._text.setPlainText(
            "Downloading card database…\n\n"
            f"{line}\n\n"
            "Stay on this screen."
        )

    def _on_db_ok(self, count: int) -> None:
        self._db_worker = None
        self._status.setText(f"Ready — {count:,} cards")
        self._text.setPlainText(
            f"Indexed {count:,} cards.\n\n"
            "Confirm on Search and type a name."
        )
        self._refresh_ready_state()
        self._ensure_focus()
        print(f"[mtg-cards] download OK count={count}", flush=True)

    def _on_db_err(self, message: str) -> None:
        self._db_worker = None
        self._status.setText(f"FAILED: {message[:80]}")
        self._text.setPlainText(
            "Download failed.\n\n"
            f"{message}\n\n"
            "Check Wi‑Fi, then Confirm Download again."
        )
        self._refresh_ready_state()
        self._ensure_focus()
        print(f"[mtg-cards] download FAIL {message}", flush=True)

    def _on_search_changed(self, _text: str) -> None:
        self._search_timer.start()

    def _run_search(self) -> None:
        q = self._search.text().strip()
        if not q:
            self._results.clear()
            self._results.hide()
            return
        if not cards_db.is_ready():
            return
        self._cards = cards_db.search(q, limit=30)
        self._results.clear()
        for card in self._cards:
            item = QListWidgetItem(card.name)
            item.setData(Qt.UserRole, card.id)
            self._results.addItem(item)
        if self._cards:
            self._results.show()
            self._results.setCurrentRow(0)
            self._show_card(self._cards[0])
        else:
            self._results.hide()
            self._text.setPlainText(f"No cards match “{q}”.")
            self._art.setText("—")
            self._art.setPixmap(QPixmap())

    def _on_result_pick(self, item: QListWidgetItem) -> None:
        self._select_item(item)

    def _on_result_current(
        self, current: Optional[QListWidgetItem], _previous: Optional[QListWidgetItem]
    ) -> None:
        if current is not None:
            self._select_item(current)

    def _select_item(self, item: QListWidgetItem) -> None:
        cid = item.data(Qt.UserRole)
        card = cards_db.get_card(str(cid))
        if card:
            self._show_card(card)

    def _show_card(self, card: cards_db.Card) -> None:
        self._selected = card
        self._text.setPlainText(card.display_text())
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
            QTimer.singleShot(0, lambda p=path: self._on_image_ready(p))

        threading.Thread(target=work, name="mtg-art", daemon=True).start()

    def _on_image_ready(self, path: Optional[Path]) -> None:
        self._image_busy = False
        if path and path.is_file():
            self._set_art(path)
            return
        if self._selected:
            self._art.setPixmap(QPixmap())
            self._art.setText("Art\nfailed")

    def _set_art(self, path: Path) -> None:
        pix = QPixmap(str(path))
        if pix.isNull():
            self._art.setText("Bad image")
            return
        scaled = pix.scaled(
            self._art.size(),
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation,
        )
        self._art.setPixmap(scaled)
        self._art.setText("")

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self._selected:
            local = cards_db.image_file_for(self._selected)
            if local:
                self._set_art(local)


def make_mtg_cards_page(on_back: Callable[[], None]) -> QWidget:
    body = MtgCardsPage(on_back)
    return page_chrome("MTG Cards", body, on_back, scroll=False)
