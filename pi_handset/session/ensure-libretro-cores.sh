#!/usr/bin/env bash
# Install libretro cores for Digivice in-UI emulators (no RetroArch window).
# Fast path: copy any apt cores, then fetch missing .so zips from libretro buildbot.
# Never apt-install retroarch (huge, unused, looked frozen for ~1h on Pi Zero).
#
#   ensure-libretro-cores.sh
#
set +e
set -u

PREFIX="${ESP_HANDSET_PREFIX:-/opt/esp-handset}"
DEST="$PREFIX/libretro"
LOG_DIR="${HOME:-/tmp}/.esp-handset"
[[ "$(id -u)" -eq 0 && -n "${SUDO_USER:-}" ]] && \
  LOG_DIR="$(getent passwd "$SUDO_USER" | cut -d: -f6)/.esp-handset"
mkdir -p "$LOG_DIR" "$DEST" 2>/dev/null || true
LOG="$LOG_DIR/libretro-ensure.log"
STATUS_FILE="/etc/esp-handset/libretro.status"
mkdir -p /etc/esp-handset 2>/dev/null || true

log() { echo "[libretro] $*" | tee -a "$LOG"; }

write_status() {
  echo "$1" >"$STATUS_FILE" 2>/dev/null || true
  chmod 644 "$STATUS_FILE" 2>/dev/null || true
}

resolve_user() {
  if [[ -n "${SUDO_USER:-}" && "${SUDO_USER}" != "root" ]]; then
    echo "$SUDO_USER"; return 0
  fi
  if [[ -n "${DIGI_GUI_USER:-}" && "${DIGI_GUI_USER}" != "root" ]]; then
    echo "${DIGI_GUI_USER}"; return 0
  fi
  for u in pi isaac; do
    id "$u" >/dev/null 2>&1 && echo "$u" && return 0
  done
  if [[ "$(id -u)" -ne 0 ]]; then
    id -un
    return 0
  fi
  echo "pi"
}

USER_NAME="$(resolve_user)"
USER_HOME="$(getent passwd "$USER_NAME" | cut -d: -f6 || echo /home/"$USER_NAME")"
USER_DEST="$USER_HOME/.esp-handset/cores"
mkdir -p "$USER_DEST" 2>/dev/null || true

log "=== start $(date -Is 2>/dev/null || date) dest=$DEST user=$USER_NAME ==="

# Tools only — do NOT try 12 phantom libretro-* debs or retroarch.
export DEBIAN_FRONTEND=noninteractive
if ! command -v unzip >/dev/null 2>&1 || ! command -v curl >/dev/null 2>&1; then
  log "apt: unzip curl wget"
  apt-get install -y unzip curl wget >/dev/null 2>&1 || true
fi

fetch_file() {
  local url="$1" out="$2"
  if command -v curl >/dev/null 2>&1; then
    curl -fL --connect-timeout 12 --max-time 90 -o "$out" "$url"
    return $?
  fi
  if command -v wget >/dev/null 2>&1; then
    wget -q -T 90 -O "$out" "$url"
    return $?
  fi
  return 1
}

valid_so() {
  local f="$1"
  [[ -f "$f" && -s "$f" ]] || return 1
  [[ "$(wc -c <"$f" 2>/dev/null || echo 0)" -ge 80000 ]] || return 1
  head -c 4 "$f" 2>/dev/null | grep -q $'\x7fELF' || return 1
  return 0
}

