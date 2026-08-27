"""Digivice Share — Jellyfin server control (serve media to Fire TV / LAN)."""

from __future__ import annotations

import socket
import subprocess
from pathlib import Path
from typing import Callable, Optional, Tuple

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import (
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from esp_handset.pages import page_chrome


def _run(cmd: list, timeout: float = 12.0) -> Tuple[int, str]:
    try:
        r = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        out = ((r.stdout or "") + (r.stderr or "")).strip()
        return int(r.returncode), out
    except Exception as e:
        return 1, str(e)


def _ctl(*args: str, timeout: float = 20.0) -> Tuple[int, str]:
    bin_ = "/usr/local/bin/digivice-jellyfin-ctl"
    if not Path(bin_).is_file():
        bin_ = "digivice-jellyfin-ctl"
    return _run(["sudo", "-n", bin_, *args], timeout=timeout)


def _lan_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.4)
        s.connect(("1.1.1.1", 80))
        ip = s.getsockname()[0]
        s.close()
        if ip and not ip.startswith("127."):
            return ip
    except Exception:
        pass
    code, out = _ctl("url", timeout=5.0)
    if code == 0 and "://" in out:
        # http://x.x.x.x:8096
        try:
            return out.split("://", 1)[1].split(":", 1)[0]
        except Exception:
            pass
    return ""


def make_jellyfin_page(on_back: Callable[[], None]) -> QWidget:
    body = QWidget()
    body.setStyleSheet("background:#0e1620; color:#e8eef5;")
    lay = QVBoxLayout(body)
    lay.setContentsMargins(6, 4, 6, 6)
    lay.setSpacing(6)

    title = QLabel("Share · Jellyfin")
    title.setStyleSheet("font-size:15px; font-weight:700;")
    lay.addWidget(title)

    status = QLabel("…")
    status.setWordWrap(True)
    status.setAlignment(Qt.AlignCenter)
    status.setStyleSheet(
        "font-size:12px; font-weight:700; padding:8px;"
        " background:#16202c; border-radius:8px;"
    )
    lay.addWidget(status)

    url_lab = QLabel("")
    url_lab.setWordWrap(True)
    url_lab.setAlignment(Qt.AlignCenter)
    url_lab.setStyleSheet("font-size:11px; color:#5ec4a8; font-weight:700;")
    lay.addWidget(url_lab)

    hint = QLabel(
        "Fire TV: install Jellyfin → add this server.\n"
        "First setup: open the URL once on a PC."
    )
    hint.setWordWrap(True)
    hint.setStyleSheet("font-size:10px; color:#7a8a9a;")
    lay.addWidget(hint)

    _btn = (
        "QPushButton { font-size:12px; font-weight:700; padding:6px;"
        " background:#1e2a38; color:#e8eef5; border:1px solid #243040;"
        " border-radius:10px; }"
        'QPushButton[digiFocus="1"] { border:2px solid #FFE600; }'
    )
    _primary = (
        "QPushButton { font-size:12px; font-weight:700; color:#0a1218;"
        " background:#5ec4a8; border:none; border-radius:10px; }"
        'QPushButton[digiFocus="1"] { border:2px solid #FFE600; }'
    )

    start_btn = QPushButton("Start sharing")
    stop_btn = QPushButton("Stop")
    refresh_btn = QPushButton("Refresh cart path")
    for b in (start_btn, stop_btn, refresh_btn):
        b.setMinimumHeight(32)
        b.setFocusPolicy(Qt.StrongFocus)
        b.setStyleSheet(_btn)
    start_btn.setStyleSheet(_primary)
    lay.addWidget(start_btn)
    lay.addWidget(stop_btn)
    lay.addWidget(refresh_btn)
    lay.addStretch(1)

    busy = {"on": False}

    def paint() -> None:
        code, st = _ctl("status", timeout=5.0)
        st = (st or "").strip().splitlines()[-1] if st else "unknown"
        ip = _lan_ip()
        url = f"http://{ip}:8096" if ip else "http://<pi-ip>:8096"
        if st == "active":
            status.setText("Sharing · on")
            url_lab.setText(url)
            start_btn.setEnabled(False)
            stop_btn.setEnabled(True)
        elif st == "inactive":
            status.setText("Installed · off")
            url_lab.setText(url)
            start_btn.setEnabled(True)
            stop_btn.setEnabled(False)
        elif st == "missing":
            status.setText("Not installed\nSettings → Update")
            url_lab.setText("")
            start_btn.setEnabled(False)
            stop_btn.setEnabled(False)
        else:
            status.setText(st[:80] or "Unknown")
            url_lab.setText(url)

    def do_start() -> None:
        if busy["on"]:
            return
        busy["on"] = True
        status.setText("Starting…")
        start_btn.setEnabled(False)

        def _work() -> None:
            code, out = _ctl("start", timeout=45.0)
            QTimer.singleShot(0, lambda: _done_start(code, out))

        def _done_start(code: int, out: str) -> None:
            busy["on"] = False
            if code != 0:
                status.setText(f"Start failed\n{(out or '')[:90]}")
            paint()

        import threading

        threading.Thread(target=_work, daemon=True).start()

    def do_stop() -> None:
        if busy["on"]:
            return
        busy["on"] = True
        status.setText("Stopping…")

        def _work() -> None:
            _ctl("stop", timeout=20.0)
            QTimer.singleShot(0, _done_stop)

        def _done_stop() -> None:
            busy["on"] = False
            paint()

        import threading

        threading.Thread(target=_work, daemon=True).start()

    def do_refresh() -> None:
        code, out = _ctl("refresh-cart", timeout=10.0)
        status.setText((out or "Refreshed")[:100])
        QTimer.singleShot(1200, paint)

    start_btn.clicked.connect(do_start)
    stop_btn.clicked.connect(do_stop)
    refresh_btn.clicked.connect(do_refresh)

    paint()
    timer = QTimer(body)
    timer.setInterval(4000)
    timer.timeout.connect(paint)
    timer.start()

    return page_chrome("Share", body, on_back)
