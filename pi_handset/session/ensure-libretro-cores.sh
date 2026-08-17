#!/usr/bin/env bash
# Install libretro cores for Digivice in-UI emulators (no RetroArch window).
# Apt first; download from libretro buildbot if a core is still missing.
#
#   ensure-libretro-cores.sh
#
set +e
set -u

PREFIX="${ESP_HANDSET_PREFIX:-/opt/esp-handset}"
DEST="$PREFIX/libretro"
LOG_DIR="${HOME:-/tmp}/.esp-handset"
mkdir -p "$LOG_DIR" "$DEST" 2>/dev/null || true

log() { echo "[libretro] $*"; }

resolve_user() {
  if [[ -n "${SUDO_USER:-}" && "${SUDO_USER}" != "root" ]]; then
    echo "$SUDO_USER"; return 0
  fi
  if [[ -n "${DIGI_GUI_USER:-}" && "${DIGI_GUI_USER}" != "root" ]]; then
    echo "$DIGI_GUI_USER"; return 0
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

# Debian / Raspberry Pi OS names (best-effort; missing pkgs are fine)
log "apt: libretro cores…"
export DEBIAN_FRONTEND=noninteractive
for p in \
  unzip wget curl \
  libretro-gambatte \
  libretro-mgba \
  libretro-nestopia \
  libretro-snes9x \
  libretro-fceumm \
  libretro-genesisplusgx \
  libretro-genesis-plus-gx \
  libretro-genplus \
  libretro-gpsp \
  libretro-picodrive \
  retroarch
do
  apt-get install -y "$p" >/dev/null 2>&1 || true
done

# Copy apt-installed cores into our folder so the UI has one search path
for d in \
  /usr/lib/aarch64-linux-gnu/libretro \
  /usr/lib/arm-linux-gnueabihf/libretro \
  /usr/lib/libretro \
  /usr/lib/retroarch/cores \
  "$USER_HOME/.config/retroarch/cores"
do
  [[ -d "$d" ]] || continue
  for so in "$d"/*_libretro.so; do
    [[ -f "$so" ]] || continue
    cp -n "$so" "$DEST/" 2>/dev/null || true
  done
done

have_core() {
  local stem="$1"
  [[ -f "$DEST/${stem}_libretro.so" ]] && return 0
  ls "$DEST"/${stem}*_libretro.so >/dev/null 2>&1 && return 0
  ls /usr/lib/*/libretro/${stem}*_libretro.so >/dev/null 2>&1 && return 0
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

# Cores Digivice actually launches (Pi Zero 2W-capable)
NEED_CORES="gambatte fceumm nestopia genesis_plus_gx gpsp mgba picodrive"

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
    if command -v curl >/dev/null 2>&1; then
      curl -fsSL --max-time 90 -o "$tmp" "$url" || { log "WARN: curl $stem failed"; continue; }
    elif command -v wget >/dev/null 2>&1; then
      wget -q -T 90 -O "$tmp" "$url" || { log "WARN: wget $stem failed"; continue; }
    else
      log "WARN: no curl/wget — cannot fetch $stem"
      continue
    fi
    if command -v unzip >/dev/null 2>&1; then
      unzip -o "$tmp" -d "$DEST" >/dev/null 2>&1 || log "WARN: unzip $stem failed"
    else
      log "WARN: unzip missing"
    fi
    rm -f "$tmp"
    have_core "$stem" && log "ok $stem" || log "WARN: $stem still missing"
  done
fi

chmod 755 "$DEST"/*.so 2>/dev/null || true
if [[ "$(id -u)" -eq 0 ]]; then
  chown -R "$USER_NAME:$USER_NAME" "$DEST" 2>/dev/null || true
fi

log "cores in $DEST:"
ls -1 "$DEST"/*_libretro.so 2>/dev/null | sed 's#.*/#  #' || log "  (none yet)"
exit 0
