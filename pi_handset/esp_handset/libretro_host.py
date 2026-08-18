"""Minimal libretro frontend — tick C cores, no window (Digivice owns SPI)."""

from __future__ import annotations

import ctypes
from ctypes import (
    CFUNCTYPE,
    POINTER,
    Structure,
    byref,
    c_bool,
    c_char_p,
    c_double,
    c_float,
    c_int,
    c_int16,
    c_size_t,
    c_uint,
    c_void_p,
    cast,
    memmove,
    string_at,
)
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Set, Tuple

RETRO_DEVICE_JOYPAD = 1
RETRO_DEVICE_ID_JOYPAD_B = 0
RETRO_DEVICE_ID_JOYPAD_Y = 1
RETRO_DEVICE_ID_JOYPAD_SELECT = 2
RETRO_DEVICE_ID_JOYPAD_START = 3
RETRO_DEVICE_ID_JOYPAD_UP = 4
RETRO_DEVICE_ID_JOYPAD_DOWN = 5
RETRO_DEVICE_ID_JOYPAD_LEFT = 6
RETRO_DEVICE_ID_JOYPAD_RIGHT = 7
RETRO_DEVICE_ID_JOYPAD_A = 8
RETRO_DEVICE_ID_JOYPAD_X = 9
RETRO_DEVICE_ID_JOYPAD_L = 10
RETRO_DEVICE_ID_JOYPAD_R = 11
RETRO_DEVICE_ID_JOYPAD_MASK = 256

RETRO_MEMORY_SAVE_RAM = 0

RETRO_ENVIRONMENT_GET_OVERSCAN = 2
RETRO_ENVIRONMENT_GET_CAN_DUPE = 3
RETRO_ENVIRONMENT_SET_MESSAGE = 6
RETRO_ENVIRONMENT_SET_PERFORMANCE_LEVEL = 8
RETRO_ENVIRONMENT_GET_SYSTEM_DIRECTORY = 9
RETRO_ENVIRONMENT_SET_PIXEL_FORMAT = 10
RETRO_ENVIRONMENT_SET_INPUT_DESCRIPTORS = 11
RETRO_ENVIRONMENT_SET_KEYBOARD_CALLBACK = 12
RETRO_ENVIRONMENT_GET_VARIABLE = 15
RETRO_ENVIRONMENT_SET_VARIABLES = 16
RETRO_ENVIRONMENT_GET_VARIABLE_UPDATE = 17
RETRO_ENVIRONMENT_SET_SUPPORT_NO_GAME = 18
RETRO_ENVIRONMENT_GET_LOG_INTERFACE = 27
RETRO_ENVIRONMENT_GET_CORE_ASSETS_DIRECTORY = 30
RETRO_ENVIRONMENT_GET_SAVE_DIRECTORY = 31
RETRO_ENVIRONMENT_SET_SYSTEM_AV_INFO = 32
RETRO_ENVIRONMENT_SET_SUBSYSTEM_INFO = 34
RETRO_ENVIRONMENT_SET_CONTROLLER_INFO = 35
RETRO_ENVIRONMENT_SET_MEMORY_MAPS = 36
RETRO_ENVIRONMENT_SET_GEOMETRY = 37
RETRO_ENVIRONMENT_GET_USERNAME = 38
RETRO_ENVIRONMENT_GET_LANGUAGE = 39
RETRO_ENVIRONMENT_SET_SUPPORT_ACHIEVEMENTS = 42
RETRO_ENVIRONMENT_SET_SERIALIZATION_QUIRKS = 44
RETRO_ENVIRONMENT_GET_AUDIO_VIDEO_ENABLE = 47
RETRO_ENVIRONMENT_GET_FASTFORWARDING = 49
RETRO_ENVIRONMENT_GET_CORE_OPTIONS_VERSION = 52
RETRO_ENVIRONMENT_SET_CORE_OPTIONS = 53
RETRO_ENVIRONMENT_SET_CORE_OPTIONS_INTL = 54
RETRO_ENVIRONMENT_SET_CORE_OPTIONS_DISPLAY = 55
RETRO_ENVIRONMENT_GET_INPUT_BITMASKS = 51
RETRO_ENVIRONMENT_SET_MINIMUM_AUDIO_LATENCY = 63
RETRO_ENVIRONMENT_SET_CONTENT_INFO_OVERRIDE = 65
RETRO_ENVIRONMENT_GET_GAME_INFO_EXT = 66
RETRO_ENVIRONMENT_SET_CORE_OPTIONS_V2 = 67
RETRO_ENVIRONMENT_SET_CORE_OPTIONS_V2_INTL = 68
RETRO_ENVIRONMENT_SET_VARIABLE = 70

