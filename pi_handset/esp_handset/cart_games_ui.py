"""USB game-cartridge menu — Apps tile takeover for games-only carts."""

from __future__ import annotations

from pathlib import Path
from typing import Callable, List, Optional

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import (
    QLabel,
    QListWidget,
    QListWidgetItem,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from esp_handset.cartridge import CartGame, Cartridge, current, refresh, takeover_games
from esp_handset.cart_media_ui import start_menu_audio, stop_menu_audio
from esp_handset.emu_ui import SYSTEMS, EmuPlayView
from esp_handset.pages import page_chrome
from esp_handset.rom_shelf import find_cover

DATA = Path.home() / ".esp-handset"


def games_cart_active() -> bool:
    try:
        return takeover_games()
    except Exception:
        return False


def games_home_title() -> Optional[str]:
    if not games_cart_active():
        return None
    cart = current()
    if cart is None:
        return None
    return ((cart.title or "").strip() or "Cart")[:18]


def games_home_logo() -> Optional[Path]:
    if not games_cart_active():
        return None
    cart = current()
    if cart is None:
        return None
    if cart.logo is not None and cart.logo.is_file():
        return cart.logo
    if cart.menu.logo is not None and cart.menu.logo.is_file():
        return cart.menu.logo
    for game in _valid_games(cart):
        cover = find_cover(game.path, SYSTEMS[game.system].folder, DATA)
        if cover is not None:
            return cover
    return None


def _valid_games(cart: Optional[Cartridge]) -> List[CartGame]:
    if cart is None:
        return []
    games: List[CartGame] = []
    for system in SYSTEMS:
        games.extend(cart.games_for_system(system))
    return games


def make_cart_games_page(on_back: Callable[[], None]) -> QWidget:
    """Cart menu; a single valid game starts immediately when Apps is selected."""
    body = QWidget()
    body.setStyleSheet("background:#05080c;")
    root = QVBoxLayout(body)
    root.setContentsMargins(6, 4, 6, 4)
    root.setSpacing(4)

    menu = QWidget()
    menu_lay = QVBoxLayout(menu)
    menu_lay.setContentsMargins(0, 0, 0, 0)
    menu_lay.setSpacing(4)
    bg = QLabel()
    bg.setAlignment(Qt.AlignCenter)
    bg.setMinimumHeight(90)
    bg.setStyleSheet("background:#0a1018;")
    logo = QLabel()
    logo.setAlignment(Qt.AlignCenter)
    logo.setMaximumHeight(72)
    logo.hide()
    lst = QListWidget()
    lst.setMinimumHeight(70)
    menu_lay.addWidget(bg, 1)
    menu_lay.addWidget(logo, 0)
    menu_lay.addWidget(lst, 0)

    stack = QStackedWidget()
    stack.addWidget(menu)
    root.addWidget(stack, 1)
    chrome = page_chrome("Cartridge", body, on_back, scroll=False)

    state = {"cart": None, "games": [], "play_view": None}

    def _set_art(cart: Optional[Cartridge]) -> None:
        assets = cart.menu if cart is not None else None
        path = assets.background if assets is not None else None
        if path is not None and path.is_file():
            pm = QPixmap(str(path))
            if not pm.isNull():
                bg.setPixmap(
                    pm.scaled(
                        max(body.width(), 220),
                        max(body.height() - 80, 100),
                        Qt.KeepAspectRatioByExpanding,
                        Qt.SmoothTransformation,
                    )
                )
                return
        bg.clear()

    def _set_logo(cart: Optional[Cartridge]) -> None:
        path = games_home_logo() if cart is not None else None
        if path is None:
            logo.clear()
            logo.hide()
            return
        pm = QPixmap(str(path))
        if pm.isNull():
            logo.clear()
            logo.hide()
            return
        logo.setPixmap(pm.scaled(190, 68, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        logo.show()

    def show_menu() -> None:
        view = state["play_view"]
        if view is not None:
            view.stop()
        state["play_view"] = None
        chrome.emu_board = None  # type: ignore[attr-defined]
        chrome.gb_board = None  # type: ignore[attr-defined]
        stack.setCurrentWidget(menu)
        lst.setFocus(Qt.OtherFocusReason)

    def launch(game: CartGame) -> None:
        system = SYSTEMS.get(game.system)
        if system is None or not game.path.is_file():
            return
        old = state["play_view"]
        if old is not None:
            old.stop()
        view = EmuPlayView(system, on_quit=show_menu)
        state["play_view"] = view
        chrome.emu_board = view  # type: ignore[attr-defined]
        chrome.gb_board = view  # type: ignore[attr-defined]
        stack.addWidget(view)
        stack.setCurrentWidget(view)
        view.start_rom(game.path)

    def activate_row(_item: Optional[QListWidgetItem] = None) -> None:
        row = lst.currentRow()
        games = state["games"]
        if 0 <= row < len(games):
            launch(games[row])

    def rebuild() -> None:
        refresh(force=True)
        cart = current()
        games = _valid_games(cart)
        state["cart"] = cart
        state["games"] = games
        show_menu()
        _set_art(cart)
        _set_logo(cart)
        lst.clear()
        for game in games:
            system = SYSTEMS[game.system]
            lst.addItem(QListWidgetItem(f"{game.title}  ·  {system.title}"))
        if not games:
            lst.addItem(QListWidgetItem("No valid games on cartridge"))
            return
        if len(games) == 1:
            QTimer.singleShot(0, lambda game=games[0]: launch(game))
        else:
            lst.setCurrentRow(0)
            lst.setFocus(Qt.OtherFocusReason)
            start_menu_audio(cart.menu.music if cart is not None else None)

    def on_hardware_back() -> bool:
        view = state["play_view"]
        if view is not None and view.playing:
            return True
        if stack.currentWidget() is not menu:
            show_menu()
            return True
        on_back()
        return True

    def on_navigate_away() -> None:
        stop_menu_audio()
        view = state["play_view"]
        if view is not None:
            view.stop()
        state["play_view"] = None

    lst.itemActivated.connect(activate_row)
    chrome.on_hardware_back = on_hardware_back  # type: ignore[attr-defined]
    chrome.on_navigate_away = on_navigate_away  # type: ignore[attr-defined]
    chrome.on_page_show = rebuild  # type: ignore[attr-defined]
    chrome.emu_board = None  # type: ignore[attr-defined]
    chrome.gb_board = None  # type: ignore[attr-defined]
    return chrome
