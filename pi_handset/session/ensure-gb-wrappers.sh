#!/usr/bin/env bash
# Always install digivice-gb / digivice-stop-gb into /usr/local/bin and
# clear leftover GB/SPI state. Called from full-update, apply-update, update-handset.
#
#   ensure-gb-wrappers.sh
#   ensure-gb-wrappers.sh --no-kill   # install only
#
set +e
set -u

PREFIX="${ESP_HANDSET_PREFIX:-/opt/esp-handset}"
DO_KILL=1
[[ "${1:-}" == "--no-kill" ]] && DO_KILL=0

log() { echo "[ensure-gb] $*"; }

find_repo() {
  if [[ -n "${ESP_HANDSET_REPO:-}" && -d "${ESP_HANDSET_REPO}/pi_handset/session" ]]; then
    echo "$ESP_HANDSET_REPO"
    return 0
  fi
  if [[ -f /etc/esp-handset/repo.path ]]; then
    local p
    p="$(tr -d '[:space:]' </etc/esp-handset/repo.path)"
    [[ -d "$p/pi_handset/session" ]] && echo "$p" && return 0
  fi
  local d
  for d in /home/*/esp-phone "/home/*/esp phone" /opt/esp-phone; do
    # shellcheck disable=SC2086
    for hit in $d; do
      [[ -d "$hit/pi_handset/session" ]] && echo "$hit" && return 0
    done
  done
  return 1
}

find_script() {
  local name="$1"
  local repo
  repo="$(find_repo || true)"
  local c
  for c in \
    "${repo:+$repo/pi_handset/session/$name}" \
    "$PREFIX/session/$name" \
    "$PREFIX.staging/session/$name" \
    "$(cd "$(dirname "$0")" 2>/dev/null && pwd)/$name"
  do
    [[ -n "$c" && -f "$c" ]] && echo "$c" && return 0
  done
  return 1
}

install_one() {
  local src_name="$1"
  local dest_bin="$2"
  local src
  src="$(find_script "$src_name" || true)"
  if [[ -n "$src" && -f "$src" ]]; then
    mkdir -p "$PREFIX/session" 2>/dev/null || true
    install -m 755 "$src" "$PREFIX/session/$src_name" 2>/dev/null || cp -f "$src" "$PREFIX/session/$src_name"
    install -m 755 "$src" "/usr/local/bin/$dest_bin"
    chmod 755 "/usr/local/bin/$dest_bin" 2>/dev/null || true
    log "installed /usr/local/bin/$dest_bin  ← $src"
    return 0
  fi
  return 1
}