RETRO_PIXEL_FORMAT_0RGB1555 = 0
RETRO_PIXEL_FORMAT_XRGB8888 = 1
RETRO_PIXEL_FORMAT_RGB565 = 2

# Digivice names → libretro joypad ids
BTN_IDS = {
    "b": RETRO_DEVICE_ID_JOYPAD_B,
    "y": RETRO_DEVICE_ID_JOYPAD_Y,
    "select": RETRO_DEVICE_ID_JOYPAD_SELECT,
    "start": RETRO_DEVICE_ID_JOYPAD_START,
    "up": RETRO_DEVICE_ID_JOYPAD_UP,
    "down": RETRO_DEVICE_ID_JOYPAD_DOWN,
    "left": RETRO_DEVICE_ID_JOYPAD_LEFT,
    "right": RETRO_DEVICE_ID_JOYPAD_RIGHT,
    "a": RETRO_DEVICE_ID_JOYPAD_A,
    "x": RETRO_DEVICE_ID_JOYPAD_X,
    "l": RETRO_DEVICE_ID_JOYPAD_L,
    "r": RETRO_DEVICE_ID_JOYPAD_R,
}

# Fast / cheap defaults for Pi Zero 2W
_SPEED_VARS = {
    "gambatte_gbc_color_correction": "disabled",
    "gambatte_mix_frames": "disabled",
    "gambatte_gb_colorization": "disabled",
    "mgba_frameskip": "1",
    "mgba_audio_low_pass_filter": "disabled",
    "mgba_color_correction": "OFF",
    "gpsp_frameskip": "auto",
    "fceumm_overclocking": "disabled",
    "fceumm_sndquality": "Low",
    "nestopia_overclock": "1x",
    "genesis_plus_gx_lcd_filter": "disabled",
    "genesis_plus_gx_blargg_ntsc_filter": "disabled",
    "genesis_plus_gx_overscan": "disabled",
    "picodrive_drc": "enabled",
    "picodrive_audio_filter": "disabled",
}

CORE_DIRS = (
    Path("/opt/esp-handset/libretro"),
    Path.home() / ".esp-handset" / "cores",
    Path("/usr/lib/aarch64-linux-gnu/libretro"),
    Path("/usr/lib/arm-linux-gnueabihf/libretro"),
    Path("/usr/lib/libretro"),
    Path("/usr/lib/retroarch/cores"),
    Path.home() / ".config" / "retroarch" / "cores",
)


class _SystemInfo(Structure):
    _fields_ = [
        ("library_name", c_char_p),
        ("library_version", c_char_p),
        ("valid_extensions", c_char_p),
        ("need_fullpath", c_bool),
        ("block_extract", c_bool),
    ]


class _GameInfo(Structure):
    _fields_ = [
        ("path", c_char_p),
        ("data", c_void_p),
        ("size", c_size_t),
        ("meta", c_char_p),
    ]


class _Geometry(Structure):
    _fields_ = [
        ("base_width", c_uint),
        ("base_height", c_uint),
        ("max_width", c_uint),
        ("max_height", c_uint),
        ("aspect_ratio", c_float),
    ]


class _Timing(Structure):
    _fields_ = [
        ("fps", c_double),
        ("sample_rate", c_double),
    ]


class _AvInfo(Structure):
    _fields_ = [
        ("geometry", _Geometry),
        ("timing", _Timing),
    ]


class _Variable(Structure):
    _fields_ = [
        ("key", c_char_p),
        ("value", c_char_p),
    ]


