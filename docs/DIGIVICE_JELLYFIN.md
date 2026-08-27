# Digivice Jellyfin — share phone media to Fire TV / LAN

Digivice can run a **Jellyfin** server so other devices (Fire TV, phones, PCs) play movies and music stored on the Pi or on a USB cartridge.

## What you get

| | |
|--|--|
| Digivice | **Settings → System → Share** — Start / Stop |
| Clients | Jellyfin app on Fire TV (or any Jellyfin client) |
| Libraries | `~/Videos`, `~/Music`, `~/Audiobooks` |
| Cart | When a cart with `cartridge.json` is mounted, **Refresh cart path** links it under `/srv/digivice-media/cart` — add that folder in Jellyfin once |

Jellyfin is **not** started on every boot (saves RAM). Use **Start sharing** when you want the TV to see Digivice.

## One-time setup

1. On Digivice: **Settings → Update** (installs Jellyfin).
2. **Settings → System → Share → Start sharing**.
3. On a **PC or desktop browser** (not the tiny Digivice panel), open the URL shown (e.g. `http://192.168.1.42:8096`).
4. Finish the Jellyfin wizard (admin user).
5. Add libraries:
   - Movies → `/home/<user>/Videos` (and/or cart movies folder)
   - Music → `/home/<user>/Music`
   - Optional: `/srv/digivice-media/cart` for USB carts
6. On **Fire TV**: install **Jellyfin**, Add Server → Digivice IP, port **8096**.

Prefer **direct play** (H.264 / common MP4/MKV). Heavy transcoding on a Pi 4 2GB will struggle.

## SSH / doctor

```bash
sudo digivice-ensure-jellyfin --doctor
sudo digivice-jellyfin-ctl status
sudo digivice-jellyfin-ctl url
sudo digivice-jellyfin-ctl start
```

## Notes

- Same Wi‑Fi as the Fire TV.
- USB cart unplug → Refresh cart path (or stop/start Share).
- First library scan can take a while after adding many files.
