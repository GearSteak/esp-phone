# Ollama + small DeepSeek (optional)

Digivice app: **Tools → AI** talks to a local [Ollama](https://ollama.com) server.

Default model: `llama3.2:1b` on Pi 4 2GB (set in `/etc/esp-handset/ollama.env` by `digivice-full-update`).

## Install (automatic)

`sudo digivice-full-update` runs **`digivice-ensure-ollama`**, which:

1. Installs [Ollama](https://ollama.com) (official install script)
2. Starts the `ollama` service
3. Writes `/etc/esp-handset/ollama.env` if missing
4. Pulls a small model in the **background** (log: `~/.esp-handset/ollama-pull.log`)

Manual:

```bash
sudo digivice-ensure-ollama
sudo digivice-ensure-ollama --foreground-pull   # wait until download finishes
```

### Model picked by RAM

| RAM | Model |
|-----|--------|
| Pi 4 **2 GB** | `llama3.2:1b` |
| Pi 4 **4 GB+** | `llama3.2:3b` |
| &lt; 1.5 GB (Pi Zero class) | install skipped |

Override before install: `sudo DIGIVICE_OLLAMA_MODEL=deepseek-r1:1.5b digivice-ensure-ollama`

## Install (manual, if needed)

```bash
curl -fsSL https://ollama.com/install.sh | sh
ollama pull llama3.2:1b
```

Verify:

```bash
curl -s http://127.0.0.1:11434/api/tags
ollama run llama3.2:1b "hi"
```

## Digivice config

Optional `/etc/esp-handset/ollama.env` or `~/.esp-handset/ollama.env`:

```bash
OLLAMA_HOST=http://127.0.0.1:11434
OLLAMA_MODEL=llama3.2:1b
```

Or env for one session:

```bash
export ESP_OLLAMA_MODEL=llama3.2:1b
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
