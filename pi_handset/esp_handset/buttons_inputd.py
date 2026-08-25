#!/usr/bin/env python3
"""Digivice button pad → UI keys (phone), mouse (desktop), or GB map.

  UP / DOWN / LEFT / RIGHT / CONFIRM / BACK / HOME / SELECT (optional 8th)
  BCM: 5 / 6 / 12 / 13 / 16 / 19 / 20 / 21  (override DIGI_BTN_*)

Mode file (phone | desktop | gb), checked every 0.4s:
  /etc/esp-handset/ui_mode
  ~/.esp-handset/session_mode  (every user home)

Phone  — arrows / Enter / Esc / Home / Tab(Select)
Desktop — d-pad=mouse, Confirm=LMB, Back=RMB, Select=MMB, Home=relaunch
GB      — d-pad=move, Confirm=A(x), Back=B(z), Home=Start, Select=Select
          (Home+Confirm still = Select for 7-button cases)
          Confirm+Back+Home=exit emu

If Digivice (handset_app) is running, mode is always phone — a stale
desktop mode file must not steal the pad into mouse mode.

handset-session writes mode on handset-phone / handset-desktop.
"""

from __future__ import annotations

import glob
import os
import socket
import subprocess
import sys
import threading
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
    "SELECT": 21,  # 8th button — pin 40; leave unwired OK (pulled up)
}

XDOTOOL_KEYS = {
    "UP": "Up",
    "DOWN": "Down",
    "LEFT": "Left",
    "RIGHT": "Right",
    "CONFIRM": "Return",
    "BACK": "Escape",
    "HOME": "Home",
    "SELECT": "Tab",
}

