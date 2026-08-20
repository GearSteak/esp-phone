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
VIDEOS_DIR = Path.home() / "Videos" / "phone"


def photos_dir() -> Path:
    PHOTOS.mkdir(parents=True, exist_ok=True)
    return PHOTOS


def videos_dir() -> Path:
    VIDEOS_DIR.mkdir(parents=True, exist_ok=True)
    return VIDEOS_DIR


def _stamp(prefix: str, ext: str = "jpg") -> Path:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    folder = videos_dir() if ext.lower() in ("mp4", "h264", "mkv") else photos_dir()
    return folder / f"{prefix}_{ts}.{ext.lstrip('.')}"


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
        list(d.glob("*.jpg"))
        + list(d.glob("*.jpeg"))
        + list(d.glob("*.png"))
        + list(videos_dir().glob("*.mp4")),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return files[:limit]


def stitch_panorama(frames: list[Path], *, out: Optional[Path] = None) -> Path:
    """Join stills side-by-side (simple horizontal pano)."""
    if len(frames) < 2:
        raise RuntimeError("Need at least 2 frames for a panorama")
    try:
        from PIL import Image  # type: ignore
    except ImportError as e:
        raise RuntimeError("Install python3-pil for panoramas") from e
    imgs = [Image.open(p).convert("RGB") for p in frames]
    h = min(im.height for im in imgs)
    scaled = []
    for im in imgs:
        w = max(1, int(im.width * h / im.height))
        scaled.append(im.resize((w, h), Image.LANCZOS))
    total_w = sum(im.width for im in scaled)
    pano = Image.new("RGB", (total_w, h))
    x = 0
    for im in scaled:
        pano.paste(im, (x, 0))
        x += im.width
    dest = out or _stamp("pano")
    pano.save(str(dest), quality=90)
    return dest


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
        self._recording = False
        self._record_path: Optional[Path] = None
        self._encoder = None
        self._record_output = None

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

    @property
    def recording(self) -> bool:
        return bool(self._recording)

    def start_recording(self, path: Optional[Path] = None) -> Path:
        """Start H.264 video while preview runs."""
        if self._recording:
            raise RuntimeError("Already recording")
        out = path or _stamp("video", "mp4")
        with self._lock:
            picam = self._picam
            if picam is None:
                raise RuntimeError("Preview not running")
            try:
                from picamera2.encoders import H264Encoder  # type: ignore
                from picamera2.outputs import FileOutput  # type: ignore
            except ImportError as e:
                raise RuntimeError("picamera2 encoder missing for video") from e
            self._encoder = H264Encoder()
            self._record_output = FileOutput(str(out))
            picam.start_recording(self._encoder, self._record_output)
            self._recording = True
            self._record_path = out
        return out

    def stop_recording(self) -> Optional[Path]:
        with self._lock:
            picam = self._picam
            path = self._record_path
            if not self._recording or picam is None:
                return None
            try:
                picam.stop_recording()
            except Exception:
                pass
            self._recording = False
            self._encoder = None
            self._record_output = None
            self._record_path = None
        if path and path.exists():
            return path
        return path

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
        with self._lock:
            if self._recording and self._picam is not None:
                try:
                    self._picam.stop_recording()
                except Exception:
                    pass
            self._recording = False
            self._encoder = None
            self._record_output = None
            self._record_path = None
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