copy_existing() {
  local d so
  for d in \
    /usr/lib/aarch64-linux-gnu/libretro \
    /usr/lib/arm-linux-gnueabihf/libretro \
    /usr/lib/libretro \
    /usr/lib/retroarch/cores \
    "$USER_HOME/.config/retroarch/cores" \
    "$USER_DEST"
  do
    [[ -d "$d" ]] || continue
    for so in "$d"/*_libretro.so; do
      [[ -f "$so" ]] || continue
      valid_so "$so" || continue
      cp -n "$so" "$DEST/" 2>/dev/null || true
    done
  done
}
copy_existing

have_core() {
  local stem="$1" f
  for f in "$DEST/${stem}_libretro.so" "$DEST/${stem}"*_libretro.so \
    "$USER_DEST/${stem}_libretro.so" "$USER_DEST/${stem}"*_libretro.so; do
    valid_so "$f" && return 0
  done
  return 1
}

ARCH="$(uname -m)"
case "$ARCH" in
  aarch64|arm64) RL_ARCH="aarch64" ;;
  armv7l|armhf|armv6l) RL_ARCH="armhf" ;;
  x86_64) RL_ARCH="x86_64" ;;
  *)
    log "arch $ARCH — skip buildbot download"
    RL_ARCH=""
    ;;
esac

NEED_CORES="gambatte fceumm nestopia genesis_plus_gx mgba snes9x pcsx_rearmed"

if [[ -n "$RL_ARCH" ]]; then
  BASE="https://buildbot.libretro.com/nightly/linux/${RL_ARCH}/latest"
  for stem in $NEED_CORES; do
    if have_core "$stem"; then
      log "have $stem"
      continue
    fi
    url="$BASE/${stem}_libretro.so.zip"
    tmp="/tmp/digi-${stem}-core.zip"
    log "download $stem ($RL_ARCH)…"
    rm -f "$tmp"
    if ! fetch_file "$url" "$tmp"; then
      log "WARN: download $stem failed"
      rm -f "$tmp"
      continue
    fi
    if command -v unzip >/dev/null 2>&1; then
      unzip -oj "$tmp" "*_libretro.so" -d "$DEST" >/dev/null 2>&1 \
        || unzip -o "$tmp" -d "$DEST" >/dev/null 2>&1 \
        || log "WARN: unzip $stem failed"
    else
      log "WARN: unzip missing"
    fi
    rm -f "$tmp"
    if have_core "$stem"; then
      log "ok $stem"
    else
      log "WARN: $stem still missing after download"
    fi
  done
fi

chmod 755 "$DEST"/*.so 2>/dev/null || true
for so in "$DEST"/*_libretro.so; do
  [[ -f "$so" ]] || continue
  valid_so "$so" || { log "WARN: bad/truncated $(basename "$so") — removing"; rm -f "$so"; }
done

# Mirror into user cores dir (Digivice searches here too)
for so in "$DEST"/*_libretro.so; do
  [[ -f "$so" ]] || continue
  cp -f "$so" "$USER_DEST/" 2>/dev/null || true
done

if [[ "$(id -u)" -eq 0 ]]; then
  chown -R "$USER_NAME:$USER_NAME" "$DEST" "$USER_DEST" 2>/dev/null || true
fi

NES_BIOS_DIRS=(
  "$PREFIX/bios/nes"
  "$USER_HOME/.esp-handset/bios/nes"
)
NST_URL="https://raw.githubusercontent.com/libretro/nestopia/master/NstDatabase.xml"
for bios in "${NES_BIOS_DIRS[@]}"; do
  mkdir -p "$bios" 2>/dev/null || true
  if [[ ! -s "$bios/NstDatabase.xml" ]]; then
    log "fetch NstDatabase.xml → $bios"
    fetch_file "$NST_URL" "$bios/NstDatabase.xml" || true
  fi
done
if [[ "$(id -u)" -eq 0 ]]; then
  chown -R "$USER_NAME:$USER_NAME" "$PREFIX/bios" \
    "$USER_HOME/.esp-handset/bios" 2>/dev/null || true
fi

MISSING=""
for stem in gambatte fceumm nestopia genesis_plus_gx mgba snes9x pcsx_rearmed; do
  have_core "$stem" || MISSING="$MISSING $stem"
done
if [[ -z "$MISSING" ]]; then
  write_status "ok gambatte fceumm nestopia genesis_plus_gx mgba snes9x pcsx_rearmed"
else
  write_status "missing$MISSING"
fi

log "cores in $DEST:"
ls -1 "$DEST"/*_libretro.so 2>/dev/null | sed 's#.*/#  #' | tee -a "$LOG" \
  || log "  (none yet)"
exit 0
