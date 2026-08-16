"""Hide / restore desktop taskbars so Digivice can own the screen."""
from __future__ import annotations

import os
import subprocess
from typing import List


def _run(cmd: List[str], timeout: float = 2.0) -> None:
    try:
        subprocess.run(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=timeout,
            check=False,
        )
    except Exception:
        pass


def hide_desktop_chrome() -> None:
    """Hide LXDE / PIXEL / labwc panels so they don't peek under Digivice."""
    # Soft hide first
    _run(["lxpanelctl", "hide"])
    # Bookworm Wayland / labwc panel
    for name in (
        "wf-panel-pi",
        "wf-panel",
        "waybar",
        "lxpanel",
        "lxqt-panel",
        "mate-panel",
        "xfce4-panel",
        "polybar",
    ):
        _run(["pkill", "-x", name])
    # pcmanfm desktop icons can also sit on top
    _run(["pcmanfm", "--desktop-off"])
    # Show desktop / minimize everything behind us
    _run(["wmctrl", "-k", "on"])


def show_desktop_chrome() -> None:
    """Best-effort restore when leaving Digivice for Linux desktop."""
    _run(["wmctrl", "-k", "off"])
    _run(["lxpanelctl", "show"])
    # Restart common panels if they were killed
    user = os.environ.get("USER") or os.environ.get("SUDO_USER") or "pi"
    home = os.path.expanduser(f"~{user}") if user else os.path.expanduser("~")
    # Prefer user session restart via dbus-free nohup
    for cmd in (
        ["lxpanel", "--profile", "LXDE-pi"],
        ["lxpanel"],
        ["wf-panel-pi"],
    ):
        try:
            subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
                env=os.environ.copy(),
            )
            break
        except Exception:
            continue
    del home  # reserved for future autostart paths
