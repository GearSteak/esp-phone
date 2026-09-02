"""Magic: The Gathering — life counter, card search, settings."""

from esp_handset.tcg.mtg.life_ui import make_mtg_life_page, make_mtg_settings_page
from esp_handset.tcg.mtg.cards_ui import make_mtg_cards_page

__all__ = [
    "make_mtg_life_page",
    "make_mtg_settings_page",
    "make_mtg_cards_page",
]
