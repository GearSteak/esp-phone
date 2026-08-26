"""In-Digivice browser — embedded web view inside Digivice chrome."""

from __future__ import annotations

from typing import Callable, Optional

from PyQt5.QtCore import Qt, QUrl
from PyQt5.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from esp_handset.pages import page_chrome


def webengine_available() -> bool:
    try:
        from PyQt5.QtWebEngineWidgets import QWebEngineView  # noqa: F401

        return True
    except Exception:
        return False


def make_browser_page(on_back: Callable[[], None]) -> QWidget:
    """Skinned browser page. Requires PyQt5 QtWebEngineWidgets."""
    del on_back
    body = QWidget()
    lay = QVBoxLayout(body)
    lay.setContentsMargins(2, 2, 2, 2)
    lay.setSpacing(2)

    if not webengine_available():
        msg = QLabel(
            "Embedded browser needs Qt WebEngine.\n\n"
            "Run Settings → Update (or on the Pi):\n"
            "  sudo apt install python3-pyqt5.qtwebengine\n\n"
            "Then reopen Browser."
        )
        msg.setWordWrap(True)
        msg.setStyleSheet("color:#e8eef5; font-size:11px; padding:8px;")
        lay.addWidget(msg)
        lay.addStretch(1)
        return page_chrome("Browser", body, None, scroll=False)

    from PyQt5.QtWebEngineWidgets import QWebEngineView

    bar = QHBoxLayout()
    bar.setSpacing(2)
    back_btn = QPushButton("‹")
    back_btn.setFixedSize(28, 26)
    fwd_btn = QPushButton("›")
    fwd_btn.setFixedSize(28, 26)
    go_btn = QPushButton("Go")
    go_btn.setFixedHeight(26)
    go_btn.setStyleSheet("font-weight:800;")
    url = QLineEdit()
    url.setPlaceholderText("https://…")
    url.setFixedHeight(26)
    url.setStyleSheet(
        "font-size:10px; padding:3px 6px; background:#16202c; color:#e8eef5;"
        " border:1px solid #243040; border-radius:6px;"
    )
    for b in (back_btn, fwd_btn, go_btn):
        b.setFocusPolicy(Qt.StrongFocus)
        b.setStyleSheet(
            "QPushButton { font-size:12px; font-weight:700; background:#1e2a38;"
            " color:#e8eef5; border:1px solid #243040; border-radius:6px; }"
            'QPushButton[digiFocus="1"] { border:2px solid #FFE600; }'
        )
    bar.addWidget(back_btn)
    bar.addWidget(fwd_btn)
    bar.addWidget(url, 1)
    bar.addWidget(go_btn)
    lay.addLayout(bar)

    view = QWebEngineView()
    view.setStyleSheet("background:#000;")
    lay.addWidget(view, 1)

    def navigate() -> None:
        text = (url.text() or "").strip()
        if not text:
            return
        if "://" not in text:
            text = "https://" + text
        url.setText(text)
        view.setUrl(QUrl(text))

    def on_url_changed(qurl: QUrl) -> None:
        url.setText(qurl.toString())

    back_btn.clicked.connect(view.back)
    fwd_btn.clicked.connect(view.forward)
    go_btn.clicked.connect(navigate)
    url.returnPressed.connect(navigate)
    view.urlChanged.connect(on_url_changed)

    view.setUrl(QUrl("https://duckduckgo.com/"))
    url.setText("https://duckduckgo.com/")

    chrome = page_chrome("Browser", body, None, scroll=False)

    def digi_activate() -> bool:
        if url.hasFocus():
            navigate()
            return True
        return False

    chrome.digi_activate = digi_activate  # type: ignore[attr-defined]
    chrome.browser_view = view  # type: ignore[attr-defined]
    return chrome
