#!/usr/bin/env bash
# Digivice media/cart/player diagnostics.
#   digivice-media-doctor [video-file]
# Writes: ~/.esp-handset/media-doctor.txt (+ /tmp/digivice-media-doctor.txt)

set +e
set -u

USER_HOME="${HOME:-/tmp}"
USER_NAME="$(id -un 2>/dev/null || echo '?')"
if [[ "$(id -u 2>/dev/null)" -eq 0 && -n "${SUDO_USER:-}" && "${SUDO_USER}" != "root" ]]; then
  CANDIDATE_HOME="$(getent passwd "$SUDO_USER" 2>/dev/null | cut -d: -f6)"
  if [[ -n "$CANDIDATE_HOME" ]]; then
    USER_HOME="$CANDIDATE_HOME"
    USER_NAME="$SUDO_USER"
  fi
fi

OUT_DIR="$USER_HOME/.esp-handset"
mkdir -p "$OUT_DIR" /tmp 2>/dev/null || true
OUT="$OUT_DIR/media-doctor.txt"
OUT2="/tmp/digivice-media-doctor.txt"
VIDEO="${1:-}"
PREFIX="${ESP_HANDSET_PREFIX:-/opt/esp-handset}"
MPV_LOG="$OUT_DIR/mpv-last.log"
FFPLAY_LOG="$OUT_DIR/ffplay-last.log"

show_file_tail() {
  local path="$1"
  local lines="${2:-160}"
  if [[ -f "$path" ]]; then
    echo "### $path"
    tail -n "$lines" "$path" 2>&1
  else
    echo "(missing: $path)"
  fi
}

{
  echo "=== digivice-media-doctor $(date -Iseconds) ==="
  echo "host=$(hostname 2>/dev/null || echo '?') user=$USER_NAME"
  echo "kernel=$(uname -a 2>/dev/null || echo '?')"
  echo "prefix=$PREFIX"
  echo "video_arg=${VIDEO:-"(none)"}"
  echo

  echo "--- deployed Digivice version ---"
  if [[ -f "$PREFIX/esp_handset/media_ui.py" ]]; then
    echo "media_ui=$PREFIX/esp_handset/media_ui.py"
    sha256sum "$PREFIX/esp_handset/media_ui.py" 2>&1 || true
  else
    echo "media_ui missing from $PREFIX"
  fi
  if [[ -f /etc/esp-handset/repo.path ]]; then
    REPO="$(tr -d '\r\n' </etc/esp-handset/repo.path 2>/dev/null)"
    echo "repo=$REPO"
    git -C "$REPO" log -1 --oneline 2>&1 || true
  else
    echo "repo path: /etc/esp-handset/repo.path missing"
  fi
  echo

  echo "--- player binaries ---"
  for player in mpv ffplay vlc ffprobe; do
    if command -v "$player" >/dev/null 2>&1; then
      echo "$player=$(command -v "$player")"
      case "$player" in
        mpv) mpv --version 2>&1 | head -n 8 ;;
        ffplay|ffprobe) "$player" -version 2>&1 | head -n 3 ;;
        vlc) vlc --version 2>&1 | head -n 3 ;;
      esac
    else
      echo "$player=MISSING"
    fi
  done
  echo

  echo "--- active player ---"
  pgrep -af '[m]pv|[f]fplay|[v]lc' 2>&1 || echo "(no active external player)"
  echo

  echo "--- last mpv log ---"
  show_file_tail "$MPV_LOG" 220
  echo
  echo "--- last ffplay log ---"
  show_file_tail "$FFPLAY_LOG" 220
  echo

  echo "--- USB topology ---"
  lsusb -t 2>&1 || echo "lsusb -t unavailable"
  echo
  lsusb 2>&1 || true
  echo
  lsblk -o NAME,TRAN,TYPE,FSTYPE,SIZE,RO,MOUNTPOINTS 2>&1 || true
  echo

  echo "--- system load / Pi health ---"
  uptime 2>&1 || true
  free -h 2>&1 || true
  if command -v vcgencmd >/dev/null 2>&1; then
    vcgencmd measure_temp 2>&1
    vcgencmd get_throttled 2>&1
    vcgencmd get_mem arm 2>&1
  else
    echo "vcgencmd=MISSING"
  fi
  echo

  if [[ -n "$VIDEO" ]]; then
    echo "--- requested video ---"
    if [[ -f "$VIDEO" ]]; then
      stat "$VIDEO" 2>&1 || true
      findmnt -T "$VIDEO" 2>&1 || true
      echo "### ffprobe stream details"
      ffprobe -v error \
        -show_entries stream=index,codec_name,profile,width,height,pix_fmt,bit_rate,r_frame_rate \
        -show_entries format=duration,size,bit_rate \
        -of default=noprint_wrappers=1 "$VIDEO" 2>&1 || true
    else
      echo "video does not exist: $VIDEO"
    fi
    echo
  else
    echo "--- requested video ---"
    echo "No video path supplied. Run: digivice-media-doctor /path/to/cart/video.mkv"
    echo
  fi

  echo "--- recent kernel USB/media messages ---"
  dmesg --time-format=iso --level=err,warn 2>&1 | tail -n 100 || true
  echo
  echo "=== end doctor ==="
} | tee "$OUT" | tee "$OUT2"

if [[ "$(id -u 2>/dev/null)" -eq 0 && -n "${SUDO_USER:-}" && "${SUDO_USER}" != "root" ]]; then
  chown "$SUDO_USER:$SUDO_USER" "$OUT" "$OUT2" 2>/dev/null || true
fi

echo
echo "Report: $OUT"
echo "Also:   $OUT2"
echo "Run with a file: digivice-media-doctor /media/.../video.mkv"
exit 0
