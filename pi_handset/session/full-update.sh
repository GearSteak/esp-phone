#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════
#  ONE command — full Digivice software stack update
#
#    sudo digivice-full-update
#
#  Or from a git checkout before the command is installed:
#
#    cd ~/esp-phone && git pull && sudo bash pi_handset/session/full-update.sh
#
#  What it does (everything that matters):
#    • git fetch + hard-reset main (re-clone if git corrupt)
#    • apt packages (PyQt, uinput, GPIO, xdotool, spidev, …)
#    • copies UI/scripts → /opt/esp-handset + /usr/local/bin
#    • systemd: digi-buttons-inputd, esp-keyd (enable + start)
#    • udev + uinput + software mouse cursor conf
#    • passwordless digivice-update / full-update / power for Settings
#    • FIX SCREENS: kill broken HDMI hotplug, restore userspace ST7789 SPI,
#      wake panel, restart Digivice (so the 2" works again from this one command)
#
#  Flags:
#    --with-display     also run install-display.sh (can break userspace SPI)
#    --with-spi-userspace  re-apply Instructables SPI userspace config (always on by default)
#    --no-spi-fix        skip the built-in SPI/HDMI screen repair
#    --no-restart       don't relaunch Digivice UI when done
#    --reboot           reboot when finished
# ═══════════════════════════════════════════════════════════════════════════
set -u
set +e

PREFIX="${ESP_HANDSET_PREFIX:-/opt/esp-handset}"
GIT_URL="${ESP_HANDSET_GIT_URL:-https://github.com/GearSteak/esp-phone.git}"
BRANCH="${ESP_HANDSET_BRANCH:-main}"
LOG_DIR="${HOME:-/tmp}/.esp-handset"
LOG="${LOG_DIR}/full-update.log"
WITH_DISPLAY=0
WITH_SPI_USER=1
SPI_FIX=1
DO_RESTART=1
DO_REBOOT=0
NEED_REBOOT=0

for a in "$@"; do
  case "$a" in
    --with-display) WITH_DISPLAY=1 ;;
    --with-spi-userspace|--spi-userspace) WITH_SPI_USER=1 ;;
    --no-spi-userspace) WITH_SPI_USER=0 ;;
    --no-spi-fix) SPI_FIX=0 ;;
    --no-restart) DO_RESTART=0 ;;
    --reboot) DO_REBOOT=1 ;;
    -h|--help)
      sed -n '2,35p' "$0"
      exit 0
      ;;
  esac
done

mkdir -p "$LOG_DIR" 2>/dev/null || true
log() { echo "[$(date '+%H:%M:%S')] $*" | tee -a "$LOG"; }
die() { log "ERROR: $*"; exit 1; }

# --- root ---
if [[ "$(id -u)" -ne 0 ]]; then
  echo "Re-run with:  sudo digivice-full-update $*"
  echo "  or:         sudo bash $0 $*"
  exec sudo env \
    ESP_HANDSET_PREFIX="$PREFIX" \
    ESP_HANDSET_REPO="${ESP_HANDSET_REPO:-}" \
    ESP_HANDSET_GIT_URL="$GIT_URL" \
    ESP_HANDSET_BRANCH="$BRANCH" \
    HOME="${HOME}" \
    SUDO_USER="${SUDO_USER:-$USER}" \
    DISPLAY="${DISPLAY:-:0}" \
    bash "$0" "$@"
fi

USER_NAME="${SUDO_USER:-$USER}"
[[ "$USER_NAME" == "root" ]] && USER_NAME="pi"
USER_HOME="$(getent passwd "$USER_NAME" | cut -d: -f6 || echo /home/"$USER_NAME")"

log "════════════════════════════════════════"
log " Digivice FULL UPDATE"
log " user=$USER_NAME  prefix=$PREFIX"
log "════════════════════════════════════════"

# --- packages ---
export DEBIAN_FRONTEND=noninteractive
log "apt: packages…"
apt-get update -qq 2>&1 | tee -a "$LOG" | tail -n 5
apt-get install -y \
  git \
  python3 python3-pip python3-pyqt5 python3-serial \
  python3-uinput python3-smbus python3-rpi.gpio python3-lgpio \
  python3-spidev \
  i2c-tools xdotool xbitmaps x11-xserver-utils \
  wmctrl fonts-dejavu-core \
  2>&1 | tee -a "$LOG" | tail -n 20