# Game Boy / GBC (RetroArch gambatte + mgba keyboard defaults we ship)
GB_XDOTOOL = {
    "UP": "Up",
    "DOWN": "Down",
    "LEFT": "Left",
    "RIGHT": "Right",
    "A": "x",
    "B": "z",
    "START": "Return",
    "SELECT": "Shift_R",
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
TYPE_SOCK = Path("/run/digivice/type.sock")


def log(msg: str) -> None:
    print(f"[digi-buttons] {msg}", flush=True)


def open_type_sock():
    """CardKB (and friends) type through THIS uinput device — labwc already has it."""
    try:
        TYPE_SOCK.parent.mkdir(parents=True, exist_ok=True)
        try:
            TYPE_SOCK.unlink()
        except FileNotFoundError:
            pass
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        sock.bind(str(TYPE_SOCK))
        os.chmod(TYPE_SOCK, 0o666)
        sock.setblocking(False)
        log(f"type socket {TYPE_SOCK}")
        return sock
    except OSError as e:
        log(f"type socket: {e}")
        return None


def drain_type_sock(sock, device, uinput_mod) -> None:
    if sock is None:
        return
    for _ in range(48):
        try:
            data = sock.recv(80)
        except BlockingIOError:
            return
        except OSError:
            return
        try:
            parts = data.decode("ascii", "replace").split()
            if len(parts) != 2:
                continue
            op, n = parts[0], int(parts[1])
            ev = (1, n)  # EV_KEY
            if op == "S":
                device.emit(uinput_mod.KEY_LEFTSHIFT, 1)
            device.emit(ev, 1)
            time.sleep(0.008)
            device.emit(ev, 0)
            if op == "S":
                device.emit(uinput_mod.KEY_LEFTSHIFT, 0)
        except Exception as e:
            log(f"type sock: {e}")


def pin_map() -> Dict[str, int]:
    """Build GPIO map. DIGI_BTN_SELECT=off|0|none skips the 8th button."""
    out: Dict[str, int] = {}
    for name, default in DEFAULTS.items():
        env = os.environ.get(f"DIGI_BTN_{name}", "").strip()
        if name == "SELECT" and env.lower() in ("off", "0", "none", "disable", "-1"):
            continue
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
    # Digivice UI up → always phone keys (ignore stale desktop/gb mode file)
    if digivice_running():
        return "phone"
    for p in mode_file_candidates():
        try:
            if not p.is_file():
                continue
            m = p.read_text(encoding="utf-8").strip().lower()
            if m in ("phone", "desktop", "gb"):
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

    def key_named(self, xkey: str, down: bool) -> None:
        """Emit an arbitrary xdotool key name (for GB mode)."""
        if not xkey:
            return
        self._run(["keydown" if down else "keyup", xkey])

    def tap_named(self, xkey: str) -> None:
        if not xkey:
            return
        self._run(["key", "--clearmodifiers", xkey])

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


def open_gpio(pins: Dict[str, int]) -> GpioBackend:
    """Open pins with the first backend that can actually *claim* them.

    New Raspberry Pi OS often lets `import RPi.GPIO` succeed, then fails on
    setup (use python3-rpi-lgpio / python3-lgpio instead).
    """
    errors: List[str] = []
    for factory, name in (
        (RPiGpio, "RPi.GPIO"),
        (LgpioBackend, "lgpio"),
    ):
        g: Optional[GpioBackend] = None
        try:
            g = factory()
            g.setup(pins)
            log(f"GPIO backend: {name}")
            return g
        except Exception as e:
            errors.append(f"{name}: {e}")
            log(f"{name} failed ({e})")
            if g is not None:
                try:
                    g.cleanup()
                except Exception:
                    pass
    raise SystemExit(
        "No GPIO backend — install python3-lgpio or python3-rpi-lgpio. "
        + "; ".join(errors)
    )


def is_pressed(level: int) -> bool:
    if ACTIVE_HIGH:
        return level != 0
    return level == 0


def _pgrep_f(pat: str) -> bool:
    try:
        r = subprocess.run(
            ["pgrep", "-f", pat],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        return r.returncode == 0
    except Exception:
        return False


def quit_gb_emulator() -> None:
    """Confirm+Back+Home — stop GB emu; ensure Digivice comes back if launcher died."""
    log("GB exit combo → stop emulator")
    pats = (
        "retroarch",
        "mgba-sdl",
        "mgba-qt",
        "mgba",
        "vbam",
        "sameboy",
    )
    for pat in pats:
        try:
            subprocess.run(
                ["pkill", "-TERM", "-f", pat],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=2,
                check=False,
            )
        except Exception:
            pass

    def _recover() -> None:
        time.sleep(0.7)
        for pat in pats:
            try:
                subprocess.run(
                    ["pkill", "-KILL", "-f", pat],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=2,
                    check=False,
                )
            except Exception:
                pass
        # digivice-gb should exec handset-phone; if it crashed, panel stays black
        time.sleep(2.5)
        if digivice_running():
            return
        if _pgrep_f("digivice-gb"):
            # launcher still cleaning up — give it a bit more
            time.sleep(3.0)
            if digivice_running():
                return
        log("GB exit: Digivice not back — force relaunch + phone mode")
        try:
            write_mode_phone()
        except Exception:
            pass
        try:
            # Free SPI mirror so Digivice can open ST7789
            subprocess.run(
                ["pkill", "-TERM", "-f", "desktop_spi_mirror.py"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=2,
                check=False,
            )
        except Exception:
            pass
        try:
            for lock in (
                "/tmp/digivice-st7789.lock",
                "/run/digivice-st7789.lock",
            ):
                try:
                    os.remove(lock)
                except OSError:
                    pass
        except Exception:
            pass
        try:
            relaunch_digivice()
        except Exception as e:
            log(f"GB force relaunch failed: {e}")

    threading.Thread(target=_recover, daemon=True).start()


def main() -> int:
    try:
        import uinput
    except ImportError:
        log("FATAL: python3-uinput required")
        return 1

    use_mcp = False
    try:
        from esp_handset import mcp23017

        use_mcp = mcp23017.backend_enabled()
    except Exception:
        use_mcp = False

    if use_mcp:
        pins = dict(DEFAULTS)
        gpio = None
        log("input backend: MCP23017 @ I2C 0x20")
    else:
        pins = pin_map()
        gpio = open_gpio(pins)

    phone_map = {
        "UP": uinput.KEY_UP,
        "DOWN": uinput.KEY_DOWN,
        "LEFT": uinput.KEY_LEFT,
        "RIGHT": uinput.KEY_RIGHT,
        "CONFIRM": uinput.KEY_ENTER,
        "BACK": uinput.KEY_ESC,
        "HOME": uinput.KEY_HOME,
        "SELECT": uinput.KEY_TAB,
    }
    gb_map = {
        "UP": uinput.KEY_UP,
        "DOWN": uinput.KEY_DOWN,
        "LEFT": uinput.KEY_LEFT,
        "RIGHT": uinput.KEY_RIGHT,
        "A": uinput.KEY_X,
        "B": uinput.KEY_Z,
        "START": uinput.KEY_ENTER,
        "SELECT": uinput.KEY_RIGHTSHIFT,
    }
    extra = [getattr(uinput, f"KEY_{c}") for c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ"]
    extra += [getattr(uinput, f"KEY_{d}") for d in "0123456789"]
    extra += [
        uinput.KEY_LEFTSHIFT,
        uinput.KEY_SPACE,
        uinput.KEY_BACKSPACE,
        uinput.KEY_DOT,
        uinput.KEY_COMMA,
        uinput.KEY_SLASH,
        uinput.KEY_SEMICOLON,
        uinput.KEY_APOSTROPHE,
        uinput.KEY_MINUS,
        uinput.KEY_EQUAL,
        uinput.KEY_LEFTBRACE,
        uinput.KEY_RIGHTBRACE,
        uinput.KEY_BACKSLASH,
    ]
    events = list(
        dict.fromkeys(
            list(phone_map.values())
            + list(gb_map.values())
            + extra
            + [
                uinput.BTN_LEFT,
                uinput.BTN_RIGHT,
                uinput.BTN_MIDDLE,
                uinput.REL_X,
                uinput.REL_Y,
            ]
        )
    )
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

    type_sock = open_type_sock()
    xinj = XInject()
    mode = read_mode()
    mouse_step = read_mouse_step()
    log(
        f"ready mode={mode}  mouse_step={mouse_step}  "
        + (
            "backend=MCP23017"
            if use_mcp
            else " ".join(f"{n}=BCM{p}" for n, p in pins.items())
        )
    )
    log(
        "  phone: keys · desktop: mouse · gb: A/B/Start/Select · "
        "exit GB = Confirm+Back+Home"
    )

    if use_mcp:
        from esp_handset import mcp23017

        phone0 = mcp23017.read_phone_buttons()
        levels = {n: (0 if phone0.get(n, False) else 1) for n in pins}
    else:
        levels = {n: gpio.read(p) for n, p in pins.items()}
    prev = {n: levels[n] for n in pins}
    raw = {n: levels[n] for n in pins}
    stable_since = {n: time.monotonic() for n in pins}
    held = {n: is_pressed(levels[n]) for n in pins}
    last_mode_check = 0.0
    last_mode = mode
    last_step = mouse_step
    gb_exit_since = [None]
    gb_a = [False]
    gb_b = [False]
    gb_start = [False]
    gb_select = [False]
    gb_exit_armed = [True]

    def gb_emit(logical: str, down: bool) -> None:
        code = gb_map.get(logical)
        if code is not None:
            try:
                device.emit(code, 1 if down else 0)
            except Exception as e:
                log(f"gb uinput {logical}: {e}")
        xinj.key_named(GB_XDOTOOL.get(logical, ""), down)

    def gb_release_all() -> None:
        for logical, flag in (
            ("A", gb_a),
            ("B", gb_b),
            ("START", gb_start),
            ("SELECT", gb_select),
        ):
            if flag[0]:
                gb_emit(logical, False)
                flag[0] = False

    try:
        while True:
            drain_type_sock(type_sock, device, uinput)
            now = time.monotonic()
            if now - last_mode_check > 0.4:
                mode = read_mode()
                mouse_step = read_mouse_step()
                last_mode_check = now
                if mode != last_mode:
                    log(f"mode → {mode}")
                    if last_mode == "gb" and mode != "gb":
                        gb_release_all()
                        gb_exit_since[0] = None
                        gb_exit_armed[0] = True
                    last_mode = mode
                if mouse_step != last_step:
                    log(f"mouse_step → {mouse_step}")
                    last_step = mouse_step

            for name, pin in pins.items():
                try:
                    if use_mcp:
                        from esp_handset import mcp23017

                        phone_btns = mcp23017.read_phone_buttons()
                        down_now = phone_btns.get(name, False)
                        level = 0 if down_now else 1
                    else:
                        level = gpio.read(pin)
                except Exception as e:
                    log(f"read {name}: {e}")
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
                        elif name == "SELECT":
                            device.emit(uinput.BTN_MIDDLE, 1 if down else 0)
                            xinj.click(2, down)
                        elif name == "HOME":
                            if down:
                                try:
                                    relaunch_digivice()
                                except Exception as e:
                                    log(f"HOME relaunch crash-guard: {e}")
                        if down and name in ("UP", "DOWN", "LEFT", "RIGHT"):
                            log(f"DESKTOP hold {name}")
                        elif down and name != "HOME":
                            log(f"DESKTOP {name} down")
                    except Exception as e:
                        log(f"desktop emit {name}: {e}")
                elif mode == "gb":
                    try:
                        if name in ("UP", "DOWN", "LEFT", "RIGHT"):
                            gb_emit(name, down)
                        elif name == "SELECT":
                            # Dedicated Select button (8th key)
                            if down:
                                if not gb_select[0]:
                                    gb_emit("SELECT", True)
                                    gb_select[0] = True
                                    log("GB SELECT")
                            else:
                                if gb_select[0]:
                                    gb_emit("SELECT", False)
                                    gb_select[0] = False
                        elif name == "BACK":
                            if down:
                                if not gb_b[0]:
                                    gb_emit("B", True)
                                    gb_b[0] = True
                            else:
                                if gb_b[0]:
                                    gb_emit("B", False)
                                    gb_b[0] = False
                        elif name == "HOME":
                            if down:
                                if not gb_start[0]:
                                    gb_emit("START", True)
                                    gb_start[0] = True
                            else:
                                if gb_select[0] and not held.get("SELECT"):
                                    # combo Select from Home+Confirm path only
                                    gb_emit("SELECT", False)
                                    gb_select[0] = False
                                if gb_start[0]:
                                    gb_emit("START", False)
                                    gb_start[0] = False
                        elif name == "CONFIRM":
                            if down:
                                if held.get("HOME"):
                                    if gb_start[0]:
                                        gb_emit("START", False)
                                        gb_start[0] = False
                                    if not gb_select[0]:
                                        gb_emit("SELECT", True)
                                        gb_select[0] = True
                                        log("GB SELECT (Home+Confirm)")
                                else:
                                    if not gb_a[0]:
                                        gb_emit("A", True)
                                        gb_a[0] = True
                            else:
                                if gb_a[0]:
                                    gb_emit("A", False)
                                    gb_a[0] = False
                                if gb_select[0] and not held.get("SELECT"):
                                    gb_emit("SELECT", False)
                                    gb_select[0] = False
                                    if held.get("HOME") and not gb_start[0]:
                                        gb_emit("START", True)
                                        gb_start[0] = True
                        if down:
                            log(f"GB {name}")
                    except Exception as e:
                        log(f"gb emit {name}: {e}")
                else:
                    try:
                        if name in phone_map:
                            device.emit(phone_map[name], 1 if down else 0)
                    except Exception as e:
                        log(f"uinput {name}: {e}")
                    if name in XDOTOOL_KEYS:
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

            if mode == "gb":
                if held.get("CONFIRM") and held.get("BACK") and held.get("HOME"):
                    if gb_exit_since[0] is None:
                        gb_exit_since[0] = now
                    elif gb_exit_armed[0] and now - gb_exit_since[0] >= 0.45:
                        gb_release_all()
                        quit_gb_emulator()
                        gb_exit_armed[0] = False
                else:
                    gb_exit_since[0] = None
                    gb_exit_armed[0] = True

            time.sleep(SCAN_S)
    except KeyboardInterrupt:
        pass
    finally:
        try:
            gb_release_all()
        except Exception:
            pass
        if gpio is not None:
            gpio.cleanup()
        try:
            device.destroy()
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
