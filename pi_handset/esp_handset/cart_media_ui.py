"""USB cart DVD-style media menus — Media tile takeover when movies/tv cart is in."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Callable, List, Optional, Tuple

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import (
    QLabel,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

from esp_handset.cartridge import (
    Cartridge,
    MenuAssets,
    current,
    refresh,
    takeover_media_kind,
)
from esp_handset.media_ui import digivice_play, media_list, _MUTED, _TEXT, _ACCENT
from esp_handset.pages import page_chrome

_menu_audio: Optional[subprocess.Popen] = None


def stop_menu_audio() -> None:
    global _menu_audio
    proc = _menu_audio
    _menu_audio = None
    if proc is None:
        return
    try:
        proc.terminate()
    except Exception:
        pass
    try:
        proc.wait(timeout=0.8)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass


def start_menu_audio(path: Optional[Path]) -> None:
    """Loop theme music under the DVD menu (mpv/ffplay); silent if missing."""
    from shutil import which

    stop_menu_audio()
    if path is None or not path.is_file():
        return
    global _menu_audio
    if which("mpv"):
        _menu_audio = subprocess.Popen(
            [
                "mpv",
                "--no-video",
                "--loop=inf",
                "--really-quiet",
                "--no-terminal",
                "--volume=70",
                str(path),
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        return
    if which("ffplay"):
        _menu_audio = subprocess.Popen(
            [
                "ffplay",
                "-nodisp",
                "-autoexit",
                "-loop",
                "0",
                "-loglevel",
                "quiet",
                str(path),
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )


def _play_feature(path: Path) -> None:
    stop_menu_audio()
    digivice_play(path)


def _pick_menu(*assets: MenuAssets) -> MenuAssets:
    for a in assets:
        if a is None:
            continue
        if a.background or a.music or a.select_sound:
            return a
    return MenuAssets()


def media_cart_active() -> bool:
    try:
        return takeover_media_kind("movies") or takeover_media_kind("tv")
    except Exception:
        return False


def media_home_title() -> Optional[str]:
    """Home Media tile title when a movies/tv cart is mounted."""
    if not media_cart_active():
        return None
    cart = current()
    if cart is None:
        return None
    t = (cart.title or "").strip() or "Cart"
    return t[:18]


def make_cart_media_page(on_back: Callable[[], None]) -> QWidget:
    """DVD-style hub: title pick (if needed) → Play / Extras / seasons."""
    del on_back

    body = QWidget()
    body.setStyleSheet("background:#05080c;")
    root = QVBoxLayout(body)
    root.setContentsMargins(0, 0, 0, 0)
    root.setSpacing(0)

    bg = QLabel()
    bg.setAlignment(Qt.AlignCenter)
    bg.setMinimumHeight(120)
    bg.setStyleSheet("background:#0a1018;")
    bg.setScaledContents(False)
    root.addWidget(bg, 3)

    title_lab = QLabel("")
    title_lab.setAlignment(Qt.AlignCenter)
    title_lab.setWordWrap(True)
    title_lab.setStyleSheet(
        f"font-size:13px; font-weight:700; color:{_TEXT};"
        " background:rgba(0,0,0,160); padding:4px 6px;"
    )
    root.addWidget(title_lab)

    hint = QLabel("")
    hint.setAlignment(Qt.AlignCenter)
    hint.setStyleSheet(f"font-size:9px; color:{_MUTED}; padding:0 4px 2px;")
    root.addWidget(hint)

    lst = media_list()
    lst.setMaximumHeight(130)
    lst.setStyleSheet(
        lst.styleSheet()
        + f" QListWidget {{ background:rgba(10,16,24,220); border:none;"
        f" border-top:1px solid {_ACCENT}; }}"
    )
    root.addWidget(lst, 2)

    # Navigation stack: ("titles",) | ("movie", idx) | ("extras", idx) |
    # ("show", idx) | ("season", show_i, season_i)
    stack: List[Tuple] = []
    state = {"cart": None}  # type: ignore[var-annotated]
    actions: List[Tuple[str, Callable[[], None]]] = []

    def _set_bg(assets: MenuAssets) -> None:
        path = assets.background
        if path is not None and path.is_file():
            pm = QPixmap(str(path))
            if not pm.isNull():
                # Scale to label; KeepAspectRatioByExpanding for cover feel
                scaled = pm.scaled(
                    max(bg.width(), 240),
                    max(bg.height(), 160),
                    Qt.KeepAspectRatioByExpanding,
                    Qt.SmoothTransformation,
                )
                bg.setPixmap(scaled)
                return
        bg.clear()
        bg.setText("")
        bg.setStyleSheet("background:#0a1018;")

    def _fill(items: List[str], acts: List[Callable[[], None]]) -> None:
        nonlocal actions
        actions = [(items[i], acts[i]) for i in range(len(items))]
        lst.clear()
        for label in items:
            lst.addItem(QListWidgetItem(label))
        if items:
            lst.setCurrentRow(0)

    def _go_titles() -> None:
        cart: Optional[Cartridge] = state["cart"]
        stack.clear()
        stack.append(("titles",))
        if cart is None:
            title_lab.setText("No cart")
            hint.setText("Insert a media cartridge")
            _set_bg(MenuAssets())
            stop_menu_audio()
            _fill([], [])
            return
        assets = cart.menu
        _set_bg(assets)
        start_menu_audio(assets.music)
        title_lab.setText(cart.title)
        hint.setText("Select a title")

        labels: List[str] = []
        callbacks: List[Callable[[], None]] = []
        for i, m in enumerate(cart.movies):
            labels.append(m.title)
            callbacks.append(lambda i=i: _go_movie(i))
        for i, s in enumerate(cart.tv):
            labels.append(s.title)
            callbacks.append(lambda i=i: _go_show(i))
        if len(labels) == 1:
            # Single title → skip picker, open its menu
            callbacks[0]()
            return
        if not labels:
            hint.setText("Cart has no movies/TV")
        _fill(labels, callbacks)

    def _go_movie(idx: int) -> None:
        cart: Optional[Cartridge] = state["cart"]
        if cart is None or not (0 <= idx < len(cart.movies)):
            return
        movie = cart.movies[idx]
        stack[:] = [("titles",), ("movie", idx)]
        assets = _pick_menu(movie.menu, cart.menu)
        _set_bg(assets)
        start_menu_audio(assets.music or cart.menu.music)
        title_lab.setText(movie.title)
        hint.setText("DVD menu")

        labels = ["▶  Play"]
        callbacks: List[Callable[[], None]] = [
            lambda p=movie.path: _play_feature(p) if p.is_file() else None
        ]
        if movie.extras:
            labels.append("★  Extras")
            callbacks.append(lambda i=idx: _go_extras(i))
        if len(cart.movies) + len(cart.tv) > 1:
            labels.append("←  Titles")
            callbacks.append(_go_titles)
        _fill(labels, callbacks)

    def _go_extras(idx: int) -> None:
        cart: Optional[Cartridge] = state["cart"]
        if cart is None or not (0 <= idx < len(cart.movies)):
            return
        movie = cart.movies[idx]
        stack.append(("extras", idx))
        assets = _pick_menu(movie.menu, cart.menu)
        _set_bg(assets)
        title_lab.setText(f"{movie.title} · Extras")
        hint.setText("Special features")
        labels: List[str] = []
        callbacks: List[Callable[[], None]] = []
        for ex in movie.extras:
            labels.append(ex.title)
            callbacks.append(
                lambda p=ex.path: _play_feature(p) if p.is_file() else None
            )
        labels.append("←  Back")
        callbacks.append(lambda i=idx: _go_movie(i))
        _fill(labels, callbacks)

    def _go_show(idx: int) -> None:
        cart: Optional[Cartridge] = state["cart"]
        if cart is None or not (0 <= idx < len(cart.tv)):
            return
        show = cart.tv[idx]
        stack[:] = [("titles",), ("show", idx)]
        assets = _pick_menu(show.menu, cart.menu)
        _set_bg(assets)
        start_menu_audio(assets.music or cart.menu.music)
        title_lab.setText(show.title)
        hint.setText("Seasons")
        labels: List[str] = []
        callbacks: List[Callable[[], None]] = []
        # Play from first episode
        first = None
        if show.seasons and show.seasons[0].episodes:
            first = show.seasons[0].episodes[0].path
        if first is not None:
            labels.append("▶  Play")
            callbacks.append(
                lambda p=first: _play_feature(p) if p.is_file() else None
            )
        for si, season in enumerate(show.seasons):
            labels.append(season.title)
            callbacks.append(lambda s=idx, se=si: _go_season(s, se))
        if len(cart.movies) + len(cart.tv) > 1:
            labels.append("←  Titles")
            callbacks.append(_go_titles)
        _fill(labels, callbacks)

    def _go_season(show_i: int, season_i: int) -> None:
        cart: Optional[Cartridge] = state["cart"]
        if cart is None or not (0 <= show_i < len(cart.tv)):
            return
        show = cart.tv[show_i]
        if not (0 <= season_i < len(show.seasons)):
            return
        season = show.seasons[season_i]
        stack.append(("season", show_i, season_i))
        assets = _pick_menu(show.menu, cart.menu)
        _set_bg(assets)
        title_lab.setText(f"{show.title} · {season.title}")
        hint.setText("Episodes")
        labels: List[str] = []
        callbacks: List[Callable[[], None]] = []
        for ep in season.episodes:
            labels.append(ep.title)
            callbacks.append(
                lambda p=ep.path: _play_feature(p) if p.is_file() else None
            )
        labels.append("←  Back")
        callbacks.append(lambda s=show_i: _go_show(s))
        _fill(labels, callbacks)

    def do_activate(_item=None) -> None:
        row = lst.currentRow()
        if 0 <= row < len(actions):
            actions[row][1]()

    def rebuild() -> None:
        refresh(force=True)
        cart = current()
        if cart is None or not (
            cart.has_kind("movies") or cart.has_kind("tv")
        ):
            state["cart"] = None
            stop_menu_audio()
            title_lab.setText("No media cart")
            hint.setText("Media folder is available from home")
            _set_bg(MenuAssets())
            _fill([], [])
            return
        state["cart"] = cart
        # Prefer movie menu if single movie matches cart branding
        if len(cart.movies) == 1 and not cart.tv:
            _go_movie(0)
        elif len(cart.tv) == 1 and not cart.movies:
            _go_show(0)
        else:
            _go_titles()

    lst.itemActivated.connect(do_activate)
    # Confirm on Digivice often uses Enter / Return via digi_nav on buttons;
    # also double-activate via itemClicked for touch
    lst.itemClicked.connect(lambda _=None: None)

    def on_page_show() -> None:
        rebuild()

        def _refresh_bg() -> None:
            try:
                top = stack[-1] if stack else ("titles",)
                cart = state["cart"]
                if cart is None:
                    return
                if top[0] == "movie" and 0 <= top[1] < len(cart.movies):
                    m = cart.movies[top[1]]
                    _set_bg(_pick_menu(m.menu, cart.menu))
                elif top[0] in ("show", "season", "extras"):
                    if top[0] == "extras" and 0 <= top[1] < len(cart.movies):
                        m = cart.movies[top[1]]
                        _set_bg(_pick_menu(m.menu, cart.menu))
                    elif top[0] == "show" and 0 <= top[1] < len(cart.tv):
                        _set_bg(_pick_menu(cart.tv[top[1]].menu, cart.menu))
                    elif top[0] == "season":
                        si = top[1]
                        if 0 <= si < len(cart.tv):
                            _set_bg(_pick_menu(cart.tv[si].menu, cart.menu))
                else:
                    _set_bg(cart.menu)
            except Exception:
                pass

        from PyQt5.QtCore import QTimer

        QTimer.singleShot(50, _refresh_bg)

    def on_navigate_away() -> None:
        stop_menu_audio()

    def on_hardware_back() -> bool:
        if len(stack) <= 1:
            stop_menu_audio()
            return False  # shell pops to home
        kind = stack[-1][0]
        if kind == "extras":
            _go_movie(stack[-1][1])
            return True
        if kind == "season":
            _go_show(stack[-1][1])
            return True
        if kind in ("movie", "show"):
            cart = state["cart"]
            if cart and (len(cart.movies) + len(cart.tv) > 1):
                _go_titles()
                return True
            stop_menu_audio()
            return False
        stop_menu_audio()
        return False

    chrome = page_chrome("Cart", body, None, scroll=False)
    chrome.on_page_show = on_page_show  # type: ignore[attr-defined]
    chrome.on_navigate_away = on_navigate_away  # type: ignore[attr-defined]
    chrome.on_hardware_back = on_hardware_back  # type: ignore[attr-defined]

    # Digivice Confirm on list: shell digi_nav will focus list; map Return
    def digi_activate() -> bool:
        do_activate()
        return True

    chrome.digi_activate = digi_activate  # type: ignore[attr-defined]
    body.digi_activate = digi_activate  # type: ignore[attr-defined]
    lst.setProperty("digiPad", False)
    return chrome
