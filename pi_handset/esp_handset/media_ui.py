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


def find_sidecar_subtitles(video: Path) -> List[Path]:
    """Same-folder .srt/.vtt/.ass next to the video (movie.srt, movie.en.srt, …)."""
    video = Path(video)
    if not video.is_file():
        return []
    parent = video.parent
    stem = video.stem
    found: List[Path] = []
    for ext in (".srt", ".vtt", ".ass", ".ssa", ".sub"):
        exact = parent / f"{stem}{ext}"
        if exact.is_file():
            found.append(exact)
        try:
            for p in parent.glob(f"{stem}.*{ext}"):
                if p.is_file() and p not in found:
                    found.append(p)
        except OSError:
            pass
    return found


def digivice_play(
    path: Path,
    *,
    start_sec: Optional[float] = None,
    sub_files: Optional[List[Path]] = None,
) -> bool:
    """Play media Digivice-friendly: hand off HDMI, Pi hwdec, Back/Escape quits.

    Start the player first; only hide Digivice hosts after mpv is alive so a
    failed launch never leaves a postage-stamp 240x320 window on HDMI.
    """
    from shutil import which
    import os
    import subprocess
    import threading
    import time as _time

    path = Path(path)
    if not path.is_file():
        return False

    codec_info = ""
    try:
        codec_info = probe_video_codec(path)
    except Exception:
        codec_info = ""

    subs: List[Path] = []
    for pth in list(sub_files or []) + find_sidecar_subtitles(path):
        try:
            rp = Path(pth).resolve()
        except OSError:
            continue
        if rp.is_file() and rp not in subs:
            subs.append(rp)

    def _find_kiosk():
        try:
            from PyQt5.QtWidgets import QApplication

            app = QApplication.instance()
            if app is None:
                return None
            for w in app.topLevelWidgets():
                ctl = getattr(w, "_kiosk_controller", None) or getattr(
                    w, "_multi_presenter", None
                )
                if ctl is not None:
                    return ctl
        except Exception:
            pass
        return None

    def _handoff_begin() -> None:
        ctl = _find_kiosk()
        if ctl is not None and hasattr(ctl, "begin_media_handoff"):
            ctl.begin_media_handoff()

    def _handoff_end() -> None:
        ctl = _find_kiosk()
        if ctl is None:
            return
        # Must run on Qt main thread — request_media_restore queues end_media_handoff
        if hasattr(ctl, "request_media_restore"):
            ctl.request_media_restore()
        elif hasattr(ctl, "end_media_handoff"):
            ctl.end_media_handoff()

    def _watch_subprocess(proc: subprocess.Popen) -> None:
        try:
            proc.wait()
        except Exception:
            pass
        _handoff_end()

    def _build_mpv_cmd() -> List[str]:
        conf = Path.home() / ".cache" / "digivice-mpv-input.conf"
        try:
            conf.parent.mkdir(parents=True, exist_ok=True)
            conf.write_text(
                "ESC quit\nENTER quit\nq quit\nBS quit\n"
                "s cycle sub\nj cycle sub\n"
                "v cycle-values sub-visibility yes no\n",
                encoding="utf-8",
            )
        except OSError:
            conf = Path("/tmp/digivice-mpv-input.conf")
            try:
                conf.write_text(
                    "ESC quit\nENTER quit\nq quit\nBS quit\n"
                    "s cycle sub\nj cycle sub\n"
                    "v cycle-values sub-visibility yes no\n",
                    encoding="utf-8",
                )
            except OSError:
                conf = None

        cmd = [
            "mpv",
            "--profile=fast",
            "--fullscreen",
            "--force-window=yes",
            "--ontop",
            "--osd-level=1",
            "--no-terminal",
            "--keep-open=no",
            # On Pi 4, auto-safe + OpenGL selects the DRM hardware path for
            # HEVC when the installed FFmpeg/mpv build supports it, while
            # retaining a usable fallback for H.264 and older installations.
            "--hwdec=auto-safe",
            "--hwdec-codecs=all",
            "--gpu-api=opengl",
            "--vo=gpu",
            "--framedrop=vo",
            "--vd-lavc-threads=4",
            "--video-sync=audio",
            "--interpolation=no",
            "--cache=yes",
            "--sub-visibility=yes",
            "--sub-auto=fuzzy",
            "--sub-font-size=48",
            "--sub-bold=yes",
            "--sub-border-size=2",
            "--sub-color=#FFFFFFFF",
            "--sub-border-color=#000000FF",
        ]
        for sp in subs:
            cmd.append(f"--sub-file={sp}")
        if start_sec is not None and start_sec > 0:
            cmd.append(f"--start={start_sec}")
        if conf is not None:
            cmd.append(f"--input-conf={conf}")
        cmd.append(str(path))
        return cmd

    def _mpv_log_path() -> Path:
        log_path = Path.home() / ".esp-handset" / "mpv-last.log"
        try:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            with open(log_path, "w", encoding="utf-8") as lf:
                lf.write(f"codec={codec_info or '?'}\n")
                sub_note = ", ".join(str(s) for s in subs) or "(auto/embedded)"
                lf.write(f"subs={sub_note}\n")
        except OSError:
            pass
        return log_path

    def _start_player(cmd: List[str], *, log_path: Optional[Path] = None) -> bool:
        """Launch player; hide Digivice after it is alive; restore when it exits."""
        if not cmd:
            return False

        try:
            from PyQt5.QtCore import QProcess, QTimer
            from PyQt5.QtWidgets import QApplication

            app = QApplication.instance()
        except Exception:
            app = None

        if app is not None:
            proc = QProcess(app)
            app._digivice_player = proc  # prevent GC while playing

            handoff_done = {"ok": False}

            def _maybe_handoff() -> None:
                if handoff_done["ok"]:
                    return
                if proc.state() == QProcess.NotRunning:
                    return
                handoff_done["ok"] = True
                _handoff_begin()

            def _on_finished(_code: int, _status: QProcess.ExitStatus) -> None:
                try:
                    del app._digivice_player
                except Exception:
                    pass
                _handoff_end()

            proc.finished.connect(_on_finished)
            proc.started.connect(lambda: QTimer.singleShot(400, _maybe_handoff))

            if log_path is not None:
                try:
                    with open(log_path, "a", encoding="utf-8") as lf:
                        lf.write(" ".join(cmd) + "\n\n")
                except OSError:
                    pass
                proc.setStandardOutputFile(os.devnull)
                proc.setStandardErrorFile(str(log_path))
            else:
                proc.setStandardOutputFile(os.devnull)
                proc.setStandardErrorFile(os.devnull)

            proc.start(cmd[0], cmd[1:])

            def _check_fail() -> None:
                if proc.state() == QProcess.NotRunning and not handoff_done["ok"]:
                    try:
                        if log_path is not None:
                            with open(log_path, "a", encoding="utf-8") as lf:
                                lf.write(
                                    f"\nplayer exited immediately code={proc.exitCode()}\n"
                                )
                    except OSError:
                        pass

            QTimer.singleShot(500, _check_fail)
            return True

        try:
            log_f = subprocess.DEVNULL
            if log_path is not None:
                log_f = open(log_path, "a", encoding="utf-8")
                log_f.write(" ".join(cmd) + "\n\n")
                log_f.flush()
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=log_f,
                start_new_session=True,
                env=os.environ.copy(),
            )
        except Exception as e:
            try:
                if log_path is not None:
                    with open(log_path, "a", encoding="utf-8") as lf:
                        lf.write(f"\nPopen failed: {e}\n")
            except OSError:
                pass
            return False

        _time.sleep(0.4)
        if proc.poll() is not None:
            try:
                if log_path is not None:
                    with open(log_path, "a", encoding="utf-8") as lf:
                        lf.write(f"\nplayer exited immediately code={proc.returncode}\n")
            except OSError:
                pass
            return False
        _handoff_begin()
        threading.Thread(target=_watch_subprocess, args=(proc,), daemon=True).start()
        return True

    if which("mpv"):
        log_path = _mpv_log_path()
        return _start_player(_build_mpv_cmd(), log_path=log_path)

    if which("ffplay"):
        cmd = ["ffplay", "-fs", "-autoexit", "-window_title", "Digivice"]
        if start_sec is not None and start_sec > 0:
            cmd.extend(["-ss", str(start_sec)])
        if subs:
            cmd.extend(["-vf", f"subtitles={subs[0]}"])
        cmd.append(str(path))
        return _start_player(cmd)

    if which("vlc"):
        cmd = [
            "vlc",
            "--fullscreen",
            "--play-and-exit",
            "--no-video-title-show",
            "--no-qt-fs-controller",
            "--qt-notification=0",
            "--avcodec-hw=any",
            "--sub-track=0",
        ]
        if start_sec is not None and start_sec > 0:
            cmd.append(f"--start-time={int(start_sec)}")
        for sp in subs:
            cmd.extend(["--sub-file", str(sp)])
        cmd.append(str(path))
        return _start_player(cmd)

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
