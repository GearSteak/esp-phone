"""Digivice Weather — auto location via GPS, Wi‑Fi APs, or IP, then Open-Meteo."""
from __future__ import annotations

import json
import subprocess
import urllib.parse
import urllib.request
from typing import Callable, List, Optional

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget

from esp_handset import store
from esp_handset.pages import page_chrome

_WMO = {
    0: "Clear",
    1: "Mainly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Fog",
    48: "Rime fog",
    51: "Light drizzle",
    53: "Drizzle",
    55: "Heavy drizzle",
    61: "Light rain",
    63: "Rain",
    65: "Heavy rain",
    71: "Light snow",
    73: "Snow",
    75: "Heavy snow",
    80: "Rain showers",
    81: "Rain showers",
    82: "Heavy showers",
    95: "Thunderstorm",
}


def _http_json(url: str, *, data: Optional[bytes] = None, timeout: float = 10.0) -> dict:
    req = urllib.request.Request(
        url,
        data=data,
        headers={"User-Agent": "DigiviceWeather/1.0", "Accept": "application/json"},
        method="POST" if data is not None else "GET",
    )
    if data is not None:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def _wifi_aps() -> List[dict]:
    """Scan nearby Wi‑Fi APs for Mozilla Location Service."""
    aps: List[dict] = []
    try:
        r = subprocess.run(
            [
                "nmcli",
                "-t",
                "-f",
                "BSSID,SIGNAL",
                "device",
                "wifi",
                "list",
                "--rescan",
                "yes",
            ],
            capture_output=True,
            text=True,
            timeout=12,
            check=False,
        )
        for line in (r.stdout or "").splitlines():
            try:
                mac_part, sig = line.rsplit(":", 1)
                mac = mac_part.replace("\\:", ":").strip()
                signal = int(sig.strip())
            except Exception:
                continue
            if len(mac) < 11:
                continue
            dbm = max(-95, min(-30, signal - 100))
            aps.append({"macAddress": mac.upper(), "signalStrength": dbm})
    except Exception:
        pass
    best: dict = {}
    for ap in aps:
        mac = ap["macAddress"]
        if mac not in best or ap["signalStrength"] > best[mac]["signalStrength"]:
            best[mac] = ap
    return list(best.values())[:20]


def _locate_wifi_mls() -> Optional[dict]:
    aps = _wifi_aps()
    if len(aps) < 2:
        return None
    body = json.dumps({"wifiAccessPoints": aps}).encode()
    url = "https://location.services.mozilla.com/v1/geolocate?key=geoclue"
    try:
        data = _http_json(url, data=body, timeout=12)
        loc = data.get("location") or {}
        la, lo = loc.get("lat"), loc.get("lng")
        if la is None or lo is None:
            return None
        return {
            "lat": float(la),
            "lon": float(lo),
            "label": "Wi‑Fi",
            "detail": f"{len(aps)} nearby APs",
        }
    except Exception:
        return None


def _locate_ip() -> Optional[dict]:
    endpoints = (
        ("https://ipapi.co/json/", ("latitude", "longitude", "city", "country_name")),
        (
            "https://reallyfreegeoip.org/json/",
            ("latitude", "longitude", "city", "country_name"),
        ),
        ("https://geo.kamero.ai/api/geo", ("latitude", "longitude", "city", "country")),
    )
    for url, keys in endpoints:
        try:
            data = _http_json(url, timeout=8)
            la, lo = data.get(keys[0]), data.get(keys[1])
            if la is None or lo is None:
                continue
            city = str(data.get(keys[2]) or "").strip()
            country = str(data.get(keys[3]) or "").strip()
            label = ", ".join(x for x in (city, country) if x)
            return {
                "lat": float(la),
                "lon": float(lo),
                "label": "Wi‑Fi / IP",
                "detail": label or "approx",
            }
        except Exception:
            continue
    return None


def _locate_gps(modem) -> Optional[dict]:
    if not modem:
        return None
    try:
        modem.gps_on()
        fix = modem.gps_fix()
    except Exception:
        return None
    if fix.get("ok") and fix.get("lat") is not None and fix.get("lon") is not None:
        return {
            "lat": float(fix["lat"]),
            "lon": float(fix["lon"]),
            "label": "GPS",
            "detail": str(fix.get("summary") or "fix"),
        }
    return None


