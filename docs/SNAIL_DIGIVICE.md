# Digivice ↔ Snail OS (XTEINK X3) companion

Digivice acts as a **LAN companion** for an X3 running **Snail OS**. The X3 runs
a card Lua app (`digivice.lua`); Digivice serves a tiny HTTP API with notifications.

This does **not** replace official Snail Companion BLE. It is Digivice-owned.

## Setup

### Digivice (Pi)

1. **Apps → Tools → Snail Link**
2. Confirm **Start bridge**
3. Note the URL (e.g. `http://192.168.1.50:8787`) — same Wi‑Fi as the X3

### X3 (Snail OS)

1. Copy [`extras/snail/digivice.lua`](../extras/snail/digivice.lua) to the SD card as:

   ```text
   apps/digivice.lua
   ```

2. Edit the `HOST` line to match Digivice’s URL.
3. Put the card in the X3, open **Digivice** from the launcher.
4. **OK** / **RIGHT** refreshes the Digivice notification inbox.

## API (Digivice)

| Path | Returns |
|------|---------|
| `GET /snail/v1/ping` | `{ok,pong,name}` |
| `GET /snail/v1/status` | name, ip, uptime, time |
| `GET /snail/v1/inbox?limit=20` | `{total,items:[{title,body,kind,when,line}]}` |
| `GET /snail/v1/host.txt` | plain-text HOST=… helper |

Inbox rows come from Digivice `~/.esp-handset/notifs.json` (SMS, LoRa, alarms, etc.).

## HTTPS caveat

Snail documents `snail.fetch` as **HTTPS only**. LAN **HTTP** may be rejected.

If fetch fails with a scheme/TLS error:

1. Generate a self-signed cert on the Pi:

   ```bash
   mkdir -p ~/.esp-handset/snail-bridge
   openssl req -x509 -newkey rsa:2048 -nodes -days 3650 \
     -keyout ~/.esp-handset/snail-bridge/key.pem \
     -out ~/.esp-handset/snail-bridge/cert.pem \
     -subj "/CN=digivice"
   ```

2. Change Digivice bridge code / UI to `start(tls=True)` (or ask for a TLS toggle).
3. Set `HOST` to `https://…:8787` — Snail may still reject an untrusted CA.

Workarounds if TLS verification is strict: a reverse proxy with a real cert, or
a tunnel (Cloudflare / Tailscale HTTPS). Long-term: Digivice-defined BLE instead
of Snail’s closed Companion protocol.

## Test without the X3

```bash
# On Digivice / Pi with bridge running:
curl -s http://127.0.0.1:8787/snail/v1/ping
curl -s http://127.0.0.1:8787/snail/v1/inbox
```

## Files

| Path | Role |
|------|------|
| `pi_handset/esp_handset/snail_bridge.py` | HTTP server |
| `pi_handset/esp_handset/snail_bridge_ui.py` | Digivice UI |
| `extras/snail/digivice.lua` | X3 card app |
