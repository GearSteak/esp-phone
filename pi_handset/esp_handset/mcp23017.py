"""SeenGreat MCP23017 E017 — 14-button pad + torch/vibe outputs @ I2C 0x20."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Dict, Optional, Tuple

_ADDR = int(os.environ.get("DIGIVICE_MCP_ADDR", "0x20"), 0)
_BUS = int(os.environ.get("DIGIVICE_MCP_I2C_BUS", "1"))

# MCP23017 registers
_IODIRA = 0x00
_IODIRB = 0x01
_GPPUA = 0x0C
_GPPUB = 0x0D
_GPIOA = 0x12
_GPIOB = 0x13
_OLATA = 0x14
_OLATB = 0x15

# Inputs: GPA0-7 dpad + face, GPB0-5 shoulders + start/select
# Outputs: GPB6 torch, GPB7 vibe (active high → MOSFET driver)
_INPUT_MASK_A = 0xFF
_INPUT_MASK_B = 0x3F  # GPB0-5 inputs; 6-7 outputs
_OUTPUT_MASK_B = 0xC0

# Logical names → (port, bit)  port 0=A 1=B
_PIN_MAP: Dict[str, Tuple[int, int]] = {
    "UP": (0, 0),
    "DOWN": (0, 1),
    "LEFT": (0, 2),
    "RIGHT": (0, 3),
    "A": (0, 4),
    "B": (0, 5),
    "X": (0, 6),
    "Y": (0, 7),
    "L": (1, 0),
    "R": (1, 1),
    "L2": (1, 2),
    "R2": (1, 3),
    "START": (1, 4),
    "SELECT": (1, 5),
}

# Phone-mode aliases (8-button Digivice nav)
_PHONE_MAP = {
    "UP": "UP",
    "DOWN": "DOWN",
    "LEFT": "LEFT",
    "RIGHT": "RIGHT",
    "CONFIRM": "A",
    "BACK": "B",
    "HOME": "START",
    "SELECT": "SELECT",
}

_OUTPUTS = {
    "TORCH": (1, 6),
    "VIBE": (1, 7),
}


@dataclass
class McpState:
    raw_a: int
    raw_b: int
    pressed: Dict[str, bool]


def _open_bus():
    try:
        from smbus2 import SMBus  # type: ignore

        return SMBus(_BUS)
    except ImportError:
        import smbus  # type: ignore

        return smbus.SMBus(_BUS)


def _write(bus, reg: int, val: int) -> None:
    bus.write_byte_data(_ADDR, reg, val & 0xFF)


def _read(bus, reg: int) -> int:
    return bus.read_byte_data(_ADDR, reg) & 0xFF


def init(bus=None) -> bool:
    """Configure MCP: inputs with pull-ups; GPB6/7 outputs low."""
    own = bus is None
    if own:
        try:
            bus = _open_bus()
        except OSError:
            return False
    try:
        _write(bus, _IODIRA, _INPUT_MASK_A)
        _write(bus, _IODIRB, _INPUT_MASK_B | _OUTPUT_MASK_B)
        _write(bus, _GPPUA, _INPUT_MASK_A)
        _write(bus, _GPPUB, _INPUT_MASK_B)
        _write(bus, _OLATB, 0x00)
        return True
    except OSError:
        return False
    finally:
        if own and bus is not None:
            try:
                bus.close()
            except Exception:
                pass


def _pressed_from_ports(a: int, b: int) -> Dict[str, bool]:
    out: Dict[str, bool] = {}
    for name, (port, bit) in _PIN_MAP.items():
        val = a if port == 0 else b
        # Active low (button to GND)
        out[name] = not bool(val & (1 << bit))
    return out


def read_state() -> Optional[McpState]:
    try:
        bus = _open_bus()
        try:
            if not init(bus):
                return None
            a = _read(bus, _GPIOA)
            b = _read(bus, _GPIOB)
        finally:
            try:
                bus.close()
            except Exception:
                pass
        return McpState(raw_a=a, raw_b=b, pressed=_pressed_from_ports(a, b))
    except OSError:
        return None


def read_phone_buttons() -> Dict[str, bool]:
    """Map to Digivice 8-button names for buttons_inputd."""
    st = read_state()
    if st is None:
        return {}
    out: Dict[str, bool] = {}
    for phone, logical in _PHONE_MAP.items():
        out[phone] = st.pressed.get(logical, False)
    return out


def set_output(name: str, on: bool) -> bool:
    port_bit = _OUTPUTS.get(name.upper())
    if port_bit is None:
        return False
    port, bit = port_bit
    if port != 1:
        return False
    try:
        bus = _open_bus()
        try:
            if not init(bus):
                return False
            olat = _read(bus, _OLATB)
            if on:
                olat |= 1 << bit
            else:
                olat &= ~(1 << bit)
            _write(bus, _OLATB, olat)
            return True
        finally:
            try:
                bus.close()
            except Exception:
                pass
    except OSError:
        return False


def present() -> bool:
    try:
        bus = _open_bus()
        try:
            bus.read_byte_data(_ADDR, _GPIOA)
            return True
        finally:
            try:
                bus.close()
            except Exception:
                pass
    except OSError:
        return False


def backend_enabled() -> bool:
    env = os.environ.get("DIGI_BTN_BACKEND", "").strip().lower()
    if env == "mcp":
        return True
    if env == "gpio":
        return False
    for path in ("/etc/esp-handset/buttons-backend",):
        try:
            t = open(path, encoding="utf-8").read().strip().lower()
            if t == "mcp":
                return True
            if t == "gpio":
                return False
        except OSError:
            pass
    return present()
