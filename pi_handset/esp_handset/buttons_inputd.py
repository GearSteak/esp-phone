#!/usr/bin/env python3
"""Digivice 7-button pad → UI keys (phone) or mouse (Linux desktop).

  UP / DOWN / LEFT / RIGHT / CONFIRM / BACK / HOME
  BCM: 5 / 6 / 12 / 13 / 16 / 19 / 20  (override DIGI_BTN_*)

Mode file (phone | desktop), checked every 0.4s:
  /etc/esp-handset/ui_mode
  ~/.esp-handset/session_mode  (every user home)

Phone  — arrows / Enter / Esc / Home  (uinput + xdotool keys)
Desktop — d-pad=mouse, Confirm=LMB, Back=RMB, Home=relaunch Digivice

If Digivice (handset_app) is running, mode is always phone — a stale
desktop mode file must not steal the pad into mouse mode.

handset-session writes mode on handset-phone / handset-desktop.
"""

from __future__ import annotations

import glob
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional

DEFAULTS = {
    "UP": 5,
    "DOWN": 6,
    "LEFT": 12,
    "RIGHT": 13,
    "CONFIRM": 16,
    "BACK": 19,
    "HOME": 20,
}

XDOTOOL_KEYS = {
    "UP": "Up",
    "DOWN": "Down",
    "LEFT": "Left",
    "RIGHT": "Right",
    "CONFIRM": "Return",
    "BACK": "Escape",
    "HOME": "Home",
}

DEBOUNCE_S = float(os.environ.get("DIGI_BTN_DEBOUNCE", "0.025"))
SCAN_S = float(os.environ.get("DIGI_BTN_SCAN", "0.012"))
# Default slightly slower than old 12 — Settings → Mouse can change live
_DEFAULT_MOUSE_STEP = int(os.environ.get("DIGI_BTN_MOUSE_STEP", "10"))
ACTIVE_HIGH = os.environ.get("DIGI_BTN_ACTIVE_HIGH", "0").strip() in (
    "1",
    "true",
    "yes",
)
MODE_PATHS = [
    Path("/etc/esp-handset/ui_mode"),
]
MOUSE_STEP_PATHS = [
    Path("/etc/esp-handset/mouse_step"),
]


def log(msg: str) -> None:
    print(f"[digi-buttons] {msg}", flush=True)


def pin_map() -> Dict[str, int]:
    out: Dict[str, int] = {}
    for name, default in DEFAULTS.items():
        env = os.environ.get(f"DIGI_BTN_{name}", "").strip()
        out[name] = int(env) if env else default
    return out


def mode_file_candidates() -> List[Path]:
    paths = list(MODE_PATHS)
    for home in glob.glob("/home/*"):
        paths.append(Path(home) / ".esp-handset" / "session_mode")
    # root fallthrough
    paths.append(Path("/root/.esp-handset/session_mode"))
    env_home = os.environ.get("HOME")
    if env_home:
        paths.append(Path(env_home) / ".esp-handset" / "session_mode")
    return paths


def mouse_step_candidates() -> List[Path]:
    paths: List[Path] = []
    for home in glob.glob("/home/*"):
        paths.append(Path(home) / ".esp-handset" / "mouse_step")
    paths.append(Path("/root/.esp-handset/mouse_step"))
    env_home = os.environ.get("HOME")
    if env_home:
        paths.append(Path(env_home) / ".esp-handset" / "mouse_step")
    paths.extend(MOUSE_STEP_PATHS)
    return paths


def read_mouse_step() -> int:
    """Pixels per scan tick while a d-pad direction is held (desktop mode)."""
    best: Optional[tuple] = None  # (mtime, value)
    for p in mouse_step_candidates():
        try:
            if not p.is_file():
                continue
            raw = p.read_text(encoding="utf-8").strip().split()[0]
            v = int(raw)
            if not (1 <= v <= 64):
                continue
            mtime = p.stat().st_mtime
            if best is None or mtime >= best[0]:
                best = (mtime, v)
        except (OSError, ValueError, IndexError):
            continue
    if best is not None:
        return best[1]
    return _DEFAULT_MOUSE_STEP


