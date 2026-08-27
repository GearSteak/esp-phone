"""In-Digivice browser — embedded web view inside Digivice chrome.

Prefers Qt WebEngine; falls back to Qt WebKit (QWebView) which is what
Raspberry Pi OS actually packages for ARM. External light browser is a
last-resort button if neither binding imports.
"""

from __future__ import annotations

from typing import Callable, Optional, Tuple

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


def _probe_backends() -> Tuple[Optional[str], Optional[type]]:
    """Return (name, view_class) for the first working web widget."""
    try:
        from PyQt5.QtWebEngineWidgets import QWebEngineView

        return "webengine", QWebEngineView
    except Exception:
        pass
    try:
        from PyQt5.QtWebKitWidgets import QWebView

        return "webkit", QWebView
    except Exception:
        pass
    return None, None


def webengine_available() -> bool:
    """True if any embedded web backend can import (Engine or WebKit)."""
    name, _ = _probe_backends()
    return name is not None


def make_browser_page(on_back: Callable[[], None]) -> QWidget:
    """Skinned browser page using WebEngine or WebKit."""
    del on_back
    body = QWidget()
    lay = QVBoxLayout(body)
    lay.setContentsMargins(2, 2, 2, 2)
    lay.setSpacing(2)

    backend, view_cls = _probe_backends()
    if view_cls is None:
        msg = QLabel(
            "No embedded browser package yet.\n\n"
            "Run Settings → Update — it installs\n"
            "Qt WebKit (and WebEngine when available).\n\n"
            "Or open a light browser on the desktop."
        )
        msg.setWordWrap(True)
        msg.setStyleSheet("color:#e8eef5; font-size:11px; padding:8px;")
        lay.addWidget(msg)
        ext = QPushButton("Open external browser")
        ext.setMinimumHeight(32)
        ext.setFocusPolicy(Qt.StrongFocus)
        ext.setStyleSheet(
            "QPushButton { font-size:12px; font-weight:700; color:#0a1218;"
            " background:#5ec4a8; border:none; border-radius:10px; }"
            'QPushButton[digiFocus="1"] { border:2px solid #FFE600; }'
        )

        def _open_ext() -> None:
            try:
                from esp_handset.apps import open_browser

                open_browser()
            except Exception as e:
                msg.setText(f"Could not open external browser:\n{e}")

        ext.clicked.connect(_open_ext)
        lay.addWidget(ext)
        lay.addStretch(1)
        return page_chrome("Browser", body, None, scroll=False)

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

    view = view_cls()
    view.setStyleSheet("background:#000;")
    lay.addWidget(view, 1)

    def _set_url(text: str) -> None:
        q = QUrl(text)
        if hasattr(view, "setUrl"):
            view.setUrl(q)
        else:
            view.load(q)

    def navigate() -> None:
        text = (url.text() or "").strip()
        if not text:
            return
        if "://" not in text:
            text = "https://" + text
        url.setText(text)
        _set_url(text)

    def on_url_changed(qurl: QUrl) -> None:
        url.setText(qurl.toString())

    back_btn.clicked.connect(view.back)
    fwd_btn.clicked.connect(view.forward)
    go_btn.clicked.connect(navigate)
    url.returnPressed.connect(navigate)
    if hasattr(view, "urlChanged"):
        view.urlChanged.connect(on_url_changed)

    _set_url("https://duckduckgo.com/")
    url.setText("https://duckduckgo.com/")

    chrome = page_chrome("Browser", body, None, scroll=False)

    def digi_activate() -> bool:
        if url.hasFocus():
            navigate()
            return True
        return False

    chrome.digi_activate = digi_activate  # type: ignore[attr-defined]
    chrome.browser_view = view  # type: ignore[attr-defined]
    chrome.browser_backend = backend  # type: ignore[attr-defined]
    return chrome
