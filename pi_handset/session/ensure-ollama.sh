#!/usr/bin/env bash
# Install Ollama + pull a small chat model for Digivice Tools → AI.
#
#   sudo digivice-ensure-ollama
#   sudo digivice-ensure-ollama --foreground-pull   # wait for model download
#   sudo digivice-ensure-ollama --skip-pull
#
set -u
set +e

LOG_DIR="${HOME:-/tmp}/.esp-handset"
[[ "$(id -u)" -eq 0 && -n "${SUDO_USER:-}" ]] && \
  LOG_DIR="$(getent passwd "$SUDO_USER" | cut -d: -f6)/.esp-handset"
mkdir -p "$LOG_DIR" /etc/esp-handset 2>/dev/null || true
LOG="$LOG_DIR/ollama-ensure.log"
PULL_LOG="$LOG_DIR/ollama-pull.log"
STATUS_FILE="/etc/esp-handset/ollama.status"
ENV_FILE="/etc/esp-handset/ollama.env"
HOST="${DIGIVICE_OLLAMA_HOST:-http://127.0.0.1:11434}"
FOREGROUND_PULL=0
SKIP_PULL=0

for a in "$@"; do
  case "$a" in
    --foreground-pull) FOREGROUND_PULL=1 ;;
    --skip-pull) SKIP_PULL=1 ;;
  esac
done

log() { echo "[ensure-ollama] $*" | tee -a "$LOG" >&2; }

write_status() {
  echo "$1" >"$STATUS_FILE" 2>/dev/null || true
  chmod 644 "$STATUS_FILE" 2>/dev/null || true
}

mem_total_kb() {
  awk '/MemTotal:/ {print $2; exit}' /proc/meminfo 2>/dev/null || echo 0
}

pick_model() {
  local mem="$1" m="${DIGIVICE_OLLAMA_MODEL:-}"
  if [[ -n "$m" ]]; then
    echo "$m"
    return 0
  fi
  if [[ -f "$ENV_FILE" ]]; then
    m="$(grep -E '^OLLAMA_MODEL=' "$ENV_FILE" 2>/dev/null | head -n1 | cut -d= -f2- | tr -d '\r\"'"'"' ')"
    if [[ -n "$m" ]]; then
      echo "$m"
      return 0
    fi
  fi
  # Pi 4 2GB target: small fast chat model (~1.3 GB on disk)
  if [[ "$mem" -lt 1500000 ]]; then
    echo "qwen2.5:0.5b"
  elif [[ "$mem" -lt 3500000 ]]; then
    echo "llama3.2:1b"
  else
    echo "llama3.2:3b"
  fi
}

have_ollama() {
  command -v ollama >/dev/null 2>&1
}

api_up() {
  curl -sf --max-time 3 "${HOST}/api/tags" >/dev/null 2>&1
}

model_present() {
  local model="$1"
  curl -sf --max-time 5 "${HOST}/api/tags" 2>/dev/null \
    | grep -q "\"name\":\"${model}\"" && return 0
  curl -sf --max-time 5 "${HOST}/api/tags" 2>/dev/null \
    | grep -q "\"name\":\"${model%:*}:latest\"" && return 0
  ollama list 2>/dev/null | awk '{print $1}' | grep -qx "$model" && return 0
  return 1
}

write_env() {
  local model="$1"
  if [[ -f "$ENV_FILE" ]] && grep -q '^OLLAMA_MODEL=' "$ENV_FILE" 2>/dev/null; then
    log "keep existing $ENV_FILE"
    return 0
  fi
  cat >"$ENV_FILE" <<EOF
# Digivice AI (Tools → AI) — written by digivice-ensure-ollama
OLLAMA_HOST=${HOST}
OLLAMA_MODEL=${model}
EOF
  chmod 644 "$ENV_FILE" 2>/dev/null || true
  log "wrote $ENV_FILE (model=$model)"
}

install_ollama() {
  if have_ollama; then
    log "ollama already installed: $(command -v ollama)"
    return 0
  fi
  log "installing Ollama (official script)…"
  if ! command -v curl >/dev/null 2>&1; then
    export DEBIAN_FRONTEND=noninteractive
    apt-get install -y curl ca-certificates >/dev/null 2>&1 || true
  fi
  if ! curl -fsSL https://ollama.com/install.sh | sh 2>&1 | tee -a "$LOG"; then
    log "WARN: Ollama install script failed"
    return 1
  fi
  have_ollama && log "ollama installed: $(command -v ollama)" && return 0
  return 1
}

start_service() {
  if systemctl list-unit-files ollama.service >/dev/null 2>&1; then
    systemctl enable ollama.service 2>/dev/null || true
    systemctl start ollama.service 2>/dev/null || true
  fi
  local i
  for i in $(seq 1 30); do
    api_up && return 0
    sleep 1
  done
  log "starting ollama serve (fallback)…"
  if ! pgrep -x ollama >/dev/null 2>&1; then
    nohup ollama serve >>"$LOG" 2>&1 &
    sleep 2
  fi
  for i in $(seq 1 20); do
    api_up && return 0
    sleep 1
  done
  return 1
}

do_pull() {
  local model="$1"
  if model_present "$model"; then
    log "model already present: $model"
    write_status "ok $model"
    return 0
  fi
  log "pulling model $model (may take several minutes)…"
  if [[ "$FOREGROUND_PULL" -eq 1 ]]; then
    if ollama pull "$model" 2>&1 | tee -a "$PULL_LOG"; then
      write_status "ok $model"
      return 0
    fi
    write_status "pull-failed $model"
    return 1
  fi
  (
    echo "=== pull $model $(date -Is 2>/dev/null || date) ===" >>"$PULL_LOG"
    ollama pull "$model" >>"$PULL_LOG" 2>&1
    ec=$?
    if [[ "$ec" -eq 0 ]]; then
      echo "ok $model" >"$STATUS_FILE"
    else
      echo "pull-failed $model" >"$STATUS_FILE"
    fi
  ) &
  disown 2>/dev/null || true
  write_status "pulling $model"
  log "model pull running in background — log: $PULL_LOG"
  return 0
}

if [[ "$(id -u)" -ne 0 ]]; then
  log "need root (try: sudo digivice-ensure-ollama)"
  exit 1
fi

MEM="$(mem_total_kb)"
MODEL="$(pick_model "$MEM")"
log "=== start mem=${MEM}kB model=$MODEL ==="

if [[ "$MEM" -lt 900000 ]]; then
  log "WARN: <1 GB RAM — Ollama not recommended; skipping install"
  write_status "skip-low-ram"
  exit 0
fi

if ! install_ollama; then
  write_status "install-failed"
  exit 1
fi

write_env "$MODEL"

if ! start_service; then
  log "WARN: Ollama API not up yet"
  write_status "service-down"
  exit 1
fi

if [[ "$SKIP_PULL" -eq 1 ]]; then
  write_status "ok-no-pull"
  log "skip pull (--skip-pull)"
  exit 0
fi

do_pull "$MODEL"
log "done — Tools → AI · model $MODEL · status: $(cat "$STATUS_FILE" 2>/dev/null)"
exit 0
