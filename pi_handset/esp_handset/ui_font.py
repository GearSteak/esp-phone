"""Application font loading for the Digivice Qt interface."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PyQt5.QtGui import QFont, QFontDatabase

_FONT_PATH = Path(__file__).resolve().parents[1] / "Assets" / "Tengoku.ttf"


def install_app_font(app) -> Optional[str]:
    """Load Tengoku and make it the application and painted UI font."""
    if not _FONT_PATH.is_file():
        return None
    font_id = QFontDatabase.addApplicationFont(str(_FONT_PATH))
    if font_id < 0:
        return None
    families = QFontDatabase.applicationFontFamilies(font_id)
    if not families:
        return None
    family = families[0]
    app.setFont(QFont(family))
    for alias in ("DejaVu Sans", "sans-serif", "monospace"):
        QFont.insertSubstitution(alias, family)
    return family
