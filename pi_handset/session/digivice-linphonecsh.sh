#!/usr/bin/env bash
# Stable entry Digivice always calls for VoIP (PATH: /usr/local/bin).
# Finds the real linphonecsh wherever apt put it.
set +e
REAL=""
for hint in /etc/esp-handset/linphone.bin "${HOME}/.esp-handset/linphone.bin"; do
  if [[ -f "$hint" ]]; then
    cand="$(tr -d '[:space:]' <"$hint" 2>/dev/null || true)"
    if [[ -n "$cand" && -e "$cand" && -x "$cand" ]]; then
      REAL="$cand"
      break
    fi
  fi
done
if [[ -z "$REAL" ]]; then
  for cand in \
    /usr/bin/linphonecsh \
    /usr/local/bin/linphonecsh \
    "$(command -v linphonecsh 2>/dev/null)"
  do
    [[ -z "$cand" ]] && continue
    [[ "$cand" == *digivice-linphonecsh* ]] && continue
    if [[ -e "$cand" && -x "$cand" ]]; then
      REAL="$cand"
      break
    fi
  done
fi
if [[ -z "$REAL" ]] && command -v dpkg >/dev/null 2>&1; then
  REAL="$(dpkg -L linphone-cli 2>/dev/null | grep '/linphonecsh$' | head -n1 || true)"
fi
if [[ -z "$REAL" || ! -e "$REAL" ]]; then
  echo "digivice-linphonecsh: linphonecsh not found (install linphone-cli)" >&2
  exit 127
fi
# Keep hints fresh
mkdir -p /etc/esp-handset "${HOME}/.esp-handset" 2>/dev/null || true
echo "$REAL" >/etc/esp-handset/linphone.bin 2>/dev/null || true
echo "$REAL" >"${HOME}/.esp-handset/linphone.bin" 2>/dev/null || true
exec "$REAL" "$@"