def make_weather_page(on_back: Callable[[], None], modem=None) -> QWidget:
    del on_back
    body = QWidget()
    lay = QVBoxLayout(body)
    lay.setSpacing(6)
    lay.setContentsMargins(6, 4, 6, 4)

    saved = store.load("weather.json", {}) or {}
    place = QLabel("")
    place.setAlignment(Qt.AlignCenter)
    place.setWordWrap(True)
    place.setStyleSheet(
        "font-size:12px; font-weight:700; color:#e8f0ff;"
        " background:#152030; border-radius:10px; padding:8px;"
    )
    out = QLabel("Finding location…")
    out.setAlignment(Qt.AlignCenter)
    out.setWordWrap(True)
    out.setStyleSheet("font-size:18px; font-weight:700; color:#cde;")
    detail = QLabel("GPS → Wi‑Fi APs → IP")
    detail.setAlignment(Qt.AlignCenter)
    detail.setWordWrap(True)
    detail.setStyleSheet("font-size:10px; color:#9ab;")
    refresh = QPushButton("Update weather")
    refresh.setMinimumHeight(36)
    refresh.setStyleSheet("font-size:13px; font-weight:700;")
    lay.addWidget(place)
    lay.addStretch(1)
    lay.addWidget(out)
    lay.addWidget(detail)
    lay.addStretch(1)
    lay.addWidget(refresh)

    state = {
        "lat": saved.get("lat"),
        "lon": saved.get("lon"),
        "source": saved.get("source") or "",
        "place": saved.get("place") or "",
        "busy": False,
    }

    def _show_place() -> None:
        src = state.get("source") or "?"
        pl = state.get("place") or ""
        la, lo = state.get("lat"), state.get("lon")
        if la is not None and lo is not None:
            coord = f"{float(la):.3f}, {float(lo):.3f}"
            place.setText(f"{pl}\n{src} · {coord}" if pl else f"{src}\n{coord}")
        else:
            place.setText("No location yet")

    def _persist(loc: dict) -> None:
        state["lat"] = loc["lat"]
        state["lon"] = loc["lon"]
        state["source"] = loc.get("label") or ""
        state["place"] = loc.get("detail") or ""
        store.save(
            "weather.json",
            {
                "lat": round(float(loc["lat"]), 5),
                "lon": round(float(loc["lon"]), 5),
                "source": state["source"],
                "place": state["place"],
            },
        )
        _show_place()

    def _fetch_forecast(la: float, lo: float) -> None:
        url = (
            "https://api.open-meteo.com/v1/forecast?"
            + urllib.parse.urlencode(
                {
                    "latitude": la,
                    "longitude": lo,
                    "current_weather": "true",
                }
            )
        )
        with urllib.request.urlopen(url, timeout=10) as resp:
            data = json.loads(resp.read().decode())
        cw = data.get("current_weather") or {}
        code = cw.get("weathercode")
        try:
            code_i = int(code)
        except (TypeError, ValueError):
            code_i = -1
        desc = _WMO.get(code_i, f"Code {code}")
        out.setText(f"{desc}\n{cw.get('temperature')}°C")
        detail.setText(f"Wind {cw.get('windspeed')} km/h · {cw.get('time') or ''}")

    def _pump() -> None:
        try:
            from PyQt5.QtWidgets import QApplication

            QApplication.processEvents()
        except Exception:
            pass

    def do_update() -> None:
        if state["busy"]:
            return
        state["busy"] = True
        refresh.setEnabled(False)
        out.setText("Locating…")
        detail.setText("GPS → Wi‑Fi → IP")
        _pump()

        loc = None
        notes: List[str] = []
        loc = _locate_gps(modem)
        if loc:
            notes.append("GPS")
        else:
            notes.append("no GPS")
            out.setText("Scanning Wi‑Fi…")
            _pump()
            loc = _locate_wifi_mls()
            if loc:
                notes.append("Wi‑Fi")
            else:
                notes.append("no Wi‑Fi fix")
                out.setText("IP lookup…")
                _pump()
                loc = _locate_ip()
                if loc:
                    notes.append("IP")
                else:
                    notes.append("no IP")

        try:
            if not loc:
                if state.get("lat") is not None and state.get("lon") is not None:
                    loc = {
                        "lat": float(state["lat"]),
                        "lon": float(state["lon"]),
                        "label": state.get("source") or "Saved",
                        "detail": state.get("place") or "last known",
                    }
                    notes.append("saved")
                else:
                    out.setText("Couldn't find you")
                    detail.setText(" · ".join(notes) + "\nEnable GPS or Wi‑Fi")
                    return
            _persist(loc)
            out.setText("Fetching…")
            _pump()
            _fetch_forecast(float(loc["lat"]), float(loc["lon"]))
            trail = " · ".join(notes)
            if trail:
                detail.setText(detail.text() + f"\n{trail}")
        except Exception as e:
            out.setText("Weather failed")
            detail.setText(str(e)[:90])
        finally:
            state["busy"] = False
            refresh.setEnabled(True)

    refresh.clicked.connect(do_update)
    _show_place()
    if state.get("lat") is not None:
        out.setText("Tap Update")
    QTimer.singleShot(350, do_update)
    return page_chrome("Weather", body, None, scroll=False)
