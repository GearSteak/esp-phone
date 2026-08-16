"""Hide / restore desktop taskbars so Digivice can own the screen.

Keep this gentle: hard-killing wf-panel-pi / lxpanel (and X11 bypass windows)
was crashing Digivice on open under Bookworm / labwc. Soft-hide is enough.
Optional: ESP_HANDSET_KILL_PANEL=1 for the aggressive path.
"""
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


def _want_hard_kill() -> bool:
    return os.environ.get("ESP_HANDSET_KILL_PANEL", "").strip().lower() in (
        "1",
        "true",
        "yes",
    )


def hide_desktop_chrome() -> None:
    """Tuck the taskbar so Digivice can paint full-screen."""
    _run(["lxpanelctl", "hide"])
    if not _want_hard_kill():
        return
    # Aggressive path (opt-in only — can destabilize the Pi desktop session)
    for name in (
        "wf-panel-pi",
        "wf-panel",
        "waybar",
        "lxpanel",
        "lxqt-panel",
    ):
        _run(["pkill", "-x", name])
    _run(["pcmanfm", "--desktop-off"])
    _run(["wmctrl", "-k", "on"])


def show_desktop_chrome() -> None:
    """Best-effort restore when leaving Digivice for Linux desktop."""
    _run(["wmctrl", "-k", "off"])
    _run(["lxpanelctl", "show"])
    if not _want_hard_kill():
        return
    # Only restart panels if we may have killed them
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
