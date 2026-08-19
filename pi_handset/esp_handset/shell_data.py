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


# 5 top + 4 bottom — Games/Tools live under Apps
HOME_APPS: List[AppEntry] = [
    AppEntry("calls", "Calls", "Phone · contacts", "☎"),
    AppEntry("sms", "SMS", "Texts · LoRa", "✉"),
    AppEntry("time", "Time", "Alarms · calendar", "⏱"),
    AppEntry("camera", "Camera", "Snap · preview", "◉"),
    AppEntry("browser", "Browser", "Open web", "⎋"),
    AppEntry("media", "Media", "Gallery · notes · GPS", "▶"),
    AppEntry("email", "Email", "Gmail · Inbox", "@"),
    AppEntry("apps", "Apps", "Games · tools · Shadowdark", "◆"),
    AppEntry("settings", "Settings", "Device · Linux", "⚙"),
]

CALLS_APPS = [
    AppEntry("phone", "Phone", "T9 dial pad", "☎"),
    AppEntry("contacts", "Contacts", "Photo · phone · LoRa · email", "☺"),
    AppEntry("call_log", "Recents", "Call history", "◷"),
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
    AppEntry("weather", "Weather", "GPS · Wi‑Fi locate", "☁"),
    AppEntry("steps", "Steps", "Pi tilt · pin 11", "👟"),
    AppEntry("share_gps", "Share GPS", "", "⌖"),
]

SETTINGS_APPS = [
    AppEntry("set_system", "System", "Update · Power · Linux", "⏻"),
    AppEntry("set_display", "Display", "Look · Screen · Mouse", "▣"),
    AppEntry("set_network", "Network", "Wi-Fi / LTE", "⌁"),
    AppEntry("set_accounts", "Accounts", "SIP · Email · AI", "@"),
    AppEntry("set_security", "Security", "PIN", "🔒"),
    AppEntry("set_debug", "Debug", "Sound · alerts · tests", "⚒"),
    AppEntry("help", "Help", "Joystick map", "?"),
]

# Settings → System / Display hubs
SYSTEM_APPS = [
    AppEntry("set_update", "Update", "Pull · install · restart", "↓"),
    AppEntry("set_power", "Power", "Off · Restart", "⏻"),
    AppEntry("set_about", "About", "", "i"),
    AppEntry("linux", "Linux", "Full desktop", "▤"),
]

DISPLAY_APPS = [
    AppEntry("set_appearance", "Look", "Wallpaper", "▣"),
    AppEntry("set_orientation", "Screen", "Rotation · flip", "↻"),
    AppEntry("set_mouse", "Mouse", "Desktop pointer speed", "⇔"),
]

# Settings → Accounts hub
ACCOUNTS_APPS = [
    AppEntry("acct_sip", "SIP", "VoIP register", "☎"),
    AppEntry("acct_email", "Email", "Gmail IMAP/SMTP", "@"),
    AppEntry("acct_ai", "AI", "Ollama host", "✦"),
]

MEDIA_APPS = [
    AppEntry("gallery", "Gallery", "Photos", "▣"),
    AppEntry("recorder", "Voice", "Quick clips", "◉"),
    AppEntry("gps", "GPS", "Location", "⌖"),
    AppEntry("notes", "Notes", "Jot · save", "✎"),
    AppEntry("todos", "Todos", "Checklist", "☑"),
    AppEntry("music", "Music", "Tracks", "♪"),
    AppEntry("videos", "Videos", "Clips", "▶"),
    AppEntry("ebooks", "Ebooks", "Read", "▤"),
    AppEntry("audiobooks", "Audiobooks", "Listen", "♬"),
]

GAMES_APPS = [
    AppEntry("gb", "Game Boy", "GB / GBC ROMs", "♠"),
    AppEntry("nes", "NES", "Famicom ROMs", "◆"),
    # Key must not be "sms" — that is the home Messages folder.
    AppEntry("smsgg", "SMS / GG", "Master System · Game Gear", "◎"),
    AppEntry("snake", "Snake", "Arcade · high score", "◆"),
    AppEntry("pong", "Pong", "Arcade · vs AI", "○"),
    AppEntry("tetris", "Tetris", "Arcade · stack", "▣"),
    AppEntry("solitaire", "Solitaire", "Klondike cards", "♠"),
    AppEntry("uno", "Uno", "Match color · number", "U"),
]

APPS_APPS = [
    AppEntry("games", "Games", "Emu · arcade · cards", "♠"),
    AppEntry("tools", "Tools", "Calc · steps · AI", "⚒"),
    AppEntry("shadowdark", "Shadowdark", "Dice · torch timer", "⚔"),
]

EMU_PAGE_KEYS = ("gb", "nes", "smsgg")

# Settings → Debug hub
DEBUG_APPS = [
    AppEntry("dbg_sound", "Sound", "Beep · mic · USB · profile", "♪"),
    AppEntry("dbg_notifs", "Alerts", "Toasts · incoming call", "⚑"),
]

COMM_APPS = CALLS_APPS + SMS_APPS
SETUP_APPS = TOOLS_APPS + SETTINGS_APPS  # legacy alias

FOLDER_MAP = {
    "apps": ("folder_apps", "Apps", APPS_APPS),
    "calls": ("folder_calls", "Calls", CALLS_APPS),
    "sms": ("folder_sms", "SMS", SMS_APPS),
    "time": ("folder_time", "Time", TIME_APPS),
    "tools": ("folder_tools", "Tools", TOOLS_APPS),
    "settings": ("folder_settings", "Settings", SETTINGS_APPS),
    "media": ("folder_media", "Media", MEDIA_APPS),
    "games": ("folder_games", "Games", GAMES_APPS),
    "set_system": ("set_system", "System", SYSTEM_APPS),
    "set_display": ("set_display", "Display", DISPLAY_APPS),
    "set_accounts": ("set_accounts", "Accounts", ACCOUNTS_APPS),
    "set_debug": ("set_debug", "Debug", DEBUG_APPS),
}