def digivice_running() -> bool:
    try:
        r = subprocess.run(
            ["pgrep", "-f", "handset_app.py"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        return r.returncode == 0
    except Exception:
        return False


def read_mode() -> str:
    # Digivice UI up → always phone keys (ignore stale desktop mode file)
    if digivice_running():
        return "phone"
    for p in mode_file_candidates():
        try:
            if not p.is_file():
                continue
            m = p.read_text(encoding="utf-8").strip().lower()
            if m in ("phone", "desktop"):
                return m
        except OSError:
            continue
    return "desktop"


_LAST_RELAUNCH = 0.0


def resolve_gui_user() -> tuple:
    """(username, home) for the desktop user — Digivice must not run as root."""
    env_u = (os.environ.get("DIGI_GUI_USER") or "").strip()
    candidates: List[str] = []
    if env_u and env_u != "root":
        candidates.append(env_u)
    # Prefer active graphical session (loginctl)
    try:
        r = subprocess.run(
            ["loginctl", "list-sessions", "--no-legend"],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
        for line in (r.stdout or "").splitlines():
            parts = line.split()
            if not parts:
                continue
            sid = parts[0]
            try:
                info = subprocess.run(
                    ["loginctl", "show-session", sid, "-p", "User", "-p", "Name", "-p", "Type"],
                    capture_output=True,
                    text=True,
                    timeout=2,
                    check=False,
                )
            except Exception:
                continue
            uid = name = stype = ""
            for row in (info.stdout or "").splitlines():
                if row.startswith("User="):
                    uid = row.split("=", 1)[-1].strip()
                elif row.startswith("Name="):
                    name = row.split("=", 1)[-1].strip()
                elif row.startswith("Type="):
                    stype = row.split("=", 1)[-1].strip()
            if uid in ("", "0"):
                continue
            if not name:
                try:
                    import pwd

                    name = pwd.getpwuid(int(uid)).pw_name
                except Exception:
                    continue
            if name and name != "root":
                if stype in ("x11", "wayland", "mir", "tty", ""):
                    candidates.insert(0, name)
                else:
                    candidates.append(name)
    except Exception:
        pass
    for path in sorted(glob.glob("/home/*/.Xauthority")):
        parts = path.split("/")
        if len(parts) >= 3 and parts[2] not in ("", "root"):
            candidates.append(parts[2])
    for u in ("pi", "isaac"):
        candidates.append(u)
    seen = set()
    for u in candidates:
        if u in seen:
            continue
        seen.add(u)
        try:
            import pwd

            pw = pwd.getpwnam(u)
            return u, pw.pw_dir
        except Exception:
            home = f"/home/{u}"
            if os.path.isdir(home):
                return u, home
    return "pi", "/home/pi"


def write_mode_phone() -> None:
    """Prefer Digivice so autostart / buttons stay in phone mode."""
    payload = "phone\n"
    user, home = resolve_gui_user()
    targets = [
        Path(home) / ".esp-handset" / "session_mode",
        Path("/etc/esp-handset/ui_mode"),
    ]
    for p in targets:
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(payload, encoding="utf-8")
            if str(p).startswith("/home/"):
                try:
                    import pwd

                    pw = pwd.getpwnam(user)
                    os.chown(p.parent, pw.pw_uid, pw.pw_gid)
                    os.chown(p, pw.pw_uid, pw.pw_gid)
                except Exception:
                    pass
        except OSError:
            continue


def load_uinput_mod() -> None:
    try:
        subprocess.run(
            ["modprobe", "uinput"],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        pass


def _home_relaunch_bin() -> Optional[str]:
    for p in (
        "/usr/local/bin/digivice-home-relaunch",
        "/opt/esp-handset/session/home-relaunch.sh",
        str(Path(__file__).resolve().parent.parent / "session" / "home-relaunch.sh"),
    ):
        if os.path.isfile(p):
            return p
    return None


def relaunch_digivice() -> None:
    """Home on Linux desktop → run the same command you'd type in a terminal.

    Just:  handset-phone   (as the desktop user, backgrounded).
    No systemd path units, no SPI teardown scripts — those kept crashing the Pi.
    """
    global _LAST_RELAUNCH
    if digivice_running():
        log("HOME ignored — Digivice already running")
        return
    now = time.monotonic()
    if now - _LAST_RELAUNCH < 5.0:
        log("HOME ignored — debounce")
        return
    _LAST_RELAUNCH = now

    write_mode_phone()
    user, home = resolve_gui_user()
    disp = find_display()
    auth = os.path.join(home, ".Xauthority")
    if not os.path.isfile(auth):
        auth = find_xauthority() or auth

    log_dir = os.path.join(home, ".esp-handset")
    try:
        os.makedirs(log_dir, exist_ok=True)
    except OSError:
        log_dir = "/tmp"
    log_path = os.path.join(log_dir, "home-relaunch.log")

    # Exact equivalent of opening a terminal and running:  handset-phone &
    # Use nohup + background so the GPIO daemon never waits on Digivice.
    phone = "/usr/local/bin/handset-phone"
    if not os.path.isfile(phone):
        phone = "handset-phone"
    inner = (
        f'echo "=== HOME $(date -Iseconds) ===" >>"{log_path}"; '
        f'export DISPLAY="{disp}" XAUTHORITY="{auth}" HOME="{home}" '
        f'USER="{user}" LOGNAME="{user}" ESP_HANDSET_SKIP_LAYOUT=1; '
        f'nohup {phone} >>"{log_path}" 2>&1 </dev/null &'
    )
    cmd = [
        "sudo",
        "-u",
        user,
        "-H",
        "bash",
        "-c",
        inner,
    ]
    try:
        subprocess.Popen(
            cmd,
            start_new_session=True,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        log(f"HOME → sudo -u {user} handset-phone &  DISPLAY={disp}")
    except Exception as e:
        log(f"HOME handset-phone failed: {e}")


def find_xauthority() -> Optional[str]:
    for cand in (
        os.environ.get("XAUTHORITY"),
        "/home/pi/.Xauthority",
        "/home/isaac/.Xauthority",
    ):
        if cand and os.path.isfile(cand):
            return cand
    for path in glob.glob("/home/*/.Xauthority"):
        if os.path.isfile(path):
            return path
    for path in glob.glob("/run/user/*/Xauthority"):
        if os.path.isfile(path):
            return path
    return None


def find_display() -> str:
    return os.environ.get("DISPLAY") or ":0"


def _which(name: str) -> Optional[str]:
    for d in os.environ.get("PATH", "/usr/bin:/bin").split(":"):
        p = os.path.join(d, name)
        if os.path.isfile(p) and os.access(p, os.X_OK):
            return p
    return None


class XInject:
    def __init__(self) -> None:
        self.display = find_display()
        self.auth = find_xauthority()
        self.xdotool = _which("xdotool")
        self.ok = bool(self.xdotool)
        if self.ok:
            log(
                f"X inject ON display={self.display} "
                f"XAUTHORITY={self.auth or '(none)'}"
            )
        else:
            log("X inject OFF — sudo apt install xdotool")

    def _env(self) -> dict:
        env = os.environ.copy()
        env["DISPLAY"] = self.display
        if self.auth:
            env["XAUTHORITY"] = self.auth
        return env

    def _run(self, args: List[str]) -> None:
        if not self.ok:
            return
        try:
            subprocess.run(
                [self.xdotool, *args],
                env=self._env(),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=0.5,
                check=False,
            )
        except Exception as e:
            log(f"xdotool {args}: {e}")

    def key(self, name: str, down: bool) -> None:
        k = XDOTOOL_KEYS.get(name)
        if not k:
            return
        self._run(["keydown" if down else "keyup", k])

    def click(self, button: int, down: bool) -> None:
        # 1=left 2=middle 3=right
        self._run(["mousedown" if down else "mouseup", str(button)])

    def move(self, dx: int, dy: int) -> None:
        if not dx and not dy:
            return
        # mousemove_relative -- dx dy
        self._run(["mousemove_relative", "--", str(dx), str(dy)])

    def super_key(self, down: bool) -> None:
        self._run(["keydown" if down else "keyup", "Super_L"])


class GpioBackend:
    def setup(self, pins: Dict[str, int]) -> None:
        raise NotImplementedError

    def read(self, pin: int) -> int:
        raise NotImplementedError

    def cleanup(self) -> None:
        pass


class RPiGpio(GpioBackend):
    def __init__(self) -> None:
        import RPi.GPIO as GPIO  # type: ignore

        self.GPIO = GPIO

    def setup(self, pins: Dict[str, int]) -> None:
        self.GPIO.setmode(self.GPIO.BCM)
        self.GPIO.setwarnings(False)
        for pin in pins.values():
            self.GPIO.setup(pin, self.GPIO.IN, pull_up_down=self.GPIO.PUD_UP)

    def read(self, pin: int) -> int:
        return int(self.GPIO.input(pin))

    def cleanup(self) -> None:
        try:
            self.GPIO.cleanup()
        except Exception:
            pass


class LgpioBackend(GpioBackend):
    def __init__(self) -> None:
        import lgpio  # type: ignore

        self.lgpio = lgpio
        self.h = lgpio.gpiochip_open(0)

    def setup(self, pins: Dict[str, int]) -> None:
        for pin in pins.values():
            self.lgpio.gpio_claim_input(self.h, pin, self.lgpio.SET_PULL_UP)

    def read(self, pin: int) -> int:
        return int(self.lgpio.gpio_read(self.h, pin))

    def cleanup(self) -> None:
        try:
            self.lgpio.gpiochip_close(self.h)
        except Exception:
            pass


def open_gpio() -> GpioBackend:
    try:
        g = RPiGpio()
        log("GPIO backend: RPi.GPIO")
        return g
    except Exception as e:
        log(f"RPi.GPIO unavailable ({e})")
    try:
        g = LgpioBackend()
        log("GPIO backend: lgpio")
        return g
    except Exception as e:
        raise SystemExit(
            f"No GPIO backend ({e}) — install python3-rpi.gpio or python3-lgpio"
        ) from e


def is_pressed(level: int) -> bool:
    if ACTIVE_HIGH:
        return level != 0
    return level == 0


def main() -> int:
    try:
        import uinput
    except ImportError:
        log("FATAL: python3-uinput required")
        return 1

    pins = pin_map()
    gpio = open_gpio()
    gpio.setup(pins)

    phone_map = {
        "UP": uinput.KEY_UP,
        "DOWN": uinput.KEY_DOWN,
        "LEFT": uinput.KEY_LEFT,
        "RIGHT": uinput.KEY_RIGHT,
        "CONFIRM": uinput.KEY_ENTER,
        "BACK": uinput.KEY_ESC,
        "HOME": uinput.KEY_HOME,
    }
    events = list(phone_map.values()) + [
        uinput.BTN_LEFT,
        uinput.BTN_RIGHT,
        uinput.BTN_MIDDLE,
        uinput.REL_X,
        uinput.REL_Y,
    ]
    load_uinput_mod()
    try:
        device = uinput.Device(
            events,
            name="Digivice-Buttons",
            bustype=0x03,
            vendor=0x1D6B,
            product=0x0104,
            version=1,
        )
    except TypeError:
        device = uinput.Device(events, name="Digivice-Buttons")

    xinj = XInject()
    mode = read_mode()
    mouse_step = read_mouse_step()
    log(
        f"ready mode={mode}  mouse_step={mouse_step}  "
        + " ".join(f"{n}=BCM{p}" for n, p in pins.items())
    )
    log(
        "  phone: keys · desktop: d-pad=mouse Confirm=LMB Back=RMB Home=Digivice"
    )

    levels = {n: gpio.read(p) for n, p in pins.items()}
    prev = {n: levels[n] for n in pins}
    raw = {n: levels[n] for n in pins}
    stable_since = {n: time.monotonic() for n in pins}
    held = {n: is_pressed(levels[n]) for n in pins}
    last_mode_check = 0.0
    last_mode = mode
    last_step = mouse_step

    try:
        while True:
            now = time.monotonic()
            if now - last_mode_check > 0.4:
                mode = read_mode()
                mouse_step = read_mouse_step()
                last_mode_check = now
                if mode != last_mode:
                    log(f"mode → {mode}")
                    last_mode = mode
                if mouse_step != last_step:
                    log(f"mouse_step → {mouse_step}")
                    last_step = mouse_step

            for name, pin in pins.items():
                try:
                    level = gpio.read(pin)
                except Exception as e:
                    log(f"read BCM{pin}: {e}")
                    continue
                if level != raw[name]:
                    raw[name] = level
                    stable_since[name] = now
                    continue
                if now - stable_since[name] < DEBOUNCE_S:
                    continue
                if level == prev[name]:
                    continue
                prev[name] = level
                down = is_pressed(level)
                held[name] = down

                if mode == "desktop":
                    try:
                        if name == "CONFIRM":
                            device.emit(uinput.BTN_LEFT, 1 if down else 0)
                            xinj.click(1, down)
                        elif name == "BACK":
                            device.emit(uinput.BTN_RIGHT, 1 if down else 0)
                            xinj.click(3, down)
                        elif name == "HOME":
                            # Never Super/start-menu — Home always returns to Digivice
                            if down:
                                try:
                                    relaunch_digivice()
                                except Exception as e:
                                    log(f"HOME relaunch crash-guard: {e}")
                        # d-pad: continuous motion while held (below)
                        if down and name in ("UP", "DOWN", "LEFT", "RIGHT"):
                            log(f"DESKTOP hold {name}")
                        elif down and name != "HOME":
                            log(f"DESKTOP {name} down")
                    except Exception as e:
                        log(f"desktop emit {name}: {e}")
                else:
                    try:
                        device.emit(phone_map[name], 1 if down else 0)
                    except Exception as e:
                        log(f"uinput {name}: {e}")
                    xinj.key(name, down)
                    if down:
                        log(f"PHONE {name}")

            if mode == "desktop":
                dx = dy = 0
                if held.get("LEFT"):
                    dx -= mouse_step
                if held.get("RIGHT"):
                    dx += mouse_step
                if held.get("UP"):
                    dy -= mouse_step
                if held.get("DOWN"):
                    dy += mouse_step
                if dx or dy:
                    try:
                        device.emit(uinput.REL_X, dx, syn=False)
                        device.emit(uinput.REL_Y, dy)
                    except Exception as e:
                        log(f"rel: {e}")
                    xinj.move(dx, dy)

            time.sleep(SCAN_S)
    except KeyboardInterrupt:
        pass
    finally:
        gpio.cleanup()
        try:
            device.destroy()
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
