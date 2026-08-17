#!/usr/bin/env bash
# Stable entry Digivice always calls for VoIP (PATH: /usr/local/bin).
# Finds the *real* linphonecsh — never exec this wrapper from a pin file.
set +e
is_wrapper() {
  local p="$1" r
  [[ -z "$p" ]] && return 0
  [[ "$p" == *digivice-linphonecsh* ]] && return 0
  r="$(readlink -f "$p" 2>/dev/null || echo "$p")"
  [[ "$r" == *digivice-linphonecsh* ]] && return 0
  return 1
}

REAL=""
for hint in /etc/esp-handset/linphone.bin "${HOME}/.esp-handset/linphone.bin"; do
  if [[ -f "$hint" ]]; then
    cand="$(tr -d '[:space:]' <"$hint" 2>/dev/null || true)"
    if [[ -n "$cand" && -e "$cand" ]] && ! is_wrapper "$cand"; then
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
    [[ -z "$cand" || ! -e "$cand" ]] && continue
    is_wrapper "$cand" && continue
    REAL="$cand"
    break
  done
fi
if [[ -z "$REAL" ]] && command -v dpkg >/dev/null 2>&1; then
  REAL="$(dpkg -L linphone-cli linphone-nogtk linphone 2>/dev/null \
    | grep '/linphonecsh$' | grep -v digivice | head -n1 || true)"
  [[ -n "$REAL" && -e "$REAL" ]] || REAL=""
  if is_wrapper "$REAL"; then REAL=""; fi
fi
if [[ -z "$REAL" ]]; then
  REAL="$(find /usr/bin /usr/local/bin /usr/lib /usr/libexec -name linphonecsh 2>/dev/null \
    | grep -v digivice | head -n1 || true)"
fi
if [[ -z "$REAL" || ! -e "$REAL" ]] || is_wrapper "$REAL"; then
  echo "digivice-linphonecsh: linphonecsh not found (install linphone-cli)" >&2
  exit 127
fi
mkdir -p /etc/esp-handset "${HOME}/.esp-handset" 2>/dev/null || true
echo "$REAL" >/etc/esp-handset/linphone.bin 2>/dev/null || true
echo "$REAL" >"${HOME}/.esp-handset/linphone.bin" 2>/dev/null || true
exec "$REAL" "$@"