_EnvCb = CFUNCTYPE(c_bool, c_uint, c_void_p)
_VideoCb = CFUNCTYPE(None, c_void_p, c_uint, c_uint, c_size_t)
_AudioCb = CFUNCTYPE(None, c_int16, c_int16)
_AudioBatchCb = CFUNCTYPE(c_size_t, POINTER(c_int16), c_size_t)
_PollCb = CFUNCTYPE(None)
_InputCb = CFUNCTYPE(c_int16, c_uint, c_uint, c_uint, c_uint)


def iter_core_dirs() -> List[Path]:
    out: List[Path] = []
    seen = set()
    for d in CORE_DIRS:
        try:
            r = d.resolve() if d.exists() else d
        except OSError:
            r = d
        key = str(r)
        if key in seen:
            continue
        seen.add(key)
        out.append(d)
    try:
        import glob as _glob

        for hit in _glob.glob("/usr/lib/*/libretro"):
            p = Path(hit)
            if str(p) not in seen:
                seen.add(str(p))
                out.append(p)
    except Exception:
        pass
    return out


def _valid_core(path: Path) -> bool:
    try:
        if path.stat().st_size < 80000:
            return False
        with open(path, "rb") as f:
            return f.read(4) == b"\x7fELF"
    except OSError:
        return False


def find_cores(so_names: Sequence[str]) -> List[Path]:
    names = list(so_names)
    found: List[Path] = []
    seen = set()
    for d in iter_core_dirs():
        if not d.is_dir():
            continue
        for name in names:
            p = d / name
            try:
                key = str(p.resolve()) if p.is_file() else ""
            except OSError:
                key = str(p) if p.is_file() else ""
            if key and key not in seen:
                if not _valid_core(p):
                    continue
                seen.add(key)
                found.append(p)
        try:
            for p in d.iterdir():
                low = p.name.lower()
                if not low.endswith(".so"):
                    continue
                for name in names:
                    stem = name.lower().replace("_libretro.so", "")
                    if stem and stem in low:
                        try:
                            if not _valid_core(p):
                                break
                            key = str(p.resolve())
                        except OSError:
                            key = str(p)
                        if key not in seen:
                            seen.add(key)
                            found.append(p)
                        break
        except OSError:
            continue
    return found


def find_core(so_names: Sequence[str]) -> Optional[Path]:
    hits = find_cores(so_names)
    return hits[0] if hits else None


