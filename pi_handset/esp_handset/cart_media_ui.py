"""USB cart DVD-style media menus — Media tile takeover when movies/tv cart is in."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Callable, List, Optional, Tuple

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidgetItem,
    QPushButton,
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
from esp_handset.media_ui import (
    digivice_play,
    list_media_chapters,
    media_btn,
    media_list,
)
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


def _play_feature(path: Path, start_sec: Optional[float] = None) -> None:
    stop_menu_audio()
    digivice_play(path, start_sec=start_sec)


def _pick_menu(*assets: MenuAssets) -> MenuAssets:
    for a in assets:
        if a is None:
            continue
        if a.background or a.logo or a.music or a.select_sound:
            return a
    return MenuAssets()


def _pick_logo(assets: MenuAssets, cart: Optional[Cartridge]) -> Optional[Path]:
    if assets.logo is not None and assets.logo.is_file():
        return assets.logo
    if cart is not None and cart.logo is not None and cart.logo.is_file():
        return cart.logo
    if cart is not None and cart.menu.logo is not None and cart.menu.logo.is_file():
        return cart.menu.logo
    return None


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


def media_home_logo() -> Optional[Path]:
    """Logo for home Media center stage (above the cart name)."""
    if not media_cart_active():
        return None
    cart = current()
    if cart is None:
        return None
    return _pick_logo(cart.menu, cart)


def _small_menu_btn(text: str) -> QPushButton:
    b = media_btn(text, primary=False)
    b.setMinimumHeight(26)
    b.setMaximumHeight(28)
    b.setStyleSheet(
        "QPushButton { font-size:10px; font-weight:700; padding:3px 8px;"
        " color:#e8eef5; background:#1a2430; border:1px solid #3a4a5a;"
        " border-radius:6px; min-width:52px; }"
        'QPushButton[digiFocus="1"] { border:2px solid #FFE600; }'
    )
    return b


def make_cart_media_page(on_back: Callable[[], None]) -> QWidget:
    """DVD hub: optional bg + Play / Extras / Scenes (logo+name are on home Media)."""
    del on_back

    body = QWidget()
    body.setStyleSheet("background:#05080c;")
    root = QVBoxLayout(body)
    root.setContentsMargins(6, 4, 6, 4)
    root.setSpacing(4)

    bg = QLabel()
    bg.setAlignment(Qt.AlignCenter)
    bg.setMinimumHeight(100)
    bg.setStyleSheet("background:#0a1018;")
    bg.setScaledContents(False)

    btn_row = QWidget()
    btn_lay = QHBoxLayout(btn_row)
    btn_lay.setContentsMargins(8, 0, 8, 4)
    btn_lay.setSpacing(8)
    play_btn = _small_menu_btn("Play")
    extras_btn = _small_menu_btn("Extras")
    scenes_btn = _small_menu_btn("Scenes")
    btn_lay.addStretch(1)
    btn_lay.addWidget(play_btn)
    btn_lay.addWidget(extras_btn)
    btn_lay.addWidget(scenes_btn)
    btn_lay.addStretch(1)

    lst = media_list()
    lst.setMaximumHeight(140)
    lst.hide()

    root.addWidget(bg, 1)
    root.addWidget(btn_row, 0)
    root.addWidget(lst, 1)

    stack: List[Tuple] = []
    state = {"cart": None}  # type: ignore[var-annotated]
    actions: List[Callable[[], None]] = []
    play_cb: Optional[Callable[[], None]] = None
    extras_cb: Optional[Callable[[], None]] = None
    scenes_cb: Optional[Callable[[], None]] = None

    def _set_bg(assets: MenuAssets) -> None:
        path = assets.background
        if path is not None and path.is_file():
            pm = QPixmap(str(path))
            if not pm.isNull():
                scaled = pm.scaled(
                    max(body.width(), 220),
                    max(body.height() - 40, 120),
                    Qt.KeepAspectRatioByExpanding,
                    Qt.SmoothTransformation,
                )
                bg.setPixmap(scaled)
                bg.show()
                return
        bg.clear()
        bg.setStyleSheet("background:#0a1018;")
        bg.show()

    def _show_dvd_chrome(show: bool) -> None:
        btn_row.setVisible(show)
        if show:
            lst.hide()
            bg.show()
        else:
            btn_row.hide()
            lst.show()

    def _fill_list(items: List[str], acts: List[Callable[[], None]]) -> None:
        nonlocal actions
        actions = list(acts)
        lst.clear()
        for label in items:
            lst.addItem(QListWidgetItem(label))
        if items:
            lst.setCurrentRow(0)
        _show_dvd_chrome(False)

    def _wire_dvd_buttons(
        *,
        assets: MenuAssets,
        on_play: Callable[[], None],
        on_extras: Optional[Callable[[], None]],
        on_scenes: Optional[Callable[[], None]] = None,
    ) -> None:
        nonlocal play_cb, extras_cb, scenes_cb
        _set_bg(assets)
        play_cb = on_play
        extras_cb = on_extras
        scenes_cb = on_scenes
        play_btn.setEnabled(True)
        if on_extras is not None:
            extras_btn.show()
            extras_btn.setEnabled(True)
        else:
            extras_btn.hide()
        if on_scenes is not None:
            scenes_btn.show()
            scenes_btn.setEnabled(True)
        else:
            scenes_btn.hide()
        _show_dvd_chrome(True)

    def _go_titles() -> None:
        cart: Optional[Cartridge] = state["cart"]
        stack.clear()
        stack.append(("titles",))
        if cart is None:
            stop_menu_audio()
            _set_bg(MenuAssets())
            _show_dvd_chrome(True)
            play_btn.setEnabled(False)
            extras_btn.hide()
            scenes_btn.hide()
            return
        assets = cart.menu
        _set_bg(assets)
        start_menu_audio(assets.music)
        labels: List[str] = []
        callbacks: List[Callable[[], None]] = []
        for i, m in enumerate(cart.movies):
            labels.append(m.title)
            callbacks.append(lambda i=i: _go_movie(i))
        for i, s in enumerate(cart.tv):
            labels.append(s.title)
            callbacks.append(lambda i=i: _go_show(i))
        if len(labels) == 1:
            callbacks[0]()
            return
        _fill_list(labels or ["(empty cart)"], callbacks or [lambda: None])

    def _movie_scenes(movie) -> List[Tuple[str, float]]:
        out: List[Tuple[str, float]] = [
            (s.title, s.start_sec) for s in (movie.scenes or [])
        ]
        if out:
            return out
        return list_media_chapters(movie.path)

    def _go_movie(idx: int) -> None:
        cart: Optional[Cartridge] = state["cart"]
        if cart is None or not (0 <= idx < len(cart.movies)):
            return
        movie = cart.movies[idx]
        stack[:] = [("titles",), ("movie", idx)]
        assets = _pick_menu(movie.menu, cart.menu)
        start_menu_audio(assets.music or cart.menu.music)

        def on_play(p=movie.path) -> None:
            if p.is_file():
                _play_feature(p)

        on_ex = (lambda i=idx: _go_extras(i)) if movie.extras else None
        scenes = _movie_scenes(movie)
        on_sc = (lambda i=idx: _go_scenes(i)) if scenes else None
        _wire_dvd_buttons(
            assets=assets,
            on_play=on_play,
            on_extras=on_ex,
            on_scenes=on_sc,
        )

    def _go_scenes(idx: int) -> None:
        cart: Optional[Cartridge] = state["cart"]
        if cart is None or not (0 <= idx < len(cart.movies)):
            return
        movie = cart.movies[idx]
        stack.append(("scenes", idx))
        assets = _pick_menu(movie.menu, cart.menu)
        _set_bg(assets)
        labels: List[str] = []
        callbacks: List[Callable[[], None]] = []
        for title, start in _movie_scenes(movie):
            labels.append(title)
            callbacks.append(
                lambda p=movie.path, t=start: _play_feature(p, start_sec=t)
                if p.is_file()
                else None
            )
        labels.append("← Back")
        callbacks.append(lambda i=idx: _go_movie(i))
        _fill_list(labels, callbacks)

    def _go_extras(idx: int) -> None:
        cart: Optional[Cartridge] = state["cart"]
        if cart is None or not (0 <= idx < len(cart.movies)):
            return
        movie = cart.movies[idx]
        stack.append(("extras", idx))
        assets = _pick_menu(movie.menu, cart.menu)
        _set_bg(assets)
        labels: List[str] = []
        callbacks: List[Callable[[], None]] = []
        for ex in movie.extras:
            labels.append(ex.title)
            callbacks.append(
                lambda p=ex.path: _play_feature(p) if p.is_file() else None
            )
        labels.append("← Back")
        callbacks.append(lambda i=idx: _go_movie(i))
        _fill_list(labels, callbacks)

    def _go_show(idx: int) -> None:
        cart: Optional[Cartridge] = state["cart"]
        if cart is None or not (0 <= idx < len(cart.tv)):
            return
        show = cart.tv[idx]
        stack[:] = [("titles",), ("show", idx)]
        assets = _pick_menu(show.menu, cart.menu)
        start_menu_audio(assets.music or cart.menu.music)
        first = None
        if show.seasons and show.seasons[0].episodes:
            first = show.seasons[0].episodes[0].path

        def on_play(p=first) -> None:
            if p is not None and p.is_file():
                _play_feature(p)

        _wire_dvd_buttons(
            assets=assets,
            on_play=on_play,
            on_extras=lambda i=idx: _go_show_seasons(i),
            on_scenes=None,
        )

    def _go_show_seasons(idx: int) -> None:
        cart: Optional[Cartridge] = state["cart"]
        if cart is None or not (0 <= idx < len(cart.tv)):
            return
        show = cart.tv[idx]
        stack.append(("seasons", idx))
        labels: List[str] = []
        callbacks: List[Callable[[], None]] = []
        for si, season in enumerate(show.seasons):
            labels.append(season.title)
            callbacks.append(lambda s=idx, se=si: _go_season(s, se))
        labels.append("← Back")
        callbacks.append(lambda i=idx: _go_show(i))
        _fill_list(labels, callbacks)

    def _go_season(show_i: int, season_i: int) -> None:
        cart: Optional[Cartridge] = state["cart"]
        if cart is None or not (0 <= show_i < len(cart.tv)):
            return
        show = cart.tv[show_i]
        if not (0 <= season_i < len(show.seasons)):
            return
        season = show.seasons[season_i]
        stack.append(("season", show_i, season_i))
        labels: List[str] = []
        callbacks: List[Callable[[], None]] = []
        for ep in season.episodes:
            labels.append(ep.title)
            callbacks.append(
                lambda p=ep.path: _play_feature(p) if p.is_file() else None
            )
        labels.append("← Back")
        callbacks.append(lambda s=show_i: _go_show_seasons(s))
        _fill_list(labels, callbacks)

    def do_list_activate(_item=None) -> None:
        row = lst.currentRow()
        if 0 <= row < len(actions):
            actions[row]()

    def on_play_clicked() -> None:
        if play_cb:
            play_cb()

    def on_extras_clicked() -> None:
        if extras_cb:
            extras_cb()

    def on_scenes_clicked() -> None:
        if scenes_cb:
            scenes_cb()

    play_btn.clicked.connect(on_play_clicked)
    extras_btn.clicked.connect(on_extras_clicked)
    scenes_btn.clicked.connect(on_scenes_clicked)
    lst.itemActivated.connect(do_list_activate)

    def rebuild() -> None:
        refresh(force=True)
        cart = current()
        if cart is None or not (
            cart.has_kind("movies") or cart.has_kind("tv")
        ):
            state["cart"] = None
            stop_menu_audio()
            _set_bg(MenuAssets())
            _show_dvd_chrome(True)
            play_btn.setEnabled(False)
            extras_btn.hide()
            scenes_btn.hide()
            return
        state["cart"] = cart
        if len(cart.movies) == 1 and not cart.tv:
            _go_movie(0)
        elif len(cart.tv) == 1 and not cart.movies:
            _go_show(0)
        else:
            _go_titles()

    def on_page_show() -> None:
        rebuild()

        def _refresh_art() -> None:
            try:
                top = stack[-1] if stack else ("titles",)
                cart = state["cart"]
                if cart is None or top[0] not in ("movie", "show"):
                    return
                if top[0] == "movie" and 0 <= top[1] < len(cart.movies):
                    m = cart.movies[top[1]]
                    _set_bg(_pick_menu(m.menu, cart.menu))
                elif top[0] == "show" and 0 <= top[1] < len(cart.tv):
                    s = cart.tv[top[1]]
                    _set_bg(_pick_menu(s.menu, cart.menu))
            except Exception:
                pass

        QTimer.singleShot(50, _refresh_art)

    def on_navigate_away() -> None:
        stop_menu_audio()

    def on_hardware_back() -> bool:
        if len(stack) <= 1:
            stop_menu_audio()
            return False
        kind = stack[-1][0]
        if kind == "extras":
            _go_movie(stack[-1][1])
            return True
        if kind == "scenes":
            _go_movie(stack[-1][1])
            return True
        if kind == "seasons":
            _go_show(stack[-1][1])
            return True
        if kind == "season":
            _go_show_seasons(stack[-1][1])
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

    def digi_activate() -> bool:
        if btn_row.isVisible():
            fw = body.focusWidget()
            if fw is scenes_btn and scenes_btn.isVisible() and scenes_cb:
                on_scenes_clicked()
                return True
            if fw is extras_btn and extras_btn.isVisible() and extras_cb:
                on_extras_clicked()
                return True
            if play_cb:
                on_play_clicked()
                return True
            return True
        do_list_activate()
        return True

    chrome.digi_activate = digi_activate  # type: ignore[attr-defined]
    body.digi_activate = digi_activate  # type: ignore[attr-defined]
    return chrome
