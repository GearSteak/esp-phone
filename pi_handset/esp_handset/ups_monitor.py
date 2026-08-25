"""Waveshare UPS Module 3S — INA219 pack telemetry on I2C @ 0x41."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Optional, Tuple

# INA219 registers
_REG_CONFIG = 0x00
_REG_BUS_V = 0x02
_REG_CURRENT = 0x04
_REG_POWER = 0x03
_REG_CALIB = 0x05

_ADDR = int(os.environ.get("DIGIVICE_UPS_I2C_ADDR", "0x41"), 0)
_BUS = int(os.environ.get("DIGIVICE_UPS_I2C_BUS", "1"))

# 3S Li-ion approximate range (calibrate on bench)
_V_MIN = float(os.environ.get("DIGIVICE_UPS_V_MIN", "9.0"))
_V_MAX = float(os.environ.get("DIGIVICE_UPS_V_MAX", "12.6"))
# Negative current = discharging (INA219 sign depends on shunt orientation)
_CHARGE_MA = float(os.environ.get("DIGIVICE_UPS_CHARGE_MA", "50"))

_CACHE: Optional["UpsReading"] = None
_CACHE_AT = 0.0
_CACHE_TTL = float(os.environ.get("DIGIVICE_UPS_POLL_S", "30"))


@dataclass(frozen=True)
class UpsReading:
    bus_voltage_v: float
    current_ma: float
    power_mw: float
    percent: int
    charging: bool
    present: bool = True


def _open_bus():
    try:
        from smbus2 import SMBus  # type: ignore

        return SMBus(_BUS)
    except ImportError:
        import smbus  # type: ignore

        return smbus.SMBus(_BUS)


def _read_u16(bus, reg: int) -> int:
    raw = bus.read_i2c_block_data(_ADDR, reg, 2)
    return (raw[0] << 8) | raw[1]


def _write_u16(bus, reg: int, val: int) -> None:
    bus.write_i2c_block_data(_ADDR, reg, [(val >> 8) & 0xFF, val & 0xFF])


def _init_ina219(bus) -> None:
    # 32V range, ±320mV, 12-bit, continuous shunt+bus (Waveshare default class)
    _write_u16(bus, _REG_CONFIG, 0x019F)
    # Cal for ~0.1 ohm shunt, 1mA LSB — close enough for UI %
    _write_u16(bus, _REG_CALIB, 4096)


def _voltage_v(bus) -> float:
    raw = _read_u16(bus, _REG_BUS_V)
    return (raw >> 3) * 0.004


def _current_ma(bus) -> float:
    raw = _read_u16(bus, _REG_CURRENT)
    if raw & 0x8000:
        raw -= 0x10000
    # With cal=4096 → 0.1mA per LSB (typical Waveshare demo)
    return raw * 0.1


def _power_mw(bus) -> float:
    raw = _read_u16(bus, _REG_POWER)
    return raw * 2.0


def _percent_from_voltage(v: float) -> int:
    if v <= 0:
        return 0
    pct = (v - _V_MIN) / max(0.01, _V_MAX - _V_MIN) * 100.0
    return max(0, min(100, int(round(pct))))


def read(*, force: bool = False) -> UpsReading:
    global _CACHE, _CACHE_AT
    now = time.monotonic()
    if not force and _CACHE is not None and (now - _CACHE_AT) < _CACHE_TTL:
        return _CACHE

    try:
        bus = _open_bus()
        try:
            _init_ina219(bus)
            v = _voltage_v(bus)
            ma = _current_ma(bus)
            mw = _power_mw(bus)
        finally:
            try:
                bus.close()
            except Exception:
                pass
        charging = ma > _CHARGE_MA
        pct = _percent_from_voltage(v)
        _CACHE = UpsReading(
            bus_voltage_v=v,
            current_ma=ma,
            power_mw=mw,
            percent=pct,
            charging=charging,
            present=True,
        )
    except OSError:
        _CACHE = UpsReading(
            bus_voltage_v=0.0,
            current_ma=0.0,
            power_mw=0.0,
            percent=-1,
            charging=False,
            present=False,
        )
    _CACHE_AT = now
    return _CACHE


def status_tuple() -> Tuple[int, bool, float]:
    """percent, charging, voltage_v — for status bar."""
    r = read()
    return r.percent, r.charging, r.bus_voltage_v
