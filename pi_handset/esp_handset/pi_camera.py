"""Rear camera capture via Raspberry Pi CSI (libcamera / picamera2)."""

from __future__ import annotations

import shutil
import subprocess
import time
from datetime import datetime
from pathlib import Path

PHOTOS = Path.home() / "Pictures" / "phone"


def photos_dir() -> Path:
    PHOTOS.mkdir(parents=True, exist_ok=True)
    return PHOTOS


def _stamp(prefix: str) -> Path:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return photos_dir() / f"{prefix}_{ts}.jpg"


def capture_rear(width: int = 1280, height: int = 720) -> Path:
    """
    Capture from Pi Camera Module (CSI). Tries rpicam-still, then libcamera-still,
    then picamera2.
    """
    out = _stamp("rear")
    cmds = [
        [
            "rpicam-still",
            "-n",
            "-o",
            str(out),
            "--width",
            str(width),
            "--height",
            str(height),
            "-t",
            "300",
        ],
        [
            "libcamera-still",
            "-n",
            "-o",
            str(out),
            "--width",
            str(width),
            "--height",
            str(height),
            "-t",
            "300",
        ],
    ]
    for cmd in cmds:
        if shutil.which(cmd[0]):
            r = subprocess.run(cmd, capture_output=True, text=True)
            if r.returncode == 0 and out.exists():
                return out
            raise RuntimeError(
                f"{cmd[0]} failed: {r.stderr or r.stdout or r.returncode}"
            )

    try:
        from picamera2 import Picamera2
    except ImportError as e:
        raise RuntimeError(
            "No rpicam-still/libcamera-still and picamera2 not installed. "
            "Enable CSI camera and: sudo apt install -y rpicam-apps"
        ) from e

    picam = Picamera2()
    cfg = picam.create_still_configuration(
        main={"size": (width, height), "format": "RGB888"}
    )
    picam.configure(cfg)
    picam.start()
    time.sleep(0.4)
    picam.capture_file(str(out))
    picam.stop()
    picam.close()
    if not out.exists():
        raise RuntimeError("picamera2 capture produced no file")
    return out


def list_photos(limit: int = 40) -> list[Path]:
    d = photos_dir()
    files = sorted(d.glob("*.jpg"), key=lambda p: p.stat().st_mtime, reverse=True)
    return files[:limit]
