# Ollama + small DeepSeek (optional)

Digivice app: **Tools → AI** talks to a local [Ollama](https://ollama.com) server.

Default model: `deepseek-r1:1.5b` (override anytime).

## Install (when you want it)

On a Pi with enough RAM (Pi 4/5 recommended; Zero 2 W is often too tight for LLMs):

```bash
curl -fsSL https://ollama.com/install.sh | sh
# or: sudo apt install ollama   # if packaged

# small DeepSeek
ollama pull deepseek-r1:1.5b

# start server (service may auto-start after install)
ollama serve   # if not already a systemd unit
```

Verify:

```bash
curl -s http://127.0.0.1:11434/api/tags
ollama run deepseek-r1:1.5b "hi"
```

## Digivice config

Optional `/etc/esp-handset/ollama.env` or `~/.esp-handset/ollama.env`:

```bash
OLLAMA_HOST=http://127.0.0.1:11434
OLLAMA_MODEL=deepseek-r1:1.5b
```

Or env for one session:

```bash
export ESP_OLLAMA_MODEL=deepseek-r1:1.5b
export ESP_OLLAMA_HOST=http://127.0.0.1:11434
handset-phone
```

Chat history: `~/.esp-handset/ollama_chat.json`.

## UI

**Tools → AI** · type a prompt · **Go** · **Status** checks server/model · **Clear** resets history.

If Status says offline, install/start Ollama first — the rest of Digivice still works without it.

## Note on Pi Zero 2 W

Half‑GB boards usually cannot host even 1.5B models comfortably. Options:

- Run Ollama on a desktop/NAS and set `OLLAMA_HOST=http://that-machine:11434`
- Or wait for a Pi 4/5 handset board
