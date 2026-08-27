"""Shared Digivice media chrome — calm dark lists for tiny screens."""

from __future__ import annotations

from pathlib import Path
from typing import Callable, List, Optional, Tuple

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import (
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

_BG = "#0e1620"
_SURFACE = "#16202c"
_BORDER = "#243040"
_TEXT = "#e8eef5"
_MUTED = "#7a8a9a"
_ACCENT = "#5ec4a8"
_ACCENT_DIM = "#1a3a32"


def media_btn(text: str, *, primary: bool = False) -> QPushButton:
    b = QPushButton(text)
    b.setFocusPolicy(Qt.StrongFocus)
    b.setCursor(Qt.PointingHandCursor)
    b.setMinimumHeight(30)
    if primary:
        b.setStyleSheet(
            f"QPushButton {{ font-size:11px; font-weight:700; padding:4px 10px;"
            f" color:#0a1218; background:{_ACCENT}; border:none; border-radius:8px; }}"
            'QPushButton[digiFocus="1"] { border:2px solid #FFE600; }'
        )
    else:
        b.setStyleSheet(
            f"QPushButton {{ font-size:11px; font-weight:600; padding:4px 10px;"
            f" color:{_TEXT}; background:#1e2a38; border:1px solid {_BORDER};"
            f" border-radius:8px; }}"
            'QPushButton[digiFocus="1"] { border:2px solid #FFE600; }'
        )
    return b


def media_list() -> QListWidget:
    lst = QListWidget()
    lst.setFocusPolicy(Qt.StrongFocus)
    lst.setStyleSheet(
        f"QListWidget {{ background:{_SURFACE}; border:1px solid {_BORDER};"
        f" border-radius:8px; font-size:12px; outline:none; color:{_TEXT}; }}"
        f"QListWidget::item {{ padding:8px 10px; border-bottom:1px solid {_BORDER}; }}"
        f"QListWidget::item:selected {{ background:{_ACCENT_DIM}; color:{_TEXT}; }}"
        'QListWidget[digiFocus="1"] { border:2px solid #FFE600; }'
    )
    return lst


def media_header(glyph: str, title: str, subtitle: str = "") -> QWidget:
    w = QWidget()
    lay = QHBoxLayout(w)
    lay.setContentsMargins(2, 0, 2, 2)
    lay.setSpacing(8)
    g = QLabel(glyph)
    g.setStyleSheet(
        f"font-size:22px; color:{_ACCENT}; min-width:28px;"
    )
    g.setAlignment(Qt.AlignCenter)
    col = QVBoxLayout()
    col.setSpacing(0)
    t = QLabel(title)
    t.setStyleSheet(f"font-size:13px; font-weight:700; color:{_TEXT};")
    col.addWidget(t)
    if subtitle:
        s = QLabel(subtitle)
        s.setStyleSheet(f"font-size:9px; color:{_MUTED};")
        s.setWordWrap(True)
        col.addWidget(s)
    lay.addWidget(g)
    lay.addLayout(col, 1)
    return w


def media_empty(message: str) -> QLabel:
    lab = QLabel(message)
    lab.setAlignment(Qt.AlignCenter)
    lab.setWordWrap(True)
    lab.setStyleSheet(
        f"color:{_MUTED}; font-size:11px; padding:16px;"
        f" background:{_SURFACE}; border-radius:8px; border:1px dashed {_BORDER};"
    )
    return lab


def style_media_body(body: QWidget) -> None:
    body.setStyleSheet(f"background:{_BG}; color:{_TEXT};")


def _pretty_size(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    if n < 1024 * 1024:
        return f"{n / 1024:.0f} KB"
    return f"{n / (1024 * 1024):.1f} MB"


def digivice_play(path: Path, *, start_sec: Optional[float] = None) -> bool:
    """Play media Digivice-friendly: Back/Escape quits; Pi hwdec; OK on HDMI too.

    ``start_sec`` seeks to a scene/chapter (mpv --start=).
    """
    from shutil import which
    import subprocess
    import platform

    path = Path(path)
    if not path.is_file():
        return False

    # Prefer mpv (not xdg-open → VLC). Digivice Back is Escape via buttons_inputd.
    # HDMI/SPI: push hardware decode hard — MKV is a container; codec is what matters.
    if which("mpv"):
        conf = Path.home() / ".cache" / "digivice-mpv-input.conf"
        try:
            conf.parent.mkdir(parents=True, exist_ok=True)
            conf.write_text("ESC quit\nENTER quit\nq quit\nBS quit\n", encoding="utf-8")
        except OSError:
            conf = Path("/tmp/digivice-mpv-input.conf")
            try:
                conf.write_text(
                    "ESC quit\nENTER quit\nq quit\nBS quit\n", encoding="utf-8"
                )
            except OSError:
                conf = None
        cmd = [
            "mpv",
            "--fullscreen",
            "--osd-level=0",
            "--no-terminal",
            "--keep-open=no",
            # auto (not auto-safe) — need real V4L2/DRM decode on Pi for 1080p
            "--hwdec=auto",
            "--hwdec-codecs=all",
            "--vo=gpu",
            "--gpu-context=auto",
            "--gpu-hwdec-interop=auto",
            "--framedrop=vo",
            "--video-latency-hacks=yes",
            "--cache=yes",
            "--demuxer-readahead-secs=20",
            "--demuxer-max-bytes=157286400",
            "--vd-lavc-threads=0",
            "--audio-buffer=0.15",
            # Prefer cheap scaling if GPU is busy (SPI or weak decode)
            "--scale=bilinear",
            "--cscale=bilinear",
            "--dscale=bilinear",
            "--correct-downscaling=no",
            "--sigmoid-upscaling=no",
            "--hdr-compute-peak=no",
        ]
        # Raspberry Pi: try V4L2 M2M first via hwdec-codecs; also hint profile
        machine = (platform.machine() or "").lower()
        if machine in ("aarch64", "armv7l", "armv6l"):
            cmd.extend(
                [
                    "--hwdec-extra-frames=8",
                    "--video-sync=display-vdrop",
                ]
            )
        if start_sec is not None and start_sec > 0:
            cmd.append(f"--start={start_sec}")
        if conf is not None:
            cmd.append(f"--input-conf={conf}")
        cmd.append(str(path))
        log_path = Path.home() / ".esp-handset" / "mpv-last.log"
        try:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            log_f = open(log_path, "w", encoding="utf-8")
            log_f.write(" ".join(cmd) + "\n\n")
            log_f.flush()
        except OSError:
            log_f = subprocess.DEVNULL
        subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=log_f,
            start_new_session=True,
        )
        return True
    if which("ffplay"):
        cmd = [
            "ffplay",
            "-fs",
            "-autoexit",
            "-window_title",
            "Digivice",
        ]
        if start_sec is not None and start_sec > 0:
            cmd.extend(["-ss", str(start_sec)])
        cmd.append(str(path))
        subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        return True
    if which("vlc"):
        # Avoid Qt fullscreen tip about needing an Escape key
        cmd = [
            "vlc",
            "--fullscreen",
            "--play-and-exit",
            "--no-video-title-show",
            "--no-qt-fs-controller",
            "--qt-notification=0",
            "--no-osd",
        ]
        if start_sec is not None and start_sec > 0:
            cmd.append(f"--start-time={int(start_sec)}")
        cmd.append(str(path))
        subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        return True
    if which("xdg-open"):
        subprocess.Popen(
            ["xdg-open", str(path)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        return True
    return False


def list_media_chapters(path: Path) -> List[Tuple[str, float]]:
    """Read embedded chapters via ffprobe — [(title, start_sec), ...]."""
    from shutil import which
    import json
    import subprocess

    path = Path(path)
    if not path.is_file() or not which("ffprobe"):
        return []
    try:
        out = subprocess.check_output(
            [
                "ffprobe",
                "-v",
                "quiet",
                "-print_format",
                "json",
                "-show_chapters",
                str(path),
            ],
            timeout=12,
            text=True,
        )
        data = json.loads(out or "{}")
    except Exception:
        return []
    scenes: List[Tuple[str, float]] = []
    for i, ch in enumerate(data.get("chapters") or []):
        if not isinstance(ch, dict):
            continue
        try:
            start = float(ch.get("start_time") or 0)
        except (TypeError, ValueError):
            continue
        tags = ch.get("tags") if isinstance(ch.get("tags"), dict) else {}
        title = str((tags or {}).get("title") or f"Scene {i + 1}").strip()
        scenes.append((title, max(0.0, start)))
    return scenes


def probe_video_codec(path: Path) -> str:
    """Best-effort codec name for diagnostics (e.g. h264, hevc)."""
    from shutil import which
    import json
    import subprocess

    path = Path(path)
    if not path.is_file() or not which("ffprobe"):
        return ""
    try:
        out = subprocess.check_output(
            [
                "ffprobe",
                "-v",
                "quiet",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=codec_name,width,height",
                "-of",
                "json",
                str(path),
            ],
            timeout=8,
            text=True,
        )
        data = json.loads(out or "{}")
        streams = data.get("streams") or []
        if not streams:
            return ""
        s0 = streams[0]
        codec = str(s0.get("codec_name") or "")
        w = s0.get("width")
        h = s0.get("height")
        if w and h:
            return f"{codec} {w}x{h}"
        return codec
    except Exception:
        return ""


def _cart_video_entries():
    """List (display_title, path) from mounted movies/tv cart."""
    try:
        from esp_handset.cartridge import current, takeover_media_kind
    except Exception:
        return []
    cart = current()
    if cart is None:
        return []
    out = []
    if takeover_media_kind("movies"):
        for m in cart.movies:
            if m.path.is_file():
                out.append((m.title, m.path))
            for ex in m.extras:
                if ex.path.is_file():
                    out.append((f"{m.title} · {ex.title}", ex.path))
    if takeover_media_kind("tv"):
        for show in cart.tv:
            for season in show.seasons:
                for ep in season.episodes:
                    if ep.path.is_file():
                        out.append(
                            (f"{show.title} · {season.title} · {ep.title}", ep.path)
                        )
    return out


def _cart_music_entries():
    try:
        from esp_handset.cartridge import current, takeover_media_kind
    except Exception:
        return []
    cart = current()
    if cart is None or not takeover_media_kind("music"):
        return []
    out = []
    audio_ext = {".flac", ".mp3", ".ogg", ".opus", ".wav", ".m4a"}
    for album in cart.music:
        p = album.path
        if p.is_file() and p.suffix.lower() in audio_ext:
            out.append((album.title, p))
        elif p.is_dir():
            files = sorted(
                [
                    f
                    for f in p.iterdir()
                    if f.is_file() and f.suffix.lower() in audio_ext
                ],
                key=lambda x: x.name.lower(),
            )
            for f in files:
                out.append((f"{album.title} · {f.stem}", f))
    return out


def make_library_page(
    *,
    title: str,
    glyph: str,
    folder: Path,
    patterns: Tuple[str, ...],
    on_back: Callable[[], None],
    kind_label: str = "files",
    open_cmd: Optional[List[str]] = None,
    open_label: str = "Play",
    cart_kind: str = "",
) -> QWidget:
    """Polished file library for Music / Videos / Audiobooks (+ USB cart takeover)."""
    import subprocess

    del on_back
    body = QWidget()
    style_media_body(body)
    root = QVBoxLayout(body)
    root.setContentsMargins(4, 2, 4, 2)
    root.setSpacing(4)

    head = media_header(glyph, title, str(folder).replace(str(Path.home()), "~"))
    root.addWidget(head)

    count_lab = QLabel("")
    count_lab.setStyleSheet(f"font-size:9px; color:{_MUTED}; padding-left:2px;")
    root.addWidget(count_lab)

    lst = media_list()
    lst.setWordWrap(True)
    lst.setUniformItemSizes(False)
    lst.setSpacing(2)
    empty = media_empty(f"No {kind_label} yet.\nDrop files into\n{folder.name}/")
    empty.hide()
    root.addWidget(lst, 1)
    root.addWidget(empty)

    row = QHBoxLayout()
    row.setSpacing(4)
    open_btn = media_btn(open_label, primary=True)
    refresh_btn = media_btn("Refresh")
    row.addWidget(open_btn, 2)
    row.addWidget(refresh_btn, 1)
    root.addLayout(row)

    # (display name, path)
    entries: List[Tuple[str, Path]] = []
    state = {"from_cart": False}

    def _set_subtitle(sub: str) -> None:
        for child in head.findChildren(QLabel):
            ss = child.styleSheet() or ""
            if "font-size:9px" in ss:
                child.setText(sub)
                return

    def do_refresh() -> None:
        entries.clear()
        state["from_cart"] = False
        cart_list: List[Tuple[str, Path]] = []
        if cart_kind == "videos":
            cart_list = _cart_video_entries()
        elif cart_kind == "music":
            cart_list = _cart_music_entries()
        elif cart_kind == "audiobooks":
            try:
                from esp_handset.cartridge import current, takeover_media_kind

                cart = current()
                if cart is not None and takeover_media_kind("audiobooks"):
                    audio_ext = {".flac", ".mp3", ".ogg", ".opus", ".wav", ".m4a"}
                    for book in cart.audiobooks:
                        p = book.path
                        if p.is_file() and p.suffix.lower() in audio_ext:
                            cart_list.append((book.title, p))
                        elif p.is_dir():
                            for f in sorted(
                                [
                                    x
                                    for x in p.iterdir()
                                    if x.is_file() and x.suffix.lower() in audio_ext
                                ],
                                key=lambda x: x.name.lower(),
                            ):
                                cart_list.append((f"{book.title} · {f.stem}", f))
            except Exception:
                cart_list = []

        if cart_list:
            state["from_cart"] = True
            entries.extend(cart_list)
            try:
                from esp_handset.cartridge import current

                c = current()
                sub = f"Cart · {c.title}" if c else "USB cart"
            except Exception:
                sub = "USB cart"
            _set_subtitle(sub)
        else:
            folder.mkdir(parents=True, exist_ok=True)
            found: List[Path] = []
            for pat in patterns:
                found.extend(folder.glob(pat))
            for p in sorted(set(found), key=lambda x: x.name.lower()):
                entries.append((p.stem, p))
            _set_subtitle(str(folder).replace(str(Path.home()), "~"))

        lst.clear()
        for name, p in entries:
            try:
                sz = _pretty_size(p.stat().st_size)
            except OSError:
                sz = ""
            item = QListWidgetItem(f"{name}\n{p.suffix.lstrip('.').upper()}  ·  {sz}")
            if sz:
                item.setToolTip(sz)
            lst.addItem(item)
        tag = "cart titles" if state["from_cart"] else kind_label
        count_lab.setText(f"{len(entries)} {tag}")
        if not entries:
            lst.hide()
            empty.setText(
                f"No {kind_label} yet.\nDrop files into\n{folder.name}/"
                if not state["from_cart"]
                else "Cart has no playable files."
            )
            empty.show()
        else:
            empty.hide()
            lst.show()

    def do_open() -> None:
        row_i = lst.currentRow()
        if not (0 <= row_i < len(entries)):
            return
        _name, path = entries[row_i]
        if open_cmd:
            subprocess.Popen(
                open_cmd + [str(path)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            return
        digivice_play(path)

    open_btn.clicked.connect(do_open)
    refresh_btn.clicked.connect(do_refresh)
    lst.itemActivated.connect(lambda _=None: do_open())

    def on_page_show() -> None:
        try:
            from esp_handset.cartridge import refresh

            refresh(force=True)
        except Exception:
            pass
        do_refresh()

    chrome = page_chrome(title, body, None, scroll=False)
    chrome.on_page_show = on_page_show  # type: ignore[attr-defined]
    do_refresh()
    return chrome
