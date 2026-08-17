"""Game Boy / GBC — thin wrapper around the shared in-UI emulator."""

from __future__ import annotations

from typing import Callable, Optional

from PyQt5.QtWidgets import QWidget

from esp_handset.emu_ui import SYSTEMS, make_emu_page


def make_gb_page(
    on_back: Callable[[], None],
    *,
    on_receive: Optional[Callable[[], None]] = None,
) -> QWidget:
    return make_emu_page(SYSTEMS["gb"], on_back, on_receive=on_receive)
