"""In-UI console emulators — libretro cores (C, fast) + PyBoy fallback.

Digivice keeps the SPI panel; frames are blitted into Qt like the original GB view.
"""

from __future__ import annotations

import os
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional, Set, Tuple

from PyQt5.QtCore import Qt, QThread, pyqtSignal, QObject, QSize, QTimer
from PyQt5.QtGui import QImage, QPixmap, QKeyEvent
from PyQt5.QtWidgets import (
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from esp_handset.pages import page_chrome

DATA = Path.home() / ".esp-handset"


def _emu_log(msg: str) -> None:
    line = f"{time.strftime('%H:%M:%S')} {msg}"
    print(f"[emu] {msg}", flush=True)
    try:
        path = DATA / "emu-last.log"
        prev = ""
        if path.is_file():
            prev = path.read_text(encoding="utf-8", errors="replace")
        path.write_text(
            "\n".join((prev + line + "\n").splitlines()[-80:]) + "\n",
            encoding="utf-8",
        )
    except Exception:
        pass

# Confirm=A, Back=B, Home=Start, Select=Select — exit = hold Confirm+Back+Home
_BTN_MAP = {
    Qt.Key_Up: "up",
    Qt.Key_Down: "down",
    Qt.Key_Left: "left",
    Qt.Key_Right: "right",
    Qt.Key_Return: "a",
    Qt.Key_Enter: "a",
    Qt.Key_X: "a",
    Qt.Key_Space: "a",
    Qt.Key_Z: "b",
    Qt.Key_Escape: "b",
    Qt.Key_Tab: "select",
    Qt.Key_Shift: "select",
    Qt.Key_S: "start",
    Qt.Key_1: "start",
    Qt.Key_Home: "start",
    Qt.Key_2: "select",
    Qt.Key_A: "y",
    Qt.Key_Q: "x",
    Qt.Key_W: "l",
    Qt.Key_E: "r",
}


@dataclass(frozen=True)
class EmuSystem:
    key: str
    title: str
    subtitle: str
    glyph: str
    folder: str
    extensions: Tuple[str, ...]
    cores: Tuple[str, ...]
    native: Tuple[int, int]
    tip_extra: str = ""
    builtin: bool = False


SYSTEMS: Dict[str, EmuSystem] = {
    "gb": EmuSystem(
        "gb",
        "Game Boy",
        "GB / GBC · gambatte",
        "♠",
        "gb",
        (".gb", ".gbc", ".sgb"),
        ("gambatte_libretro.so",),
        (160, 144),
        "C core (gambatte) when present · PyBoy fallback",
    ),
    "nes": EmuSystem(
        "nes",
        "NES",
        "Famicom · fceumm",
        "◆",
        "nes",
        (".nes", ".fds", ".unf", ".unif", ".nsf"),
        ("fceumm_libretro.so", "nestopia_libretro.so"),
        (256, 240),
    ),
    "smsgg": EmuSystem(
        "smsgg",
        "SMS / GG",
        "Master System · Game Gear",
        "◎",
        "sms",
        (".sms", ".gg", ".sg"),
        ("genesis_plus_gx_libretro.so",),
        (256, 192),
    ),
}

EMU_PAGE_KEYS = tuple(SYSTEMS.keys())

ROM_EXT_TO_FOLDER = {
    ext: sys.folder for sys in SYSTEMS.values() for ext in sys.extensions
}


def rom_root() -> Path:
    p = DATA / "roms"
    p.mkdir(parents=True, exist_ok=True)
    return p


def system_rom_dirs(sys: EmuSystem) -> List[Path]:
    sub = sys.folder
    alts = {sub, sub.lower(), sub.upper(), sub.title()}
    dirs: List[Path] = []
    roots = (
        DATA / "roms",
        Path.home() / "roms",
        Path.home() / "ROMs",
        Path("/opt/esp-handset/roms"),
    )
    for root in roots:
        for name in alts:
            dirs.append(root / name)
        dirs.append(root)
    return dirs


def ensure_rom_dir(sys: EmuSystem) -> Path:
    d = DATA / "roms" / sys.folder
    d.mkdir(parents=True, exist_ok=True)
    return d


def _bios_dir(sys: EmuSystem) -> Path:
    """Nestopia looks here for NstDatabase.xml; keep user + /opt copies."""
    user = DATA / "bios" / sys.folder
    user.mkdir(parents=True, exist_ok=True)
    shared = Path("/opt/esp-handset/bios") / sys.folder
    want = "NstDatabase.xml" if sys.key == "nes" else ""
    if want:
        if (shared / want).is_file():
            return shared
        if (user / want).is_file():
            return user
    return user


def list_roms(sys: EmuSystem) -> List[Path]:
    found: List[Path] = []
    seen = set()
    ensure_rom_dir(sys)
    for d in system_rom_dirs(sys):
        if not d.is_dir():
            continue
        try:
            for p in sorted(d.iterdir(), key=lambda x: x.name.casefold()):
                if not p.is_file():
                    continue
                if p.suffix.lower() not in sys.extensions:
                    continue
                if p.name.upper() == "README.TXT":
                    continue
                try:
                    key = str(p.resolve())
                except OSError:
                    key = str(p)
                if key in seen:
                    continue
                seen.add(key)
                found.append(p)
        except OSError:
            continue
    return found


def _pyboy_ok() -> Tuple[bool, str]:
    try:
        import pyboy  # noqa: F401

        return True, f"PyBoy {getattr(pyboy, '__version__', '?')}"
    except ImportError:
        return False, "PyBoy not installed"


def backend_status(sys: EmuSystem) -> Tuple[bool, str]:
    if sys.builtin:
        return True, "Built-in CHIP-8"
    from esp_handset.libretro_host import find_core

    core = find_core(sys.cores)
    if core is not None:
        return True, f"Core {core.name}"
    if sys.key == "gb":
        ok, msg = _pyboy_ok()
        if ok:
            return True, f"{msg} (fallback)"
        return False, "Need gambatte core or: sudo pip3 install --break-system-packages pyboy"
    names = ", ".join(sys.cores[:2]) or "libretro"
    _kick_libretro_cores()
    return False, f"Need core ({names}). Installing…"


_CORE_KICK = 0.0
_CORE_INSTALL_LOCK = threading.Lock()
_CORE_INSTALL_STATE = "idle"
_CORE_INSTALL_MSG = ""


def _sudo_ensure_cores(timeout: float = 240.0) -> str:
    cmds = (
        ["sudo", "-n", "digivice-libretro-cores"],
        ["sudo", "-n", "/usr/local/bin/digivice-libretro-cores"],
        ["sudo", "-n", "bash", "/usr/local/bin/digivice-libretro-cores"],
        ["sudo", "-n", "/opt/esp-handset/session/ensure-libretro-cores.sh"],
        ["sudo", "-n", "bash", "/opt/esp-handset/session/ensure-libretro-cores.sh"],
    )
    last = "core install not available"
    for cmd in cmds:
        try:
            r = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return "core install timed out"
        except FileNotFoundError:
            continue
        except Exception as e:
            last = str(e)
            continue
        out = ((r.stdout or "") + (r.stderr or "")).strip()
        _emu_log(f"cores {' '.join(cmd)} rc={r.returncode}")
        if r.returncode == 0:
            return out[-300:] or "cores ok"
        last = out[-300:] or f"rc={r.returncode}"
        low = out.lower()
        if "password is required" in low or "not found" in low:
            continue
        return last
    return last


def _install_cores_bg() -> None:
    global _CORE_INSTALL_STATE, _CORE_INSTALL_MSG
    try:
        out = _sudo_ensure_cores(300.0)
        from esp_handset.libretro_host import find_core

        if find_core(
            (
                "gambatte_libretro.so",
                "fceumm_libretro.so",
                "nestopia_libretro.so",
                "genesis_plus_gx_libretro.so",
            )
        ):
            with _CORE_INSTALL_LOCK:
                _CORE_INSTALL_STATE = "ok"
                _CORE_INSTALL_MSG = ""
            _emu_log("cores install OK")
            return
        with _CORE_INSTALL_LOCK:
            _CORE_INSTALL_STATE = "failed"
            _CORE_INSTALL_MSG = out or "cores still missing"
        _emu_log(f"cores install failed: {_CORE_INSTALL_MSG[:100]}")
    except Exception as e:
        with _CORE_INSTALL_LOCK:
            _CORE_INSTALL_STATE = "failed"
            _CORE_INSTALL_MSG = str(e)
        _emu_log(f"cores install err: {e}")


def prepare_cores(sys: EmuSystem, timeout: float = 150.0) -> bool:
    """Download/locate libretro cores. Safe from a worker thread."""
    from esp_handset.libretro_host import find_core

    if sys.builtin or find_core(sys.cores):
        return True
    _kick_libretro_cores(force=True)
    deadline = time.time() + max(30.0, timeout)
    while time.time() < deadline:
        if find_core(sys.cores):
            return True
        with _CORE_INSTALL_LOCK:
            state = _CORE_INSTALL_STATE
        if state != "running":
            break
        time.sleep(1.0)
    left = max(30.0, deadline - time.time())
    if left >= 30.0:
        _sudo_ensure_cores(left)
    return find_core(sys.cores) is not None


def _kick_libretro_cores(*, force: bool = False) -> None:
    """Fetch nestopia/fceumm/… in the background. Never blocks the UI."""
    global _CORE_KICK
    now = time.time()
    with _CORE_INSTALL_LOCK:
        if _CORE_INSTALL_STATE == "running" and now - _CORE_KICK < 300.0:
            return
        if not force and _CORE_INSTALL_STATE != "failed" and now - _CORE_KICK < 120.0:
            return
        _CORE_INSTALL_STATE = "running"
        _CORE_INSTALL_MSG = ""
    _CORE_KICK = now
    threading.Thread(target=_install_cores_bg, name="libretro-cores", daemon=True).start()


def _set_nonblock(fd: int) -> None:
    try:
        import fcntl

        fl = fcntl.fcntl(fd, fcntl.F_GETFL)
        fcntl.fcntl(fd, fcntl.F_SETFL, fl | os.O_NONBLOCK)
    except Exception:
        pass


def _write_pcm(pcm, blob: bytes):
    if pcm is None or not blob or pcm.stdin is None:
        return pcm
    if pcm.poll() is not None:
        return None
    try:
        pcm.stdin.write(blob)
    except (BlockingIOError, BrokenPipeError, OSError):
        return pcm if pcm.poll() is None else None
    except Exception:
        return pcm
    return pcm


def _qimage_from_rgb(arr) -> Optional[QImage]:
    if arr is None:
        return None
    try:
        h, w = int(arr.shape[0]), int(arr.shape[1])
        rgb = arr if arr.flags["C_CONTIGUOUS"] else arr.copy()
        qimg = QImage(rgb.data, w, h, 3 * w, QImage.Format_RGB888)
        return qimg.copy()
    except Exception:
        return None


def _qimage_from_raw(raw: bytes, w: int, h: int, pitch: int, pix_fmt: int) -> Optional[QImage]:
    """Qt-native blit — works when numpy is missing. Never wrap an undersized buffer."""
    if not raw or w <= 0 or h <= 0 or w > 1024 or h > 1024:
        return None
    try:
        from esp_handset.libretro_host import (
            RETRO_PIXEL_FORMAT_RGB565,
            RETRO_PIXEL_FORMAT_XRGB8888,
        )

        if pix_fmt == RETRO_PIXEL_FORMAT_XRGB8888:
            row = max(int(pitch), w * 4)
            qfmt = QImage.Format_RGB32
        elif pix_fmt == RETRO_PIXEL_FORMAT_RGB565:
            row = max(int(pitch), w * 2)
            qfmt = QImage.Format_RGB16
        else:
            row = max(int(pitch), w * 2)
            qfmt = QImage.Format_RGB555
        if row <= 0 or len(raw) < row * h:
            return None
        img = QImage(raw, w, h, row, qfmt)
        if img.isNull():
            return None
        return img.copy().convertToFormat(QImage.Format_RGB888)
    except Exception:
        return None


def _frame_to_qimage(raw: bytes, w: int, h: int, pitch: int, pix_fmt: int) -> Optional[QImage]:
    from esp_handset.libretro_host import raw_to_rgb888

    arr = raw_to_rgb888(raw, w, h, pitch, pix_fmt)
    img = _qimage_from_rgb(arr)
    if img is not None:
        return img
    return _qimage_from_raw(raw, w, h, pitch, pix_fmt)


class EmuWorker(QThread):
    frame = pyqtSignal(object)
    failed = pyqtSignal(str)
    stopped = pyqtSignal()

    def __init__(self, rom: Path, system: EmuSystem, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._rom = rom
        self._sys = system
        self._stop = False
        self._held: Set[str] = set()
        self._pending_press: Set[str] = set()
        self._pending_release: Set[str] = set()
        self._pad_lock = threading.Lock()

    def request_stop(self) -> None:
        self._stop = True

    def button_down(self, name: str) -> None:
        with self._pad_lock:
            self._pending_press.add(name)
            self._pending_release.discard(name)

    def button_up(self, name: str) -> None:
        with self._pad_lock:
            self._pending_release.add(name)
            self._pending_press.discard(name)

    def button_tap(self, name: str) -> None:
        with self._pad_lock:
            self._pending_press.add(name)
            self._pending_release.add(name)

    def _sync_held(self) -> Set[str]:
        with self._pad_lock:
            for name in list(self._pending_press):
                self._pending_press.discard(name)
                self._held.add(name)
            for name in list(self._pending_release):
                self._pending_release.discard(name)
                self._held.discard(name)
            return set(self._held)

    def run(self) -> None:
        try:
            _emu_log(f"start {self._sys.key} {self._rom.name}")
            if self._run_libretro():
                return
            if self._sys.key == "gb":
                self._run_pyboy()
                return
            ok, msg = backend_status(self._sys)
            err = msg if not ok else "Core failed to start"
            _emu_log(err)
            self.failed.emit(err)
        except Exception as e:
            _emu_log(f"crash {e}")
            self.failed.emit(str(e)[:140])
        finally:
            self.stopped.emit()

    def _open_pcm(self, rate: int, want: bool):
        if not want:
            return None
        try:
            from esp_handset.audio_out import open_usb_play_stream

            pcm = open_usb_play_stream(rate=int(rate), channels=2)
            if pcm is not None and pcm.stdin is not None:
                try:
                    _set_nonblock(pcm.stdin.fileno())
                except Exception:
                    pass
            return pcm
        except Exception:
            return None

    def _close_pcm(self, pcm) -> None:
        try:
            from esp_handset.audio_out import close_usb_play_stream

            close_usb_play_stream(pcm)
        except Exception:
            pass

    def _want_sound(self) -> bool:
        try:
            from esp_handset.audio_out import _sounds_on

            return bool(_sounds_on())
        except Exception:
            return True

    def _pace(self, next_t: float, frame_s: float) -> float:
        now = time.perf_counter()
        sleep_s = next_t - now
        if sleep_s > 0.0008:
            time.sleep(min(sleep_s, 0.05))
            return next_t + frame_s
        if now > next_t + 0.08:
            return now + frame_s
        return next_t + frame_s

    def _run_libretro(self) -> bool:
        from esp_handset.libretro_host import LibretroCore, find_cores

        if not prepare_cores(self._sys, 120.0):
            _emu_log(f"no cores for {self._sys.key}: {self._sys.cores}")
            self.failed.emit(
                (
                    "NES core missing.\nSettings → Update,\nwait ~2 min, Play again."
                    if self._sys.key == "nes"
                    else "SMS / GG core missing.\nSettings → Update,\nwait ~2 min, Play again."
                )
            )
            return True
        core_paths = find_cores(self._sys.cores)
        if not core_paths:
            _emu_log(f"no cores for {self._sys.key}: {self._sys.cores}")
            return False
        last_err = None
        for core_path in core_paths:
            try:
                _emu_log(f"load {core_path.name}")
                return self._run_one_core(core_path, LibretroCore)
            except Exception as e:
                last_err = e
                _emu_log(f"fail {core_path.name}: {e}")
                continue
        if self._sys.key == "gb":
            return False
        names = ", ".join(p.name.replace("_libretro.so", "") for p in core_paths[:3])
        detail = str(last_err)[:120] if last_err else "could not start"
        self.failed.emit(f"{detail}\nTried {names}")
        return True

    def _run_one_core(self, core_path: Path, LibretroCore) -> bool:
        save_dir = DATA / "saves" / self._sys.folder
        sys_dir = _bios_dir(self._sys)
        core = None
        pcm = None
        try:
            core = LibretroCore(
                core_path,
                self._rom,
                save_dir=save_dir,
                system_dir=sys_dir,
            )
            core.load()
            _emu_log(
                f"loaded {core_path.name} {core.width}x{core.height} "
                f"need={self._rom.name}"
            )
            # Warm up — some NES cores need a few frames before first video cb.
            for _ in range(12):
                core.set_held(set())
                core.run_frame()
            want = self._want_sound()
            rate = int(round(core.sample_rate)) or 44100
            pcm = self._open_pcm(rate, want)
            fps = core.fps if core.fps > 1 else 60.0
            frame_s = 1.0 / fps
            emit_every = 1.0 / min(30.0, fps)
            next_t = time.perf_counter()
            last_emit = 0.0
            no_picture = 0
            while not self._stop:
                core.set_held(self._sync_held())
                try:
                    raw, w, h, fmt, pitch = core.run_frame()
                except Exception as e:
                    self.failed.emit(f"{core_path.name} crashed\n{str(e)[:80]}")
                    return True
                if want and pcm is not None:
                    pcm = _write_pcm(pcm, core.take_audio())
                now = time.perf_counter()
                if raw and (now - last_emit) >= emit_every:
                    last_emit = now
                    use_pitch = pitch or (len(raw) // max(h, 1))
                    img = _frame_to_qimage(raw, w, h, use_pitch, fmt)
                    if img is not None:
                        no_picture = 0
                        self.frame.emit(img)
                    else:
                        no_picture += 1
                elif not raw:
                    no_picture += 1
                if no_picture > 240:
                    self.failed.emit(
                        f"{core_path.name}: no video\n"
                        "Try Settings → Update\n"
                        "or a plain ROM file"
                    )
                    return True
                next_t = self._pace(next_t, frame_s)
            return True
        finally:
            self._close_pcm(pcm)
            if core is not None:
                try:
                    core.close()
                except Exception:
                    pass

    def _run_pyboy(self) -> None:
        """Optimized PyBoy fallback — no double throttle, skip draws, nonblock audio."""
        try:
            from pyboy import PyBoy  # noqa: F401
        except ImportError as e:
            self.failed.emit(f"PyBoy missing: {e}")
            return

        boy = None
        pcm = None
        want = self._want_sound()
        try:
            boy = self._open_pyboy(want)
            if boy is None:
                self.failed.emit("PyBoy would not start")
                return
            try:
                boy.set_emulation_speed(0)
            except Exception:
                pass

            rate = 48000
            try:
                rate = int(getattr(boy.sound, "sample_rate", 0) or 48000)
            except Exception:
                rate = 48000
            pcm = self._open_pcm(rate, want)

            frame_s = 1.0 / 59.7275
            next_t = time.perf_counter()
            last_emit = 0.0
            emit_every = 1.0 / 30.0
            slow = 0
            prev_held: Set[str] = set()
            names = ("up", "down", "left", "right", "a", "b", "start", "select")
            while not self._stop:
                t0 = time.perf_counter()
                held = self._sync_held()
                try:
                    for name in names:
                        if name in held and name not in prev_held:
                            try:
                                boy.button_press(name)
                            except Exception:
                                boy.button(name)
                        elif name not in held and name in prev_held:
                            try:
                                boy.button_release(name)
                            except Exception:
                                pass
                except Exception:
                    pass
                prev_held = set(held)

                render = (t0 - last_emit) >= emit_every
                try:
                    alive = boy.tick(1, render, want)
                except TypeError:
                    try:
                        alive = boy.tick(1, render)
                    except TypeError:
                        alive = boy.tick()
                if alive is False:
                    break

                if want and pcm is not None:
                    pcm = self._feed_pyboy_audio(boy, pcm)

                if render:
                    last_emit = t0
                    img = self._pyboy_qimage(boy)
                    if img is not None:
                        self.frame.emit(img)

                tick_ms = (time.perf_counter() - t0) * 1000.0
                if tick_ms > 22:
                    slow += 1
                elif slow > 0:
                    slow -= 1
                if want and slow > 45:
                    want = False

                next_t = self._pace(next_t, frame_s)
        finally:
            self._close_pcm(pcm)
            if boy is not None:
                try:
                    boy.stop(save=True)
                except Exception:
                    try:
                        boy.stop()
                    except Exception:
                        pass

    def _open_pyboy(self, want_sound: bool):
        from pyboy import PyBoy

        cgb = self._rom.suffix.lower() in (".gbc", ".sgb")
        attempts = []
        base = {"window": "null"}
        if not cgb:
            attempts.append({**base, "cgb": False, "sound_emulated": want_sound})
        if want_sound:
            attempts.append({**base, "sound_emulated": True, "sound_volume": 50})
            attempts.append({**base, "sound": True})
        else:
            attempts.append({**base, "sound_emulated": False})
            attempts.append({**base, "sound": False})
        attempts.append(base)
        last_err = None
        for kw in attempts:
            try:
                return PyBoy(str(self._rom), **kw)
            except TypeError:
                continue
            except Exception as e:
                last_err = e
                break
        if last_err:
            raise last_err
        return None

    @staticmethod
    def _feed_pyboy_audio(boy, pcm):
        try:
            arr = boy.sound.ndarray
        except Exception:
            return pcm
        if arr is None:
            return pcm
        try:
            n = getattr(arr, "size", 0)
            if not n:
                return pcm
            import numpy as np

            a = np.ascontiguousarray(arr)
            if a.dtype == np.int8:
                pcm16 = (a.astype(np.int16) << 8).tobytes()
            elif a.dtype == np.int16:
                pcm16 = a.tobytes()
            else:
                pcm16 = (np.clip(a, -1, 1) * 24000).astype(np.int16).tobytes()
            return _write_pcm(pcm, pcm16)
        except Exception:
            return pcm

    @staticmethod
    def _pyboy_qimage(boy) -> Optional[QImage]:
        try:
            import numpy as np

            arr = boy.screen.ndarray
            if arr is not None:
                rgb = np.ascontiguousarray(arr[:, :, :3])
                return _qimage_from_rgb(rgb)
        except Exception:
            pass
        try:
            pil = boy.screen.image
            if pil is None:
                return None
            rgb = pil.convert("RGB")
            data = rgb.tobytes()
            w, h = rgb.size
            return QImage(data, w, h, 3 * w, QImage.Format_RGB888).copy()
        except Exception:
            return None


class EmuPlayView(QWidget):
    digi_gamepad = True

    def __init__(self, system: EmuSystem, on_quit: Callable[[], None]):
        super().__init__()
        self._sys = system
        self._on_quit = on_quit
        self._worker: Optional[EmuWorker] = None
        self._held_qt: Dict[int, str] = {}
        self._last_frame: Optional[QImage] = None
        self._surface = False
        self._exit_since: Optional[float] = None
        self._exit_armed = True
        self._exit_timer = QTimer(self)
        self._exit_timer.setInterval(50)
        self._exit_timer.timeout.connect(self._poll_exit_combo)
        self._boot_timer = QTimer(self)
        self._boot_timer.setSingleShot(True)
        self._boot_timer.timeout.connect(self._boot_timeout)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setObjectName("emuPlayView")
        self.setAttribute(Qt.WA_OpaquePaintEvent, True)
        self.setAutoFillBackground(True)
        pal = self.palette()
        pal.setColor(self.backgroundRole(), Qt.black)
        self.setPalette(pal)
        self.setStyleSheet("background:#000000; color:#9ab;")

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self.screen = QLabel("")
        self.screen.setAlignment(Qt.AlignCenter)
        self.screen.setStyleSheet("background:#000000; color:#888;")
        self.screen.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.screen.setScaledContents(False)
        lay.addWidget(self.screen, 1)

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(240, 320)

    @property
    def playing(self) -> bool:
        return self._worker is not None and self._worker.isRunning()

    @property
    def capturing_pad(self) -> bool:
        """True while the play surface is up — including load / error screens."""
        return bool(self._surface)

    def start_rom(self, rom: Path) -> None:
        self.stop()
        self._surface = True
        self._last_frame = None
        self._exit_since = None
        self._exit_armed = True
        self.screen.setPixmap(QPixmap())
        self.screen.setText(f"Loading\n{rom.name}")
        _emu_log(f"ui start {self._sys.key} {rom}")
        w = EmuWorker(rom, self._sys, self)
        w.frame.connect(self._on_frame)
        w.failed.connect(self._on_fail)
        self._worker = w
        w.start(QThread.HighPriority)
        self._exit_timer.start()
        self._boot_timer.start(12000 if self._sys.key == "nes" else 6000)
        self.setFocus(Qt.OtherFocusReason)
        self.raise_()

    def stop(self) -> None:
        self._exit_timer.stop()
        self._boot_timer.stop()
        self._exit_since = None
        self._surface = False
        w = self._worker
        self._worker = None
        self._held_qt.clear()
        self._last_frame = None
        if w is not None:
            try:
                w.frame.disconnect()
            except Exception:
                pass
            try:
                w.failed.disconnect()
            except Exception:
                pass
            w.request_stop()
            # Never QThread.terminate() a libretro worker — that SIGSEGVs the next ROM.
            if not w.wait(5000):
                _emu_log("worker still stopping after 5s")
        self.screen.setPixmap(QPixmap())
        self.screen.setText("")

    def _exit_combo_held(self) -> bool:
        keys = self._held_qt
        confirm = Qt.Key_Return in keys or Qt.Key_Enter in keys
        back = Qt.Key_Escape in keys
        home = Qt.Key_Home in keys
        return confirm and back and home

    def _poll_exit_combo(self) -> None:
        if not self.playing:
            self._exit_since = None
            return
        if self._exit_combo_held():
            now = time.monotonic()
            if self._exit_since is None:
                self._exit_since = now
            elif self._exit_armed and (now - self._exit_since) >= 0.45:
                self._exit_armed = False
                self._exit_since = None
                if self._worker is not None:
                    for name in list(set(self._held_qt.values())):
                        self._worker.button_up(name)
                self._held_qt.clear()
                cb = self._on_quit
                if callable(cb):
                    cb()
        else:
            self._exit_since = None
            self._exit_armed = True

    def _tap(self, name: str) -> None:
        if self._worker is not None:
            self._worker.button_tap(name)

    def _fit_size(self, nw: int, nh: int) -> QSize:
        aw = max(self.screen.width(), 1)
        ah = max(self.screen.height(), 1)
        nw = max(int(nw), 1)
        nh = max(int(nh), 1)
        sx = max(1, aw // nw)
        sy = max(1, ah // nh)
        scale = min(sx, sy)
        iw, ih = nw * scale, nh * scale
        if iw < aw * 0.85 or ih < ah * 0.85:
            fit_w = aw
            fit_h = int(round(aw * nh / nw))
            if fit_h > ah:
                fit_h = ah
                fit_w = int(round(ah * nw / nh))
            return QSize(max(fit_w, 1), max(fit_h, 1))
        return QSize(iw, ih)

    def _paint_frame(self, qimg: QImage) -> None:
        target = self._fit_size(qimg.width(), qimg.height())
        pix = QPixmap.fromImage(qimg).scaled(
            target,
            Qt.IgnoreAspectRatio,
            Qt.FastTransformation,
        )
        self.screen.setPixmap(pix)

    def _on_frame(self, qimg: QImage) -> None:
        if qimg is None or qimg.isNull():
            return
        self._boot_timer.stop()
        self._last_frame = qimg
        self.screen.setText("")
        self._paint_frame(qimg)

    def _on_fail(self, msg: str) -> None:
        self._boot_timer.stop()
        _emu_log(f"ui fail {msg}")
        self.screen.setText(msg or "Core failed")

    def _boot_timeout(self) -> None:
        if self._last_frame is not None:
            return
        from esp_handset.libretro_host import find_core

        core = find_core(self._sys.cores)
        if not core:
            msg = (
                "NES core not installed.\n"
                "Settings → Update,\n"
                "wait ~2 min, try again."
                if self._sys.key == "nes"
                else "SMS / GG core missing.\nSettings → Update"
            )
        else:
            msg = (
                f"No picture from {core.name}.\n"
                "Try a plain ROM file\n"
                "Back = list"
            )
        _emu_log(f"ui boot timeout (no frames) core={core}")
        self.screen.setText(msg)

    def resizeEvent(self, e) -> None:  # noqa: N802
        super().resizeEvent(e)
        if self._last_frame is not None:
            self._paint_frame(self._last_frame)

    def keyPressEvent(self, e: QKeyEvent) -> None:  # noqa: N802
        if e.isAutoRepeat():
            e.accept()
            return
        name = _BTN_MAP.get(e.key())
        if name and self._worker is not None:
            self._held_qt[e.key()] = name
            self._worker.button_down(name)
            self._poll_exit_combo()
            e.accept()
            return
        e.accept()

    def keyReleaseEvent(self, e: QKeyEvent) -> None:  # noqa: N802
        if e.isAutoRepeat():
            e.accept()
            return
        name = self._held_qt.pop(e.key(), None) or _BTN_MAP.get(e.key())
        if name and self._worker is not None:
            self._worker.button_up(name)
            self._poll_exit_combo()
            e.accept()
            return
        e.accept()

    def hideEvent(self, e) -> None:  # noqa: N802
        # Do not stop() here — stacked/layout hide/show would kill the core
        # the instant Play starts. show_list / navigate-away stop instead.
        super().hideEvent(e)


def make_emu_page(
    system: EmuSystem,
    on_back: Callable[[], None],
    *,
    on_receive: Optional[Callable[[], None]] = None,
) -> QWidget:
    list_page = QWidget()
    lay = QVBoxLayout(list_page)
    lay.setContentsMargins(2, 2, 2, 2)
    lay.setSpacing(2)

    ok_be, be_msg = backend_status(system)
    extra = f"\n{system.tip_extra}" if system.tip_extra else ""
    tip = QLabel(
        (
            f"{be_msg}{extra}\n"
            "Confirm on a ROM to play · Play button also works\n"
            "In-game: Confirm=A · Back=B · Home=Start · Select=Select\n"
            "Hold Confirm+Back+Home (~0.5s) to quit"
        )
        if ok_be
        else f"{be_msg}\nROMs still work after: Settings → Update"
    )
    tip.setWordWrap(True)
    tip.setStyleSheet("color:#9ab;font-size:9px;")
    status = QLabel("")
    status.setWordWrap(True)
    status.setStyleSheet("color:#ffe66d;font-size:11px;font-weight:700;")
    lst = QListWidget()
    lst.setFocusPolicy(Qt.StrongFocus)
    lst.setStyleSheet(
        "QListWidget { background: transparent; border: none; }"
        "QListWidget::item { padding: 4px; min-height: 22px; }"
        "QListWidget::item:selected { background:#FFE600; color:#000; }"
    )
    play = QPushButton("Play")
    play.setFixedHeight(28)
    play.setStyleSheet("font-weight:800;")
    play.setEnabled(False)
    recv = QPushButton("Receive ROMs (Wi‑Fi)")
    recv.setFixedHeight(26)
    refresh = QPushButton("Reload")
    refresh.setFixedHeight(24)
    lay.addWidget(tip)
    lay.addWidget(status)
    lay.addWidget(lst, 1)
    lay.addWidget(play)
    lay.addWidget(recv)
    lay.addWidget(refresh)

    play_view = EmuPlayView(system, on_quit=lambda: None)
    stack = QStackedWidget()
    stack.addWidget(list_page)
    stack.addWidget(play_view)

    state = {"playing": False}

    def chrome_back() -> None:
        if state["playing"] and play_view.playing:
            return
        if state["playing"]:
            show_list()
            return
        on_back()

    chrome = page_chrome(system.title, stack, chrome_back, scroll=False)

    def show_list() -> None:
        state["playing"] = False
        play_view.stop()
        stack.setCurrentWidget(list_page)
        refresh_list()
        QTimer.singleShot(0, _focus_rom_list)

    def show_play() -> None:
        state["playing"] = True
        play_view._surface = True
        stack.setCurrentWidget(play_view)
        play_view.setFocus(Qt.OtherFocusReason)

    play_view._on_quit = show_list  # type: ignore[method-assign]

    def refresh_list() -> None:
        lst.clear()
        roms = list_roms(system)
        ok, msg = backend_status(system)
        play.setEnabled(bool(roms))
        folder = ensure_rom_dir(system)
        status.setText(f"{msg}\n{len(roms)} ROM(s) · {folder.name}/")
        if not ok and not system.builtin:
            _kick_libretro_cores()
        if not roms:
            empty = QListWidgetItem("No ROMs yet\n→ Receive ROMs (Wi‑Fi)")
            empty.setFlags(Qt.NoItemFlags)
            lst.addItem(empty)
            return
        for p in roms:
            item = QListWidgetItem(p.name)
            item.setData(Qt.UserRole, str(p))
            lst.addItem(item)
        if lst.currentRow() < 0:
            lst.setCurrentRow(0)

    def launch() -> None:
        item = lst.currentItem()
        path = item.data(Qt.UserRole) if item is not None else None
        if not path:
            status.setText("Pick a ROM first")
            return
        rom = Path(str(path))
        if not rom.is_file():
            status.setText("ROM missing")
            return
        ok, msg = backend_status(system)
        _emu_log(f"launch {system.key} {rom.name} core_ok={ok}")
        show_play()
        play_view.screen.setText(f"Loading\n{rom.name}")
        play_view.start_rom(rom)

    def do_receive() -> None:
        if on_receive is not None:
            on_receive()
        else:
            status.setText("Open Tools → Transfer · ROMs")

    def on_hardware_back() -> bool:
        if stack.currentWidget() is play_view:
            if play_view.playing:
                return True
            show_list()
            return True
        return False

    def on_navigate_away() -> None:
        if state["playing"] or stack.currentWidget() is play_view or play_view.playing:
            show_list()

    lst.itemActivated.connect(lambda _i: launch())
    play.clicked.connect(launch)
    refresh.clicked.connect(refresh_list)
    recv.clicked.connect(do_receive)

    def _focus_rom_list() -> None:
        if state["playing"] or stack.currentWidget() is not list_page:
            return
        from esp_handset import digi_nav

        digi_nav.clear_highlights(chrome)
        lst.setFocus(Qt.OtherFocusReason)
        digi_nav._highlight(lst, True)
        if lst.count() > 0 and lst.currentRow() < 0:
            lst.setCurrentRow(0)

    def on_page_show() -> None:
        if state["playing"]:
            return
        refresh_list()
        QTimer.singleShot(0, _focus_rom_list)

    chrome.on_hardware_back = on_hardware_back  # type: ignore[attr-defined]
    chrome.on_navigate_away = on_navigate_away  # type: ignore[attr-defined]
    chrome.on_page_show = on_page_show  # type: ignore[attr-defined]
    chrome.emu_board = play_view  # type: ignore[attr-defined]
    chrome.gb_board = play_view  # type: ignore[attr-defined]
    refresh_list()
    return chrome