# --- repo ---
find_repo() {
  if [[ -n "${ESP_HANDSET_REPO:-}" && -d "${ESP_HANDSET_REPO}/pi_handset" ]]; then
    echo "$ESP_HANDSET_REPO"; return 0
  fi
  if [[ -f /etc/esp-handset/repo.path ]]; then
    local p
    p="$(tr -d '[:space:]' </etc/esp-handset/repo.path)"
    [[ -d "$p/pi_handset" ]] && echo "$p" && return 0
  fi
  local d
  for d in \
    "$USER_HOME/esp-phone" \
    "$USER_HOME/esp phone" \
    /home/*/esp-phone \
    /opt/esp-phone
  do
    [[ -d "$d/pi_handset" ]] && echo "$d" && return 0
  done
  return 1
}

REPO="$(find_repo || true)"
if [[ -z "${REPO:-}" ]]; then
  REPO="$USER_HOME/esp-phone"
  log "Cloning $GIT_URL → $REPO"
  mkdir -p "$(dirname "$REPO")"
  rm -rf "$REPO"
  sudo -u "$USER_NAME" git clone --branch "$BRANCH" --depth 1 "$GIT_URL" "$REPO" \
    2>&1 | tee -a "$LOG" || die "git clone failed (network?)"
else
  log "Repo: $REPO"
fi

if [[ -d "$REPO/.git" ]]; then
  log "git: sync origin/$BRANCH …"
  chown -R "$USER_NAME:$USER_NAME" "$REPO" 2>/dev/null || true
  sudo -u "$USER_NAME" git -C "$REPO" remote set-url origin "$GIT_URL" 2>/dev/null || true
  if ! sudo -u "$USER_NAME" git -C "$REPO" fetch --prune origin "$BRANCH" 2>&1 | tee -a "$LOG"; then
    log "git fetch failed (corrupt clone?) — fresh re-clone"
    BAD="${REPO}.broken.$(date +%s)"
    mv "$REPO" "$BAD" 2>/dev/null || rm -rf "$REPO"
    REPO="$USER_HOME/esp-phone"
    sudo -u "$USER_NAME" git clone --branch "$BRANCH" --depth 1 "$GIT_URL" "$REPO" \
      2>&1 | tee -a "$LOG" || die "git clone failed (network?)"
  else
    sudo -u "$USER_NAME" git -C "$REPO" stash push -u -m "full-update" 2>/dev/null || true
    sudo -u "$USER_NAME" git -C "$REPO" checkout "$BRANCH" 2>/dev/null \
      || sudo -u "$USER_NAME" git -C "$REPO" checkout -B "$BRANCH" "origin/$BRANCH"
    if ! sudo -u "$USER_NAME" git -C "$REPO" reset --hard "origin/$BRANCH" 2>&1 | tee -a "$LOG"; then
      log "git reset failed — fresh re-clone"
      BAD="${REPO}.broken.$(date +%s)"
      mv "$REPO" "$BAD" 2>/dev/null || rm -rf "$REPO"
      REPO="$USER_HOME/esp-phone"
      sudo -u "$USER_NAME" git clone --branch "$BRANCH" --depth 1 "$GIT_URL" "$REPO" \
        2>&1 | tee -a "$LOG" || die "git clone failed (network?)"
    fi
  fi
  REV="$(sudo -u "$USER_NAME" git -C "$REPO" rev-parse --short HEAD 2>/dev/null || echo '?')"
  log "Now at $REV"
else
  log "WARN: not a git tree — installing whatever is on disk"
  REV="?"
fi

ROOT="$REPO/pi_handset"
[[ -d "$ROOT/esp_handset" ]] || die "missing $ROOT/esp_handset"

mkdir -p /etc/esp-handset
echo "$REPO" >/etc/esp-handset/repo.path
echo "$REPO" >"$USER_HOME/.esp-handset/repo.path" 2>/dev/null || true
chown "$USER_NAME:$USER_NAME" "$USER_HOME/.esp-handset/repo.path" 2>/dev/null || true

# --- install tree (same core as install-handset, no mystery bits) ---
log "Install → $PREFIX"
mkdir -p "$PREFIX" "$PREFIX/session" /etc/esp-handset /etc/udev/rules.d /etc/X11/xorg.conf.d
cp -a "$ROOT/esp_handset" "$PREFIX/"
cp -a "$ROOT/session/." "$PREFIX/session/" 2>/dev/null || true
[[ -d "$ROOT/display" ]] && cp -a "$ROOT/display" "$PREFIX/"

install -m 755 "$ROOT/esp_handset/handset_app.py" "$PREFIX/handset_app.py"
install -m 755 "$ROOT/esp_handset/buttons_inputd.py" "$PREFIX/buttons_inputd.py"
install -m 755 "$ROOT/esp_handset/esp_keyd.py" "$PREFIX/esp_keyd.py"
install -m 755 "$ROOT/esp_handset/pointer_overlay.py" "$PREFIX/esp_handset/pointer_overlay.py" 2>/dev/null || true
# keep under package too
[[ -f "$ROOT/esp_handset/pointer_overlay.py" ]] && \
  install -m 755 "$ROOT/esp_handset/pointer_overlay.py" "$PREFIX/esp_handset/pointer_overlay.py"
install -m 755 "$ROOT/esp_handset/hat_inputd.py" "$PREFIX/hat_inputd.py"
install -m 755 "$ROOT/esp_handset/cardkb_inputd.py" "$PREFIX/cardkb_inputd.py"
install -m 755 "$ROOT/esp_handset/t9_keypad_inputd.py" "$PREFIX/t9_keypad_inputd.py"

# Core /usr/local commands
install -m 755 "$ROOT/session/handset-session.sh" "$PREFIX/session/handset-session.sh"
install -m 755 "$ROOT/session/handset-session.sh" /usr/local/bin/handset-session
install -m 755 "$ROOT/session/full-update.sh" "$PREFIX/session/full-update.sh"
install -m 755 "$ROOT/session/full-update.sh" /usr/local/bin/digivice-full-update
install -m 755 "$ROOT/session/gui-update.sh" "$PREFIX/session/gui-update.sh"
install -m 755 "$ROOT/session/gui-update.sh" /usr/local/bin/digivice-gui-update
install -m 755 "$ROOT/session/update-handset.sh" /usr/local/bin/digivice-update 2>/dev/null || true
install -m 755 "$ROOT/session/ensure-buttons.sh" /usr/local/bin/digivice-ensure-buttons 2>/dev/null || true
install -m 755 "$ROOT/session/fix-cursor.sh" /usr/local/bin/digivice-fix-cursor 2>/dev/null || true
install -m 755 "$ROOT/session/restore-desktop-displays.sh" /usr/local/bin/digivice-restore-desktop 2>/dev/null || true
install -m 755 "$ROOT/session/desktop-spi-mirror.sh" /usr/local/bin/digivice-desktop-mirror 2>/dev/null || true
install -m 755 "$ROOT/session/fix-desktop-spi-now.sh" /usr/local/bin/digivice-fix-desktop-spi 2>/dev/null || true
install -m 755 "$ROOT/session/digivice-layout.sh" /usr/local/bin/digivice-layout 2>/dev/null || true
install -m 755 "$ROOT/session/unfuck-displays.sh" /usr/local/bin/digivice-unfuck-displays 2>/dev/null || true
install -m 755 "$ROOT/session/spi-blank.sh" /usr/local/bin/digivice-spi-blank 2>/dev/null || true
install -m 755 "$ROOT/session/spi-flash.sh" /usr/local/bin/digivice-spi-flash 2>/dev/null || true
install -m 755 "$ROOT/session/fix-screens.sh" /usr/local/bin/digivice-fix-screens 2>/dev/null || true
install -m 755 "$ROOT/session/spi-prove.sh" /usr/local/bin/digivice-spi-prove 2>/dev/null || true
install -m 755 "$ROOT/session/spi-test.sh" /usr/local/bin/digivice-spi-test 2>/dev/null || true
install -m 755 "$ROOT/session/mirror-displays.sh" /usr/local/bin/digivice-mirror-displays 2>/dev/null || true
install -m 755 "$ROOT/session/hdmi-hotplug.sh" "$PREFIX/session/hdmi-hotplug.sh" 2>/dev/null || true
install -m 755 "$ROOT/session/hdmi-hotplug.sh" /usr/local/bin/digivice-hdmi-hotplug 2>/dev/null || true
install -m 755 "$ROOT/session/power.sh" "$PREFIX/session/power.sh" 2>/dev/null || true
install -m 755 "$ROOT/session/power.sh" /usr/local/bin/digivice-power 2>/dev/null || true

if [[ -d "$ROOT/display" ]]; then
  install -m 755 "$ROOT/display/install-spi-userspace.sh" /usr/local/bin/digivice-install-spi-userspace 2>/dev/null || true
  install -m 755 "$ROOT/display/recover-hdmi.sh" /usr/local/bin/digivice-recover-hdmi 2>/dev/null || true
  install -m 755 "$ROOT/display/set-panel-rotation.sh" /usr/local/bin/digivice-set-rotation 2>/dev/null || true
  install -m 755 "$ROOT/display/spi-doctor.sh" /usr/local/bin/digivice-spi-doctor 2>/dev/null || true
fi

cat >/usr/local/bin/handset-phone <<'EOF'
#!/bin/bash
exec /usr/local/bin/handset-session phone
EOF
cat >/usr/local/bin/handset-desktop <<'EOF'
#!/bin/bash
exec /usr/local/bin/handset-session desktop
EOF
cat >/usr/local/bin/digivice-leave <<'EOF'
#!/bin/bash
export DISPLAY="${DISPLAY:-:0}"
exec /usr/local/bin/handset-session force-desktop
EOF
chmod +x /usr/local/bin/handset-phone /usr/local/bin/handset-desktop /usr/local/bin/digivice-leave \
  /usr/local/bin/digivice-full-update

# Sudoers for later GUI / terminal updates
cat >/etc/sudoers.d/esp-handset-update <<EOF
$USER_NAME ALL=(root) NOPASSWD: /usr/local/bin/digivice-full-update
$USER_NAME ALL=(root) NOPASSWD: /usr/local/bin/digivice-update
$USER_NAME ALL=(root) NOPASSWD: /usr/local/bin/digivice-gui-update
$USER_NAME ALL=(root) NOPASSWD: /usr/local/bin/digivice-power
$USER_NAME ALL=(root) NOPASSWD: /usr/local/bin/digivice-ensure-buttons
$USER_NAME ALL=(root) NOPASSWD: /usr/local/bin/digivice-fix-cursor
$USER_NAME ALL=(root) NOPASSWD: $PREFIX/session/full-update.sh
$USER_NAME ALL=(root) NOPASSWD: $PREFIX/session/update-handset.sh
$USER_NAME ALL=(root) NOPASSWD: $PREFIX/session/gui-update.sh
$USER_NAME ALL=(root) NOPASSWD: $PREFIX/session/power.sh
$USER_NAME ALL=(root) NOPASSWD: $PREFIX/session/ensure-buttons.sh
$USER_NAME ALL=(root) NOPASSWD: /usr/bin/bash $PREFIX/session/gui-update.sh
$USER_NAME ALL=(root) NOPASSWD: /bin/bash $PREFIX/session/gui-update.sh
$USER_NAME ALL=(root) NOPASSWD: /usr/bin/bash $PREFIX/session/power.sh
$USER_NAME ALL=(root) NOPASSWD: /bin/bash $PREFIX/session/power.sh
EOF
chmod 440 /etc/sudoers.d/esp-handset-update

# uinput + udev (keyboard to seat)
cat >/etc/modules-load.d/uinput.conf <<'EOF'
uinput
EOF
modprobe uinput 2>/dev/null || true
cat >/etc/udev/rules.d/99-digivice-buttons.rules <<'EOF'
KERNEL=="uinput", GROUP="input", MODE="0660", OPTIONS+="static_node=uinput"
SUBSYSTEM=="input", KERNEL=="event*", ATTRS{name}=="Digivice-Buttons", \
  MODE="0666", GROUP="input", \
  ENV{ID_INPUT}="1", ENV{ID_INPUT_KEYBOARD}="1", \
  ENV{ID_INPUT_KEY}="1", TAG+="uaccess", TAG+="seat"
EOF
udevadm control --reload-rules 2>/dev/null || true
usermod -aG dialout,input,gpio,i2c "$USER_NAME" 2>/dev/null || true

# Software mouse cursor (vc4 HW cursor often invisible)
cat >/etc/X11/xorg.conf.d/20-digivice-swcursor.conf <<'EOF'
Section "Device"
    Identifier "Digivice modesetting"
    Driver "modesetting"
    Option "SWcursor" "true"
EndSection
EOF

# Buttons + key bridge services
cat >/etc/systemd/system/digi-buttons-inputd.service <<EOF
[Unit]
Description=Digivice hard buttons (GPIO → keys)
After=multi-user.target
Wants=multi-user.target

[Service]
Type=simple
User=root
Environment=DISPLAY=:0
Environment=XAUTHORITY=$USER_HOME/.Xauthority
Environment=ESP_HANDSET_PREFIX=$PREFIX
ExecStartPre=-/sbin/modprobe uinput
ExecStart=/usr/bin/python3 $PREFIX/buttons_inputd.py
Restart=always
RestartSec=1

[Install]
WantedBy=multi-user.target
EOF

cat >/etc/systemd/system/esp-keyd.service <<EOF
[Unit]
Description=ESP KEY bridge → uinput
After=multi-user.target

[Service]
Type=simple
User=root
ExecStart=/usr/bin/python3 $PREFIX/esp_keyd.py
Restart=always
RestartSec=2
Environment=ESP_HANDSET_PREFIX=$PREFIX

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable digi-buttons-inputd.service
systemctl restart digi-buttons-inputd.service || true
systemctl enable esp-keyd.service
systemctl restart esp-keyd.service || true

if [[ -x /usr/local/bin/digivice-ensure-buttons ]]; then
  bash /usr/local/bin/digivice-ensure-buttons 2>&1 | tee -a "$LOG" || true
fi

# ═══════════════════════════════════════════════════════════════════════════
#  SCREEN FIX (built-in — this is the one-command fix for blank 2" / HDMI mess)
# ═══════════════════════════════════════════════════════════════════════════
if [[ "$SPI_FIX" -eq 1 ]]; then
  log "Screen fix: undo HDMI hotplug thrash + restore userspace ST7789"

  # Kill thrashers
  systemctl disable --now digivice-hdmi-hotplug.service 2>/dev/null || true
  rm -f /etc/systemd/system/digivice-hdmi-hotplug.service
  rm -f /etc/udev/rules.d/99-digivice-hdmi-hotplug.rules
  systemctl daemon-reload 2>/dev/null || true
  udevadm control --reload-rules 2>/dev/null || true
  if [[ -x /usr/local/bin/digivice-hdmi-hotplug ]]; then
    bash /usr/local/bin/digivice-hdmi-hotplug --disable 2>&1 | tee -a "$LOG" || true
  fi

  # Firmware/config
  BOOTCFG=""
  for c in /boot/firmware/config.txt /boot/config.txt; do
    [[ -f "$c" ]] && BOOTCFG="$c" && break
  done
  if [[ -n "$BOOTCFG" ]]; then
    cp -a "$BOOTCFG" "${BOOTCFG}.bak.full-update" 2>/dev/null || true
    sed -i -E 's/^dtoverlay=vc4-kms-v3d,nohdmi/dtoverlay=vc4-kms-v3d/' "$BOOTCFG"
    sed -i -E 's/^dtoverlay=vc4-kms-v3d(|,.*)$/dtoverlay=vc4-kms-v3d/' "$BOOTCFG"
    if ! grep -qE '^dtoverlay=vc4-kms-v3d' "$BOOTCFG"; then
      echo "dtoverlay=vc4-kms-v3d" >>"$BOOTCFG"
    fi
    # ghost HDMI head = broken X + broken SPI mirror
    if grep -qE '^hdmi_force_hotplug=' "$BOOTCFG"; then
      sed -i '/^hdmi_force_hotplug=/d' "$BOOTCFG"
      NEED_REBOOT=1
      log "removed hdmi_force_hotplug (reboot will finish firmware apply)"
    fi
    sed -i '/^hdmi_blanking=/d' "$BOOTCFG" || true
    # mipi-dbi steals SPI from spidev — kill it so /dev/spidev0.0 exists
    if grep -qE 'mipi-dbi-spi|ESP Digivice display' "$BOOTCFG"; then
      sed -i '/# --- ESP Digivice display/,/# --- END ESP Digivice display/d' "$BOOTCFG"
      sed -i '/^dtoverlay=mipi-dbi-spi/d' "$BOOTCFG"
      NEED_REBOOT=1
      log "removed mipi-dbi-spi DRM block (userspace SPI)"
    fi
    if ! grep -qE '^dtparam=spi=on' "$BOOTCFG"; then
      echo "dtparam=spi=on" >>"$BOOTCFG"
      NEED_REBOOT=1
    fi
    if ! grep -q 'ESP Digivice SPI userspace' "$BOOTCFG"; then
      cat >>"$BOOTCFG" <<'EOF'

# --- ESP Digivice SPI userspace (ST7789 mirror) ---
dtparam=spi=on
# --- END ESP Digivice SPI userspace ---
EOF
    fi
    log "config: $BOOTCFG OK"
  fi

  # Flags always
  mkdir -p /etc/esp-handset
  echo userspace >/etc/esp-handset/spi-userspace
  echo userspace >/etc/esp-handset/spi-backend
  cat >/etc/esp-handset/env <<'EOF'
ESP_HANDSET_SPI_BACKEND=userspace
ESP_HANDSET_SKIP_LAYOUT=1
ESP_ST7789_SPEED=16000000
ESP_ST7789_SWAP=1
ESP_ST7789_INVERT=1
ESP_ST7789_FPS_MS=40
EOF
  [[ -f /etc/esp-handset/panel-rotation ]] || echo 180 >/etc/esp-handset/panel-rotation
  mkdir -p /etc/profile.d
  cat >/etc/profile.d/esp-handset-spi.sh <<'EOF'
export ESP_HANDSET_SPI_BACKEND=userspace
EOF

  # Optional full install-spi-userspace (dedupe + packages)
  if [[ "$WITH_SPI_USER" -eq 1 && -f "$ROOT/display/install-spi-userspace.sh" ]]; then
    log "ensure install-spi-userspace.sh"
    bash "$ROOT/display/install-spi-userspace.sh" 2>&1 | tee -a "$LOG" || true
  fi

  pkill -9 -f handset_app.py 2>/dev/null || true
  pkill -9 -f desktop_spi_mirror.py 2>/dev/null || true
  sleep 0.4

  if [[ -e /dev/spidev0.0 ]]; then
    log "spidev0.0 present — force reinit @16MHz (kills static) + solid colors"
    export PYTHONPATH="$PREFIX:${PYTHONPATH:-}"
    export ESP_HANDSET_SPI_BACKEND=userspace
    export ESP_ST7789_SPEED=16000000
    export ESP_ST7789_SWAP=1
    export ESP_ST7789_INVERT=1
    /usr/bin/python3 - <<'PY' 2>&1 | tee -a "$LOG" || true
import sys, time, os
sys.path.insert(0, "/opt/esp-handset")
os.environ["ESP_ST7789_SPEED"] = "16000000"
os.environ["ESP_ST7789_SWAP"] = "1"
os.environ["ESP_ST7789_INVERT"] = "1"
try:
    from esp_handset import st7789_spi as st
except Exception as e:
    print("[spi-wake] import failed:", e)
    sys.exit(0)
# Force cold reinit even if a zombie process left the bus messy
try:
    st.close(blank_panel=False)
except Exception:
    pass
ok = False
if hasattr(st, "reinit"):
    ok = st.reinit()
else:
    ok = st.init()
if not ok:
    print("[spi-wake] init failed")
    sys.exit(0)
st.wake_display()
for r, g, b, n in ((255, 0, 0, "RED"), (0, 255, 0, "GREEN"), (0, 0, 255, "BLUE")):
    print("[spi-wake]", n)
    st.fill(r, g, b)
    st.wake_display()
    time.sleep(0.5)
st.fill(0, 160, 0)
st.wake_display()
st.close(blank_panel=False)
print("[spi-wake] panel solid colors OK @16MHz — static should be gone")
PY
  else
    log "WARN: no /dev/spidev0.0 — reboot required after config change"
    NEED_REBOOT=1
  fi
else
  log "Screen fix skipped (--no-spi-fix)"
fi

# Optional heavy DRM display install (opt-in only)
if [[ "$WITH_DISPLAY" -eq 1 && -f "$ROOT/display/install-display.sh" ]]; then
  log "Running install-display.sh (--with-display) — may undo userspace SPI"
  bash "$ROOT/display/install-display.sh" 2>&1 | tee -a "$LOG" || true
fi

# Cursor for live session
export DISPLAY="${DISPLAY:-:0}"
export XAUTHORITY="${XAUTHORITY:-$USER_HOME/.Xauthority}"
if [[ -x /usr/local/bin/digivice-fix-cursor ]]; then
  /usr/local/bin/digivice-fix-cursor --permanent 2>&1 | tee -a "$LOG" || true
  sudo -u "$USER_NAME" env DISPLAY="${DISPLAY:-:0}" XAUTHORITY="$USER_HOME/.Xauthority" \
    /usr/local/bin/digivice-fix-cursor 2>&1 | tee -a "$LOG" || true
fi

log "════════════════════════════════════════"
log " FULL UPDATE OK  rev=${REV:-?}  → $PREFIX"
log " Log: $LOG"
log "════════════════════════════════════════"

if [[ "$DO_REBOOT" -eq 1 || ( "$NEED_REBOOT" -eq 1 && ! -e /dev/spidev0.0 ) ]]; then
  log "Rebooting in 4s so SPI / firmware takes effect…"
  log "After boot: Digivice should autostart; or: handset-phone"
  sleep 4
  reboot
  exit 0
fi

if [[ "$NEED_REBOOT" -eq 1 ]]; then
  log "NOTE: config.txt changed — reboot when convenient:  sudo reboot"
fi

if [[ "$DO_RESTART" -eq 1 ]]; then
  log "Restarting Digivice UI (userspace SPI)…"
  pkill -9 -f handset_app.py 2>/dev/null || true
  pkill -9 -f desktop_spi_mirror.py 2>/dev/null || true
  sleep 0.6
  mkdir -p "$USER_HOME/.esp-handset"
  echo phone >"$USER_HOME/.esp-handset/session_mode"
  echo phone >/etc/esp-handset/ui_mode
  chown "$USER_NAME:$USER_NAME" "$USER_HOME/.esp-handset/session_mode" 2>/dev/null || true
  sudo -u "$USER_NAME" env \
    DISPLAY="${DISPLAY:-:0}" \
    XAUTHORITY="$USER_HOME/.Xauthority" \
    HOME="$USER_HOME" \
    ESP_HANDSET_SPI_BACKEND=userspace \
    ESP_ST7789_SPEED=16000000 \
    ESP_ST7789_SWAP=1 \
    ESP_ST7789_INVERT=1 \
    ESP_ST7789_FPS_MS=40 \
    PYTHONPATH="$PREFIX" \
    bash -c 'set -a; [ -f /etc/esp-handset/env ] && . /etc/esp-handset/env; set +a; nohup /usr/local/bin/handset-phone >>"$HOME/.esp-handset/handset.log" 2>&1 &' || true
  sleep 1.5
  if pgrep -f handset_app.py >/dev/null; then
    log "Digivice is running"
  else
    log "WARN: Digivice did not stay up — tail $USER_HOME/.esp-handset/handset.log"
    tail -n 30 "$USER_HOME/.esp-handset/handset.log" 2>/dev/null | tee -a "$LOG" || true
  fi
fi

echo ""
echo "Done. One command next time:"
echo "  sudo digivice-full-update"
if [[ "$NEED_REBOOT" -eq 1 && -e /dev/spidev0.0 ]]; then
  echo "(config cleaned; if panel still weird once: sudo reboot)"
fi
echo ""
exit 0