class LibretroCore:
    """Load a .so core, run frames, copy RGB888 + int16 audio out."""

    def __init__(
        self,
        so_path: Path,
        rom: Path,
        *,
        save_dir: Path,
        system_dir: Path,
        extra_vars: Optional[Dict[str, str]] = None,
    ):
        self.so_path = Path(so_path)
        self.rom = Path(rom)
        self.save_dir = Path(save_dir)
        self.system_dir = Path(system_dir)
        self._vars: Dict[str, str] = dict(_SPEED_VARS)
        if extra_vars:
            self._vars.update(extra_vars)
        self._held: Set[str] = set()
        self._lib = None
        self._rom_buf = None
        self._pix_fmt = RETRO_PIXEL_FORMAT_0RGB1555
        self.fps = 60.0
        self.sample_rate = 44100.0
        self.width = 160
        self.height = 144
        self._raw = b""
        self._pitch = 0
        self._got_frame = False
        self._audio = bytearray()
        self._alive = False
        self._c_keep = []  # keep ctypes objects alive

        self.save_dir.mkdir(parents=True, exist_ok=True)
        self.system_dir.mkdir(parents=True, exist_ok=True)
        self._save_dir_s = str(self.save_dir).encode("utf-8")
        self._sys_dir_s = str(self.system_dir).encode("utf-8")
        self._save_dir_p = c_char_p(self._save_dir_s)
        self._sys_dir_p = c_char_p(self._sys_dir_s)
        self._var_bufs: Dict[str, ctypes.c_char_p] = {}

        self._env_cb = _EnvCb(self._env)
        self._video_cb = _VideoCb(self._video)
        self._audio_cb = _AudioCb(self._audio_sample)
        self._audio_batch_cb = _AudioBatchCb(self._audio_batch)
        self._poll_cb = _PollCb(self._poll)
        self._input_cb = _InputCb(self._input)
        self._c_keep.extend(
            [
                self._env_cb,
                self._video_cb,
                self._audio_cb,
                self._audio_batch_cb,
                self._poll_cb,
                self._input_cb,
                self._save_dir_p,
                self._sys_dir_p,
            ]
        )

    def set_held(self, held: Set[str]) -> None:
        self._held = set(held)

    def load(self) -> None:
        # LOCAL avoids symbol clashes (gambatte + fceumm in one process).
        mode = getattr(ctypes, "RTLD_LOCAL", 0) | getattr(ctypes, "RTLD_NOW", 2)
        try:
            self._lib = ctypes.CDLL(str(self.so_path), mode=mode)
        except OSError:
            self._lib = ctypes.CDLL(str(self.so_path))
        lib = self._lib

        lib.retro_set_environment.argtypes = [_EnvCb]
        lib.retro_set_environment.restype = None
        lib.retro_set_video_refresh.argtypes = [_VideoCb]
        lib.retro_set_video_refresh.restype = None
        lib.retro_set_audio_sample.argtypes = [_AudioCb]
        lib.retro_set_audio_sample.restype = None
        lib.retro_set_audio_sample_batch.argtypes = [_AudioBatchCb]
        lib.retro_set_audio_sample_batch.restype = None
        lib.retro_set_input_poll.argtypes = [_PollCb]
        lib.retro_set_input_poll.restype = None
        lib.retro_set_input_state.argtypes = [_InputCb]
        lib.retro_set_input_state.restype = None
        lib.retro_init.restype = None
        lib.retro_deinit.restype = None
        lib.retro_get_system_info.argtypes = [POINTER(_SystemInfo)]
        lib.retro_get_system_info.restype = None
        lib.retro_get_system_av_info.argtypes = [POINTER(_AvInfo)]
        lib.retro_get_system_av_info.restype = None
        lib.retro_load_game.argtypes = [POINTER(_GameInfo)]
        lib.retro_load_game.restype = c_bool
        lib.retro_unload_game.restype = None
        lib.retro_run.restype = None
        try:
            lib.retro_set_controller_port_device.argtypes = [c_uint, c_uint]
            lib.retro_set_controller_port_device.restype = None
        except Exception:
            pass

        lib.retro_set_environment(self._env_cb)
        lib.retro_set_video_refresh(self._video_cb)
        lib.retro_set_audio_sample(self._audio_cb)
        lib.retro_set_audio_sample_batch(self._audio_batch_cb)
        lib.retro_set_input_poll(self._poll_cb)
        lib.retro_set_input_state(self._input_cb)
        lib.retro_init()

        info = _SystemInfo()
        lib.retro_get_system_info(byref(info))
        need_path = bool(info.need_fullpath)

        self._rom_path_p = c_char_p(str(self.rom).encode("utf-8"))
        self._c_keep.append(self._rom_path_p)
        raw = b""
        try:
            raw = self.rom.read_bytes()
        except OSError as e:
            raise RuntimeError(f"could not read ROM ({e})") from e
        if not raw:
            raise RuntimeError("ROM file is empty")
        # Binary buffer — do NOT use create_string_buffer(bytes, len)
        # (that requires size >= len+1 and can truncate/raise).
        self._rom_buf = (ctypes.c_char * len(raw)).from_buffer_copy(raw)
        self._c_keep.append(self._rom_buf)

        lib.retro_load_game.restype = c_bool
        attempts: List[Tuple[str, bool]] = []
        if need_path:
            attempts.append(("path", False))
            attempts.append(("data", True))
        else:
            attempts.append(("data", True))
            attempts.append(("path", False))
        last_mode = attempts[0][0]
        loaded = False
        tried = False
        for mode, with_data in attempts:
            last_mode = mode
            game = _GameInfo()
            game.path = self._rom_path_p
            game.meta = None
            if with_data:
                game.data = ctypes.cast(self._rom_buf, c_void_p)
                game.size = len(raw)
            else:
                game.data = None
                game.size = 0
            if tried:
                try:
                    lib.retro_unload_game()
                except Exception:
                    pass
            tried = True
            if lib.retro_load_game(byref(game)):
                loaded = True
                break
        if not loaded:
            raise RuntimeError(
                f"core rejected ROM ({self.so_path.name}, last={last_mode})"
            )

        av = _AvInfo()
        lib.retro_get_system_av_info(byref(av))
        self._apply_av(av)
        try:
            lib.retro_set_controller_port_device(0, RETRO_DEVICE_JOYPAD)
        except Exception:
            pass
        self._load_sram()
        self._alive = True

    def run_frame(self) -> Tuple[Optional[bytes], int, int, int, int]:
        """Advance one frame. Returns (raw, w, h, pix_fmt, pitch)."""
        self._got_frame = False
        self._lib.retro_run()
        if not self._got_frame:
            return None, self.width, self.height, self._pix_fmt, self._pitch
        return self._raw, self.width, self.height, self._pix_fmt, self._pitch

    def take_audio(self) -> bytes:
        if not self._audio:
            return b""
        out = bytes(self._audio)
        self._audio.clear()
        return out

    def close(self) -> None:
        if self._lib is None:
            return
        try:
            if self._alive:
                self._save_sram()
        except Exception:
            pass
        try:
            self._lib.retro_unload_game()
        except Exception:
            pass
        try:
            self._lib.retro_deinit()
        except Exception:
            pass
        self._alive = False
        self._lib = None

    def _srm_path(self) -> Path:
        return self.save_dir / (self.rom.stem + ".srm")

    def _mem(self, which: int):
        lib = self._lib
        lib.retro_get_memory_data.restype = c_void_p
        lib.retro_get_memory_size.restype = c_size_t
        ptr = lib.retro_get_memory_data(which)
        sz = int(lib.retro_get_memory_size(which) or 0)
        return ptr, sz

    def _load_sram(self) -> None:
        path = self._srm_path()
        if not path.is_file():
            return
        ptr, sz = self._mem(RETRO_MEMORY_SAVE_RAM)
        if not ptr or sz <= 0:
            return
        raw = path.read_bytes()[:sz]
        memmove(ptr, raw, len(raw))

    def _save_sram(self) -> None:
        ptr, sz = self._mem(RETRO_MEMORY_SAVE_RAM)
        if not ptr or sz <= 0:
            return
        self._srm_path().write_bytes(string_at(ptr, sz))

    def _apply_av(self, av: _AvInfo) -> None:
        w = int(av.geometry.base_width or 0)
        h = int(av.geometry.base_height or 0)
        if w > 0 and h > 0:
            self.width, self.height = w, h
        if av.timing.fps and av.timing.fps > 1:
            self.fps = float(av.timing.fps)
        if av.timing.sample_rate and av.timing.sample_rate > 1000:
            self.sample_rate = float(av.timing.sample_rate)

    def _env(self, cmd: int, data) -> bool:
        if not data and cmd not in (
            RETRO_ENVIRONMENT_SET_SUPPORT_NO_GAME,
            RETRO_ENVIRONMENT_GET_VARIABLE_UPDATE,
            RETRO_ENVIRONMENT_GET_INPUT_BITMASKS,
            RETRO_ENVIRONMENT_GET_FASTFORWARDING,
        ):
            return False
        try:
            return self._env_inner(cmd, data)
        except Exception:
            return False

    def _env_inner(self, cmd: int, data) -> bool:
        if cmd == RETRO_ENVIRONMENT_GET_CAN_DUPE:
            if data:
                cast(data, POINTER(c_bool))[0] = True
            return True
        if cmd == RETRO_ENVIRONMENT_GET_OVERSCAN:
            if data:
                cast(data, POINTER(c_bool))[0] = False
            return True
        if cmd == RETRO_ENVIRONMENT_SET_PIXEL_FORMAT:
            fmt = cast(data, POINTER(c_int))[0]
            if fmt in (
                RETRO_PIXEL_FORMAT_0RGB1555,
                RETRO_PIXEL_FORMAT_XRGB8888,
                RETRO_PIXEL_FORMAT_RGB565,
            ):
                self._pix_fmt = int(fmt)
                return True
            return False
        if cmd in (
            RETRO_ENVIRONMENT_GET_SYSTEM_DIRECTORY,
            RETRO_ENVIRONMENT_GET_CORE_ASSETS_DIRECTORY,
        ):
            cast(data, POINTER(c_char_p))[0] = self._sys_dir_p
            return True
        if cmd == RETRO_ENVIRONMENT_GET_SAVE_DIRECTORY:
            cast(data, POINTER(c_char_p))[0] = self._save_dir_p
            return True
        if cmd == RETRO_ENVIRONMENT_GET_VARIABLE:
            if not data:
                return False
            var = cast(data, POINTER(_Variable)).contents
            raw_key = var.key
            if isinstance(raw_key, bytes):
                key = raw_key.decode("utf-8", "replace")
            else:
                key = raw_key or ""
            val = self._vars.get(key)
            if not val:
                var.value = None
                return True
            buf = self._var_bufs.get(key)
            if buf is None:
                buf = c_char_p(val.encode("utf-8"))
                self._var_bufs[key] = buf
                self._c_keep.append(buf)
            var.value = buf
            return True
        if cmd == RETRO_ENVIRONMENT_SET_VARIABLES:
            self._ingest_variables(data)
            return True
        if cmd == RETRO_ENVIRONMENT_GET_VARIABLE_UPDATE:
            if data:
                cast(data, POINTER(c_bool))[0] = False
            return True
        if cmd == RETRO_ENVIRONMENT_GET_CORE_OPTIONS_VERSION:
            # Force legacy SET_VARIABLES — simpler and widely supported
            return False
        if cmd == RETRO_ENVIRONMENT_GET_LANGUAGE:
            if data:
                cast(data, POINTER(c_uint))[0] = 0
            return True
        if cmd == RETRO_ENVIRONMENT_GET_AUDIO_VIDEO_ENABLE:
            if data:
                cast(data, POINTER(c_int))[0] = 1 | 2
            return True
        if cmd == RETRO_ENVIRONMENT_GET_FASTFORWARDING:
            if data:
                cast(data, POINTER(c_bool))[0] = False
            return True
        if cmd == RETRO_ENVIRONMENT_SET_GEOMETRY:
            geom = cast(data, POINTER(_Geometry))[0]
            if geom.base_width and geom.base_height:
                self.width = int(geom.base_width)
                self.height = int(geom.base_height)
            return True
        if cmd == RETRO_ENVIRONMENT_SET_SYSTEM_AV_INFO:
            self._apply_av(cast(data, POINTER(_AvInfo))[0])
            return True
        if cmd in (
            RETRO_ENVIRONMENT_SET_INPUT_DESCRIPTORS,
            RETRO_ENVIRONMENT_SET_CONTROLLER_INFO,
            RETRO_ENVIRONMENT_SET_MEMORY_MAPS,
            RETRO_ENVIRONMENT_SET_PERFORMANCE_LEVEL,
            RETRO_ENVIRONMENT_SET_SUPPORT_ACHIEVEMENTS,
            RETRO_ENVIRONMENT_SET_SERIALIZATION_QUIRKS,
            RETRO_ENVIRONMENT_SET_SUBSYSTEM_INFO,
            RETRO_ENVIRONMENT_SET_MESSAGE,
            RETRO_ENVIRONMENT_SET_CORE_OPTIONS_DISPLAY,
            RETRO_ENVIRONMENT_SET_MINIMUM_AUDIO_LATENCY,
            RETRO_ENVIRONMENT_SET_SUPPORT_NO_GAME,
        ):
            return True
        if cmd == RETRO_ENVIRONMENT_GET_INPUT_BITMASKS:
            return True
        if cmd in (
            RETRO_ENVIRONMENT_GET_LOG_INTERFACE,
            RETRO_ENVIRONMENT_SET_KEYBOARD_CALLBACK,
            RETRO_ENVIRONMENT_SET_CORE_OPTIONS,
            RETRO_ENVIRONMENT_SET_CORE_OPTIONS_INTL,
            RETRO_ENVIRONMENT_SET_CORE_OPTIONS_V2,
            RETRO_ENVIRONMENT_SET_CORE_OPTIONS_V2_INTL,
            RETRO_ENVIRONMENT_GET_GAME_INFO_EXT,
            RETRO_ENVIRONMENT_GET_USERNAME,
            RETRO_ENVIRONMENT_SET_CONTENT_INFO_OVERRIDE,
        ):
            return False
        # Optional callbacks many cores probe — ignore safely.
        if cmd >= 70:
            return True
        return False

    def _ingest_variables(self, data) -> None:
        if not data:
            return
        ptr = cast(data, POINTER(_Variable))
        i = 0
        while True:
            v = ptr[i]
            if not v.key:
                break
            raw_k = v.key.decode("utf-8", "replace") if isinstance(v.key, bytes) else (v.key or "")
            raw_v = v.value
            if isinstance(raw_v, bytes):
                desc = raw_v.decode("utf-8", "replace")
            else:
                desc = raw_v or ""
            default = ""
            if ";" in desc:
                opts = desc.split(";", 1)[1]
                default = opts.split("|", 1)[0].strip()
            if raw_k not in self._vars and default:
                self._vars[raw_k] = default
            i += 1
            if i > 400:
                break

    def _video(self, data, width: int, height: int, pitch: int) -> None:
        try:
            if not data or width <= 0 or height <= 0:
                return
            w, h, p = int(width), int(height), int(pitch)
            if w > 1024 or h > 1024 or p <= 0 or p > 8192:
                return
            nbytes = p * h
            if nbytes <= 0 or nbytes > 8_000_000:
                return
            self.width = w
            self.height = h
            self._pitch = p
            self._raw = string_at(data, nbytes)
            self._got_frame = True
        except Exception:
            return

    def _audio_sample(self, left: int, right: int) -> None:
        try:
            self._audio += int(left).to_bytes(2, "little", signed=True)
            self._audio += int(right).to_bytes(2, "little", signed=True)
        except Exception:
            return

    def _audio_batch(self, data, frames: int) -> int:
        try:
            n = int(frames)
            if n <= 0 or not data or n > 8192:
                return 0
            self._audio += string_at(data, n * 4)
            return n
        except Exception:
            return 0

    def _poll(self) -> None:
        return

    def _input(self, port: int, device: int, index: int, ident: int) -> int:
        if port != 0 or device != RETRO_DEVICE_JOYPAD:
            return 0
        held = self._held
        if ident == RETRO_DEVICE_ID_JOYPAD_MASK:
            mask = 0
            for name, bid in BTN_IDS.items():
                if name in held:
                    mask |= 1 << bid
            return mask
        for name, bid in BTN_IDS.items():
            if bid == ident and name in held:
                return 1
        return 0