# Nuclear fallback: stop-gb must exist even if git tree is weird
write_stop_gb_fallback() {
  cat >/usr/local/bin/digivice-stop-gb <<'FALLBACK'
#!/usr/bin/env bash
set +e
set -u
PREFIX="${ESP_HANDSET_PREFIX:-/opt/esp-handset}"
HOME_DIR="${HOME:-/tmp}"
mkdir -p "$HOME_DIR/.esp-handset" /etc/esp-handset 2>/dev/null || true
touch "$HOME_DIR/.esp-handset/gb-disabled" 2>/dev/null || true
for h in /home/*/.esp-handset; do
  [[ -d "$h" ]] && touch "$h/gb-disabled" 2>/dev/null || true
done
pkill -9 -f 'digivice-gb|retroarch|mgba-sdl|mgba-qt|desktop_spi_mirror' 2>/dev/null || true
for m in /usr/local/bin/digivice-desktop-mirror "$PREFIX/session/desktop-spi-mirror.sh"; do
  [[ -f "$m" ]] && bash "$m" stop >/dev/null 2>&1 && break
done
rm -f /tmp/digivice-st7789.lock /run/digivice-st7789.lock /run/digivice-gb-rom
rm -f "$HOME_DIR/.esp-handset/gb-rom" /home/*/.esp-handset/gb-rom 2>/dev/null || true
echo phone >/etc/esp-handset/ui_mode 2>/dev/null || true
echo phone >"$HOME_DIR/.esp-handset/session_mode" 2>/dev/null || true
for h in /home/*/.esp-handset; do
  [[ -d "$h" ]] && echo phone >"$h/session_mode" 2>/dev/null || true
done
echo "GB stopped / SPI locks cleared. Run: handset-phone"
FALLBACK
  chmod 755 /usr/local/bin/digivice-stop-gb
  log "wrote FALLBACK /usr/local/bin/digivice-stop-gb"
}

# Thin wrappers so `digivice-full-update` always runs the git copy after pull
write_full_update_wrapper() {
  cat >/usr/local/bin/digivice-full-update <<'WRAP'
#!/bin/bash
set +e
REPO=""
[[ -f /etc/esp-handset/repo.path ]] && REPO="$(tr -d '[:space:]' </etc/esp-handset/repo.path)"
for d in "$REPO" "${HOME}/esp-phone" /home/*/esp-phone "/home/*/esp phone" /opt/esp-phone; do
  # shellcheck disable=SC2086
  for hit in $d; do
    if [[ -f "$hit/pi_handset/session/full-update.sh" ]]; then
      exec bash "$hit/pi_handset/session/full-update.sh" "$@"
    fi
  done
done
if [[ -f /opt/esp-handset/session/full-update.sh ]]; then
  exec bash /opt/esp-handset/session/full-update.sh "$@"
fi
echo "digivice-full-update: full-update.sh not found" >&2
exit 1
WRAP
  chmod 755 /usr/local/bin/digivice-full-update
  log "installed thin digivice-full-update → repo script"
}

log "=== ensure GB wrappers ==="
install_one "digivice-gb.sh" "digivice-gb" || log "WARN: digivice-gb.sh missing in tree"
if ! install_one "digivice-stop-gb.sh" "digivice-stop-gb"; then
  write_stop_gb_fallback
fi
# Also keep a copy under PREFIX even if only fallback was written
if [[ ! -f "$PREFIX/session/digivice-stop-gb.sh" && -f /usr/local/bin/digivice-stop-gb ]]; then
  mkdir -p "$PREFIX/session" 2>/dev/null || true
  cp -f /usr/local/bin/digivice-stop-gb "$PREFIX/session/digivice-stop-gb.sh" 2>/dev/null || true
  chmod 755 "$PREFIX/session/digivice-stop-gb.sh" 2>/dev/null || true
fi

write_full_update_wrapper

# Verify
if [[ -x /usr/local/bin/digivice-stop-gb ]]; then
  log "OK: $(command -v digivice-stop-gb) exists"
else
  log "ERROR: digivice-stop-gb still missing"
fi

if [[ "$DO_KILL" -eq 1 ]]; then
  log "clearing GB/SPI leftover state…"
  # Don't relaunch Digivice here (update will) — only kill + flags + locks
  touch /etc/esp-handset/gb-disabled 2>/dev/null || true
  for h in /home/*/.esp-handset "${HOME:-}/.esp-handset"; do
    [[ -d "$h" ]] || continue
    touch "$h/gb-disabled" 2>/dev/null || true
    rm -f "$h/gb-rom" 2>/dev/null || true
    echo phone >"$h/session_mode" 2>/dev/null || true
  done
  echo phone >/etc/esp-handset/ui_mode 2>/dev/null || true
  pkill -9 -f 'digivice-gb.sh|/usr/local/bin/digivice-gb' 2>/dev/null || true
  pkill -9 -f 'retroarch|mgba-sdl|mgba-qt' 2>/dev/null || true
  pkill -9 -f 'desktop_spi_mirror.py' 2>/dev/null || true
  for m in /usr/local/bin/digivice-desktop-mirror "$PREFIX/session/desktop-spi-mirror.sh"; do
    [[ -f "$m" ]] && bash "$m" stop >/dev/null 2>&1 && break
  done
  rm -f /tmp/digivice-st7789.lock /run/digivice-st7789.lock /run/digivice-gb-rom 2>/dev/null || true
  log "GB kill-switch on · SPI locks cleared · mode=phone"
fi

exit 0
