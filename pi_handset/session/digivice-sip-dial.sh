#!/usr/bin/env bash
# Place one outbound Zadarma/SIP call the same way Windows Linphone does:
#   1) start linphonec with a UDP account config
#   2) register
#   3) dial 1XXXXXXXXXX through the proxy
#
# Usage: digivice-sip-dial 15551234567
# Prints log lines; ends with OK or FAIL: reason
set +e
export PATH="/usr/local/bin:/usr/bin:/bin:${PATH:-}"
NUM="${1:-}"
LOG="${HOME}/.esp-handset/sip-last.log"
mkdir -p "${HOME}/.esp-handset"
log() { echo "[sip-dial] $*" | tee -a "$LOG"; }

if [[ -z "$NUM" ]]; then
  echo "FAIL: no number"
  exit 2
fi

# Keep digits (and leading +)
NUM="$(echo "$NUM" | tr -cd '0-9+')"
if [[ "$NUM" == +* ]]; then
  NUM="${NUM#+}"
fi
# 10-digit NANP → 1 + number
if [[ "$NUM" =~ ^[2-9][0-9]{9}$ ]]; then
  NUM="1${NUM}"
fi

CSH=""
for cand in \
  /usr/local/bin/digivice-linphonecsh \
  /usr/bin/linphonecsh \
  /usr/local/bin/linphonecsh
do
  if [[ -x "$cand" ]]; then CSH="$cand"; break; fi
done
if [[ -z "$CSH" ]]; then
  echo "FAIL: linphonecsh missing"
  exit 3
fi

SIP_SERVER="" SIP_USER="" SIP_PASS=""
for envf in \
  "${HOME}/.esp-handset/sip.env" \
  /etc/esp-handset/sip.env
do
  if [[ -r "$envf" ]]; then
    # shellcheck disable=SC1090
    set -a
    # grep only KEY=VAL lines
    eval "$(grep -E '^(SIP_SERVER|SIP_USER|SIP_PASS|SIP_DISPLAY|SIP_DID)=' "$envf" | sed 's/\r$//')"
    set +a
    [[ -n "$SIP_USER" && -n "$SIP_SERVER" ]] && break
  fi
done
if [[ -z "$SIP_USER" || -z "$SIP_SERVER" || -z "$SIP_PASS" ]]; then
  echo "FAIL: sip.env missing user/server/pass"
  exit 4
fi

RC="${HOME}/.esp-handset/linphonerc"
cat >"$RC" <<EOF
[sip]
sip_port=5060
sip_tcp_port=-1
sip_tls_port=-1
use_info=0
guess_hostname=1
inc_timeout=30
use_ipv6=0
default_proxy=0
display_name=${SIP_DISPLAY:-Digivice}

[rtp]
audio_rtp_port=7078
audio_jitt_comp=60
nortp_timeout=30

[net]
stun_server=stun.zadarma.com
firewall_policy=2
nat_policy_ref=nat_policy_0
mtu=1300

[nat_policy_0]
stun_server=stun.zadarma.com
stun_enabled=1
ice_enabled=0
turn_enabled=0
protocols=stun

[audio_codec_0]
mime=PCMU
rate=8000
channels=1
enabled=1

[audio_codec_1]
mime=PCMA
rate=8000
channels=1
enabled=1

[audio_codec_2]
mime=opus
rate=48000
channels=2
enabled=0

[auth_info_0]
username=${SIP_USER}
userid=${SIP_USER}
passwd=${SIP_PASS}
realm=${SIP_SERVER}
domain=${SIP_SERVER}

[proxy_0]
reg_proxy=<sip:${SIP_SERVER};transport=udp>
reg_identity=sip:${SIP_USER}@${SIP_SERVER}
reg_expires=120
reg_sendregister=1
publish=0
dial_escape_plus=0
EOF
chmod 600 "$RC" 2>/dev/null || true

log "csh=$CSH user=$SIP_USER host=$SIP_SERVER num=$NUM"
"$CSH" exit >/dev/null 2>&1
sleep 0.4
INIT_OUT="$("$CSH" init -c "$RC" 2>&1)"
log "init -c → ${INIT_OUT:0:120}"
sleep 0.8
ALIVE="$("$CSH" status register 2>&1)"
if echo "$ALIVE" | grep -qiE 'no running|not running|failed to connect'; then
  INIT_OUT="$("$CSH" init 2>&1)"
  log "init (no -c) → ${INIT_OUT:0:120}"
  sleep 0.6
fi

REG_OUT="$("$CSH" register --username "$SIP_USER" --host "$SIP_SERVER" --password "$SIP_PASS" 2>&1)"
log "register flags → ${REG_OUT:0:160}"
sleep 0.5
ST="$("$CSH" status register 2>&1)"
log "status1 → ${ST:0:120}"
if ! echo "$ST" | grep -qiE 'identity|registered to'; then
  REG_OUT="$("$CSH" generic "register sip:${SIP_USER}@${SIP_SERVER} ${SIP_SERVER} ${SIP_PASS}" 2>&1)"
  log "register generic → ${REG_OUT:0:160}"
  sleep 1
  ST="$("$CSH" status register 2>&1)"
  log "status2 → ${ST:0:120}"
fi

# Wait up to ~6s for REGISTER 401→OK
for i in 1 2 3 4 5 6 7 8; do
  ST="$("$CSH" status register 2>&1)"
  if echo "$ST" | grep -qiE 'identity=|registered to|RegistrationOk'; then
    log "registered ($i) → ${ST:0:120}"
    break
  fi
  if echo "$ST" | grep -q 'registered=-1' && [[ "$i" -gt 3 ]]; then
    log "still registered=-1"
  fi
  sleep 0.6
done
ST="$("$CSH" status register 2>&1)"
if echo "$ST" | grep -q 'registered=-1' && ! echo "$ST" | grep -qi identity; then
  echo "FAIL: not registered (${ST:0:60})"
  exit 5
fi

TARGET="sip:${NUM}@${SIP_SERVER}"
log "dial $NUM  and  $TARGET"
DIAL_OUT="$("$CSH" dial "$NUM" 2>&1)"
log "dial digits → ${DIAL_OUT:0:160}"
sleep 0.4
CALL="$("$CSH" status call 2>&1)"
log "call1 → ${CALL:0:160}"
if echo "$CALL" | grep -qiE 'No active call|no call|idle'; then
  DIAL_OUT="$("$CSH" dial "$TARGET" 2>&1)"
  log "dial uri → ${DIAL_OUT:0:160}"
  sleep 0.4
  CALL="$("$CSH" status call 2>&1)"
  log "call2 → ${CALL:0:160}"
fi
if echo "$CALL" | grep -qiE 'No active call|no call' || [[ -z "$CALL" ]]; then
  DIAL_OUT="$("$CSH" generic "call ${TARGET}" 2>&1)"
  log "generic call → ${DIAL_OUT:0:160}"
  sleep 0.5
  CALL="$("$CSH" status call 2>&1)"
  log "call3 → ${CALL:0:160}"
fi

if echo "$CALL" | grep -qiE 'Outgoing|Ringing|Connected|StreamsRunning|Early|sip:'; then
  echo "OK"
  exit 0
fi
# Empty/ok from dial with no 'no call' is still a start
if ! echo "$CALL" | grep -qiE 'No active call|no call'; then
  echo "OK"
  exit 0
fi
echo "FAIL: no call (${CALL:0:80})"
exit 6
