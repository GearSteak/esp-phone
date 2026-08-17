#!/usr/bin/env bash
# Stable entry Digivice always calls for linphonec (PATH: /usr/local/bin).
set +e
REAL=""
for hint in /etc/esp-handset/linphonec.bin "${HOME}/.esp-handset/linphonec.bin"; do
  if [[ -f "$hint" ]]; then
    cand="$(tr -d '[:space:]' <"$hint" 2>/dev/null || true)"
    if [[ -n "$cand" && -e "$cand" ]]; then
      REAL="$cand"
      break
    fi
  fi
done
if [[ -z "$REAL" ]]; then
  for cand in \
    /usr/bin/linphonec \
    /usr/local/bin/linphonec \
    /usr/bin/linphone-daemon \
    "$(command -v linphonec 2>/dev/null)" \
    "$(command -v linphone-daemon 2>/dev/null)"
  do
    [[ -z "$cand" ]] && continue
    [[ "$cand" == *digivice-linphonec* ]] && continue
    if [[ -e "$cand" ]]; then
      REAL="$cand"
      break
    fi
  done
fi
if [[ -z "$REAL" ]] && command -v dpkg >/dev/null 2>&1; then
  REAL="$(dpkg -L linphone-cli linphone-nogtk linphone 2>/dev/null \
    | grep -E '/linphonec$|/linphone-daemon$' | head -n1 || true)"
fi
if [[ -z "$REAL" || ! -e "$REAL" ]]; then
  echo "digivice-linphonec: linphonec not found (install linphone-cli)" >&2
  exit 127
fi
mkdir -p /etc/esp-handset "${HOME}/.esp-handset" 2>/dev/null || true
echo "$REAL" >/etc/esp-handset/linphonec.bin 2>/dev/null || true
echo "$REAL" >"${HOME}/.esp-handset/linphonec.bin" 2>/dev/null || true
exec "$REAL" "$@"