def raw_to_rgb888(raw: bytes, w: int, h: int, pitch: int, pix_fmt: int):
    """Return contiguous HxWx3 uint8 array (numpy) or None."""
    try:
        import numpy as np
    except ImportError:
        return None
    if not raw or w <= 0 or h <= 0:
        return None
    if pix_fmt == RETRO_PIXEL_FORMAT_XRGB8888:
        row = max(pitch, w * 4)
        arr = np.frombuffer(raw, dtype=np.uint8)
        if arr.size < h * row:
            return None
        bgra = arr.reshape(h, row)[:, : w * 4].reshape(h, w, 4)
        return np.ascontiguousarray(bgra[:, :, [2, 1, 0]])
    # 16-bit packed
    bpp = 2
    row_px = max(pitch // bpp, w)
    arr = np.frombuffer(raw, dtype=np.uint16)
    need = h * row_px
    if arr.size < need:
        return None
    pix = arr[:need].reshape(h, row_px)[:, :w]
    if pix_fmt == RETRO_PIXEL_FORMAT_RGB565:
        r = ((pix >> 11) & 0x1F) << 3
        g = ((pix >> 5) & 0x3F) << 2
        b = (pix & 0x1F) << 3
    else:
        r = ((pix >> 10) & 0x1F) << 3
        g = ((pix >> 5) & 0x1F) << 3
        b = (pix & 0x1F) << 3
    return np.dstack((r.astype(np.uint8), g.astype(np.uint8), b.astype(np.uint8)))
