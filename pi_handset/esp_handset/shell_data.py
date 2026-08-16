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
    AppEntry("time", "Time", "Alarms · calendar", "⏱"),
    AppEntry("camera", "Camera", "Snap · preview", "◉"),
    AppEntry("browser", "Browser", "Open web", "⎋"),
    AppEntry("media", "Media", "Gallery · notes · GPS", "▶"),
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
]

# Time folder (home → Time): alarms/timer hub + calendar
CLOCK_APPS = [
    AppEntry("clock", "Alarms", "Wake · reminders", "⚑"),
    AppEntry("timer", "Timer", "Kitchen · chores", "⌛"),
    AppEntry("calendar", "Calendar", "Events", "▦"),
]
TIME_APPS = CLOCK_APPS

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
    AppEntry("set_debug", "Debug", "Sound · alerts · tests", "⚒"),
    AppEntry("set_appearance", "Look", "Wallpaper", "▣"),
    AppEntry("set_orientation", "Screen", "Rotation · flip", "↻"),
    AppEntry("set_security", "Security", "PIN", "🔒"),
    AppEntry("set_network", "Network", "Wi‑Fi / LTE", "⌁"),
    AppEntry("set_accounts", "Accounts", "SIP", "@"),
    AppEntry("set_power", "Power", "Off · Restart", "⏻"),
    AppEntry("set_about", "About", "", "i"),
    AppEntry("help", "Help", "Joystick map", "?"),
    AppEntry("linux", "Linux", "Full desktop", "▤"),
]

MEDIA_APPS = [
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

# Settings → Debug hub
DEBUG_APPS = [
    AppEntry("dbg_sound", "Sound", "Beep · mic · USB · profile", "♪"),
    AppEntry("dbg_notifs", "Alerts", "Toasts · incoming call", "⚑"),
]

COMM_APPS = CALLS_APPS + SMS_APPS
SETUP_APPS = TOOLS_APPS + SETTINGS_APPS  # legacy alias

FOLDER_MAP = {
    "calls": ("folder_calls", "Calls", CALLS_APPS),
    "sms": ("folder_sms", "SMS", SMS_APPS),
    "time": ("folder_time", "Time", TIME_APPS),
    "tools": ("folder_tools", "Tools", TOOLS_APPS),
    "settings": ("folder_settings", "Settings", SETTINGS_APPS),
    "media": ("folder_media", "Media", MEDIA_APPS),
    "games": ("folder_games", "Games", GAMES_APPS),
    "set_debug": ("set_debug", "Debug", DEBUG_APPS),
}
