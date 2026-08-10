"""Rear camera capture + live preview via Raspberry Pi CSI (libcamera / picamera2)."""

from __future__ import annotations

import shutil
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

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
    then picamera2. Prefer LivePreview.capture_still() while preview is active.
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
            "Enable CSI camera and: sudo apt install -y rpicam-apps python3-picamera2"
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


def list_photos(limit: int = 200) -> list[Path]:
    d = photos_dir()
    files = sorted(
        list(d.glob("*.jpg")) + list(d.glob("*.jpeg")) + list(d.glob("*.png")),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return files[:limit]


class LivePreview:
    """Continuous low-res preview for Digivice (picamera2 preferred).

    on_frame(rgb_bytes, width, height) is called on the worker thread —
    marshal to UI with a Qt signal or queue.
    """

    def __init__(
        self,
        *,
        width: int = 320,
        height: int = 240,
        fps: float = 8.0,
    ) -> None:
        self.width = width
        self.height = height
        self.fps = max(2.0, min(15.0, fps))
        self._lock = threading.Lock()
        self._picam = None
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._on_frame: Optional[Callable[[bytes, int, int], None]] = None
        self._on_error: Optional[Callable[[str], None]] = None
        self._still_busy = False

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(
        self,
        on_frame: Callable[[bytes, int, int], None],
        on_error: Optional[Callable[[str], None]] = None,
    ) -> bool:
        self.stop()
        self._on_frame = on_frame
        self._on_error = on_error
        self._stop.clear()
        try:
            from picamera2 import Picamera2
        except ImportError as e:
            msg = (
                "picamera2 missing for live preview. "
                "Install: sudo apt install -y python3-picamera2 rpicam-apps"
            )
            if on_error:
                on_error(msg)
            print(f"[camera] {msg}: {e}", flush=True)
            return False

        try:
            picam = Picamera2()
            cfg = picam.create_preview_configuration(
                main={"size": (self.width, self.height), "format": "RGB888"}
            )
            picam.configure(cfg)
            picam.start()
            time.sleep(0.15)
            self._picam = picam
        except Exception as e:
            msg = f"Camera open failed: {e}"
            if on_error:
                on_error(msg)
            print(f"[camera] {msg}", flush=True)
            return False

        self._thread = threading.Thread(target=self._loop, name="cam-preview", daemon=True)
        self._thread.start()
        return True

    def _loop(self) -> None:
        interval = 1.0 / self.fps
        while not self._stop.is_set():
            t0 = time.time()
            if self._still_busy:
                time.sleep(0.05)
                continue
            try:
                with self._lock:
                    picam = self._picam
                    if picam is None:
                        break
                    arr = picam.capture_array("main")
                if arr is None:
                    time.sleep(interval)
                    continue
                # ensure contiguous RGB
                h, w = int(arr.shape[0]), int(arr.shape[1])
                if arr.ndim == 3 and arr.shape[2] >= 3:
                    rgb = arr[:, :, :3].tobytes()
                else:
                    time.sleep(interval)
                    continue
                cb = self._on_frame
                if cb is not None:
                    cb(rgb, w, h)
            except Exception as e:
                if self._stop.is_set():
                    break
                err = self._on_error
                if err is not None:
                    err(str(e))
                time.sleep(0.3)
            elapsed = time.time() - t0
            time.sleep(max(0.0, interval - elapsed))

    def capture_still(self, width: int = 1280, height: int = 720) -> Path:
        """Snap a full still while preview is running (or cold capture)."""
        out = _stamp("rear")
        with self._lock:
            picam = self._picam
            if picam is None:
                return capture_rear(width, height)
            self._still_busy = True
            try:
                # Prefer file capture from current pipeline (quick, good enough)
                picam.capture_file(str(out))
            except Exception:
                # Fallback: stop-free array dump at preview res + save via Qt not available here
                try:
                    arr = picam.capture_array("main")
                    from PIL import Image  # type: ignore

                    Image.fromarray(arr[:, :, :3]).save(str(out), quality=90)
                except Exception as e:
                    self._still_busy = False
                    raise RuntimeError(f"still capture failed: {e}") from e
            finally:
                self._still_busy = False
        if not out.exists():
            raise RuntimeError("still capture produced no file")
        return out

    def stop(self) -> None:
        self._stop.set()
        t = self._thread
        if t is not None and t.is_alive():
            t.join(timeout=2.0)
        self._thread = None
        with self._lock:
            picam = self._picam
            self._picam = None
        if picam is not None:
            try:
                picam.stop()
            except Exception:
                pass
            try:
                picam.close()
            except Exception:
                pass
        self._on_frame = None
        self._on_error = None
        self._still_busy = False
