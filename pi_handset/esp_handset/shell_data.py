"""Shared Digivice menu entries (split from shell to avoid cycles)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List


@dataclass
class AppEntry:
    key: str
    title: str
    subtitle: str = ""
    glyph: str = "◆"


# 5 top + 5 bottom (Linux lives under Settings, not on home)
HOME_APPS: List[AppEntry] = [
    AppEntry("calls", "Calls", "Phone · contacts", "☎"),
    AppEntry("sms", "SMS", "Texts · LoRa", "✉"),
    AppEntry("clock", "Clock", "Time & alarms", "⏱"),
    AppEntry("calendar", "Calendar", "Events", "▦"),
    AppEntry("browser", "Browser", "Light web", "⎋"),
    AppEntry("media", "Media", "Cam · notes · GPS", "▶"),
    AppEntry("games", "Games", "GB · built-ins", "♠"),
    AppEntry("tools", "Tools", "Calc · steps", "⚒"),
    AppEntry("settings", "Settings", "Device · Linux", "⚙"),
    AppEntry("email", "Email", "Inbox", "@"),
]

CALLS_APPS = [
    AppEntry("phone", "Phone", "T9 dial pad", "☎"),
    AppEntry("contacts", "Contacts", "Photo · phone · LoRa · email", "☺"),
]

SMS_APPS = [
    AppEntry("messages", "Messages", "Conversations", "✉"),
    AppEntry("lora", "LoRa", "Mesh chats · SOS", "⌁"),
    AppEntry("notifs", "Notifs", "", "⚑"),
]

CLOCK_APPS = [
    AppEntry("clock_face", "Clock", "", "⏱"),
    AppEntry("alarms", "Alarms", "", "⚑"),
]

TOOLS_APPS = [
    AppEntry("wifi_transfer", "Transfer", "Send & get · Wi‑Fi", "⇅"),
    AppEntry("calc", "Calculator", "", "+"),
    AppEntry("ai", "AI", "Ollama · DeepSeek", "✦"),
    AppEntry("convert", "Converter", "", "⇄"),
    AppEntry("weather", "Weather", "", "☁"),
    AppEntry("steps", "Steps", "Tilt SW-520D", "👟"),
    AppEntry("share_gps", "Share GPS", "", "⌖"),
]

SETTINGS_APPS = [
    AppEntry("set_update", "Update", "Pull · install · restart", "↓"),
    AppEntry("set_mouse", "Mouse", "Desktop pointer speed", "⇔"),
    AppEntry("set_debug", "Debug", "Mic · speaker · devices", "⚒"),
    AppEntry("set_appearance", "Look", "Wallpaper", "▣"),
    AppEntry("set_security", "Security", "PIN", "🔒"),
    AppEntry("set_network", "Network", "Wi‑Fi / LTE", "⌁"),
    AppEntry("set_accounts", "Accounts", "SIP", "@"),
    AppEntry("set_sounds", "Sounds", "", "♪"),
    AppEntry("set_power", "Power", "Off · Restart", "⏻"),
    AppEntry("set_about", "About", "", "i"),
    AppEntry("help", "Help", "Joystick map", "?"),
    AppEntry("linux", "Linux", "Full desktop", "▤"),
]

MEDIA_APPS = [
    AppEntry("camera", "Camera", "Pi CSI", "◉"),
    AppEntry("gallery", "Gallery", "", "▣"),
    AppEntry("recorder", "Voice", "", "◉"),
    AppEntry("gps", "GPS", "SIM7600", "⌖"),
    AppEntry("notes", "Notes", "", "✎"),
    AppEntry("todos", "Todos", "", "☑"),
    AppEntry("music", "Music", "", "♪"),
    AppEntry("videos", "Videos", "", "▶"),
    AppEntry("ebooks", "Ebooks", "", "▤"),
    AppEntry("audiobooks", "Audiobooks", "", "♬"),
]

GAMES_APPS = [
    AppEntry("gb", "Game Boy", "GB / GBC ROMs", "♠"),
    AppEntry("snake", "Snake", "", "◆"),
    AppEntry("pong", "Pong", "", "○"),
    AppEntry("tetris", "Tetris", "", "▣"),
    AppEntry("solitaire", "Solitaire", "", "♠"),
    AppEntry("uno", "Uno", "", "U"),
]

COMM_APPS = CALLS_APPS + SMS_APPS
SETUP_APPS = TOOLS_APPS + SETTINGS_APPS  # legacy alias

FOLDER_MAP = {
    "calls": ("folder_calls", "Calls", CALLS_APPS),
    "sms": ("folder_sms", "SMS", SMS_APPS),
    "clock": ("folder_clock", "Clock", CLOCK_APPS),
    "tools": ("folder_tools", "Tools", TOOLS_APPS),
    "settings": ("folder_settings", "Settings", SETTINGS_APPS),
    "media": ("folder_media", "Media", MEDIA_APPS),
    "games": ("folder_games", "Games", GAMES_APPS),
}
