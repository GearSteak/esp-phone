"""Ollama chat — local LLM via Ollama HTTP API (installed by digivice-full-update).

Defaults:

  ESP_OLLAMA_HOST  (default http://127.0.0.1:11434)
  ESP_OLLAMA_MODEL (default llama3.2:1b)

Also: /etc/esp-handset/ollama.env  or  ~/.esp-handset/ollama.env
  OLLAMA_HOST=http://127.0.0.1:11434
  OLLAMA_MODEL=llama3.2:1b
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable, List, Optional, Tuple

from PyQt5.QtCore import QThread, pyqtSignal
from PyQt5.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from esp_handset.pages import page_chrome

_DATA = Path.home() / ".esp-handset"
_HISTORY = _DATA / "ollama_chat.json"


def _load_env_file(path: Path) -> None:
    if not path.is_file():
        return
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k, v = k.strip(), v.strip().strip('"').strip("'")
            if k and k not in os.environ:
                os.environ[k] = v
    except OSError:
        pass


def apply_config() -> Tuple[str, str]:
    _load_env_file(Path("/etc/esp-handset/ollama.env"))
    _load_env_file(_DATA / "ollama.env")
    cfg: dict = {}
    try:
        p = _DATA / "ollama.json"
        if p.is_file():
            cfg = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        cfg = {}
    host = (
        os.environ.get("ESP_OLLAMA_HOST")
        or os.environ.get("OLLAMA_HOST")
        or str(cfg.get("host") or "http://127.0.0.1:11434")
    ).rstrip("/")
    model = (
        os.environ.get("ESP_OLLAMA_MODEL")
        or os.environ.get("OLLAMA_MODEL")
        or str(cfg.get("model") or "llama3.2:1b")
    )
    return host, model


def _http_json(method: str, url: str, body: Optional[dict] = None, timeout: float = 120):
    data = None
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
        return json.loads(raw) if raw else {}


def ollama_reachable(host: str, timeout: float = 2.0) -> Tuple[bool, str]:
    try:
        _http_json("GET", f"{host}/api/tags", timeout=timeout)
        return True, "ok"
    except urllib.error.URLError as e:
        return False, str(e.reason if hasattr(e, "reason") else e)
    except Exception as e:
        return False, str(e)


def list_models(host: str) -> List[str]:
    try:
        data = _http_json("GET", f"{host}/api/tags", timeout=5)
        return [m.get("name", "") for m in data.get("models", []) if m.get("name")]
    except Exception:
        return []


def chat(host: str, model: str, messages: List[dict], timeout: float = 180) -> str:
    """Non-streaming /api/chat."""
    data = _http_json(
        "POST",
        f"{host}/api/chat",
        body={"model": model, "messages": messages, "stream": False},
        timeout=timeout,
    )
    msg = data.get("message") or {}
    content = (msg.get("content") or "").strip()
    if content:
        return content
    # some older responses
    return (data.get("response") or data.get("error") or "(empty reply)").strip()


class _ChatWorker(QThread):
    done = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, host: str, model: str, messages: List[dict], parent=None):
        super().__init__(parent)
        self._host = host
        self._model = model
        self._messages = messages

    def run(self) -> None:
        try:
            text = chat(self._host, self._model, self._messages)
            self.done.emit(text)
        except Exception as e:
            self.failed.emit(str(e))


def _load_history() -> List[dict]:
    if not _HISTORY.exists():
        return []
    try:
        data = json.loads(_HISTORY.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return [m for m in data if isinstance(m, dict) and "role" in m]
    except Exception:
        pass
    return []


def _save_history(messages: List[dict]) -> None:
    try:
        _DATA.mkdir(parents=True, exist_ok=True)
        # Keep last 40 turns max for disk + context
        _HISTORY.write_text(json.dumps(messages[-40:], indent=2), encoding="utf-8")
    except OSError:
        pass


def make_ollama_page(on_back: Callable[[], None]) -> QWidget:
    host, model = apply_config()
    messages: List[dict] = _load_history()

    body = QWidget()
    lay = QVBoxLayout(body)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(3)

    meta = QLabel(f"{model}\n{host}")
    meta.setStyleSheet("font-size: 9px; color: #9ab;")
    meta.setWordWrap(True)
    lay.addWidget(meta)

    log = QTextEdit()
    log.setReadOnly(True)
    log.setStyleSheet("font-size: 10px;")
    lay.addWidget(log, 1)

    row = QHBoxLayout()
    row.setSpacing(3)
    entry = QLineEdit()
    entry.setPlaceholderText("Ask…")
    send = QPushButton("Go")
    send.setFixedWidth(36)
    row.addWidget(entry, 1)
    row.addWidget(send)
    lay.addLayout(row)

    tools = QHBoxLayout()
    tools.setSpacing(3)
    clear_btn = QPushButton("Clear")
    ping_btn = QPushButton("Status")
    tools.addWidget(clear_btn)
    tools.addWidget(ping_btn)
    lay.addLayout(tools)

    status = QLabel("")
    status.setStyleSheet("font-size: 9px; color: #8af;")
    status.setWordWrap(True)
    lay.addWidget(status)

    worker: Optional[_ChatWorker] = None

    def rebuild() -> None:
        lines = []
        for m in messages[-20:]:
            role = m.get("role", "?")
            prefix = "You" if role == "user" else "AI"
            content = (m.get("content") or "").strip()
            lines.append(f"{prefix}: {content}")
        log.setPlainText("\n\n".join(lines) if lines else "(no chat yet)")
        log.verticalScrollBar().setValue(log.verticalScrollBar().maximum())

    def set_busy(busy: bool) -> None:
        send.setEnabled(not busy)
        entry.setEnabled(not busy)
        clear_btn.setEnabled(not busy)

    def on_send() -> None:
        nonlocal worker, host, model
        host, model = apply_config()
        meta.setText(f"{model}\n{host}")
        text = entry.text().strip()
        if not text:
            return
        ok, err = ollama_reachable(host)
        if not ok:
            status.setText(f"Ollama offline: {err}\nSee docs/OLLAMA.md")
            return
        entry.clear()
        messages.append({"role": "user", "content": text})
        rebuild()
        status.setText("Thinking…")
        set_busy(True)
        # Cap context for Pi RAM
        ctx = messages[-12:]
        worker = _ChatWorker(host, model, ctx, parent=body)
        worker.done.connect(on_reply)
        worker.failed.connect(on_fail)
        worker.start()

    def on_reply(text: str) -> None:
        messages.append({"role": "assistant", "content": text})
        _save_history(messages)
        rebuild()
        status.setText("Ready")
        set_busy(False)

    def on_fail(err: str) -> None:
        status.setText(f"Error: {err}")
        # drop failed user turn? keep it so they can retry
        set_busy(False)

    def on_clear() -> None:
        messages.clear()
        _save_history(messages)
        rebuild()
        status.setText("Cleared")

    def on_ping() -> None:
        nonlocal host, model
        host, model = apply_config()
        meta.setText(f"{model}\n{host}")
        ok, err = ollama_reachable(host)
        if not ok:
            status.setText(f"Offline: {err}")
            return
        models = list_models(host)
        has = any(model == m or m.startswith(model.split(":")[0]) for m in models)
        if has:
            status.setText(f"OK · model present · {len(models)} total")
        else:
            status.setText(
                f"OK server · pull model:\n  ollama pull {model}"
            )

    send.clicked.connect(on_send)
    entry.returnPressed.connect(on_send)
    clear_btn.clicked.connect(on_clear)
    ping_btn.clicked.connect(on_ping)

    rebuild()
    # Soft check on open
    ok, err = ollama_reachable(host)
    if ok:
        status.setText("Ollama up — Status to check model")
    else:
        status.setText("Ollama not running (optional)\nTools → AI later when ready")

    return page_chrome("AI · Ollama", body, on_back)
