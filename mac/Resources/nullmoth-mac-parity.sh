#!/bin/bash
# Read-only checks of the Mac features that depend on how this PC presents itself, and an opt-in sleep profile.
#
#   nullmoth-mac-parity.sh identity        Apple services: serial, ROM against the primary network adapter, en0
#   nullmoth-mac-parity.sh power check     the sleep settings in effect and what the profile would change
#   nullmoth-mac-parity.sh power apply     (root) write the profile, after saving the previous values
#   nullmoth-mac-parity.sh power restore   (root) put the saved values back
#
# identity and power check change nothing. power apply is never run by the installer; it is a switch the user turns on.
# Exit status: 0 nothing to report, 1 something to report, 2 bad usage or not root.
set -u
PATH=$PATH:/usr/bin:/usr/sbin:/bin:/sbin   # a launchd job has a short PATH; the caller's tools win
STATE_DIR=${NULLMOTH_STATE_DIR:-/Library/NullMoth}
BACKUP="$STATE_DIR/power-profile.backup"
ROM_GUID=4D1EDE05-38C7-4A6A-9CC6-4BCCA8B38C14
problems=0

say() { printf '%s\n' "$1"; }
bad() { say "PROBLEM $1"; problems=1; }
ok() { say "ok      $1"; }

# nvram prints a value with bytes outside printable ASCII as %xx; this turns that back into twelve hex digits.
rom_hex() {
  local raw
  raw=$(nvram "$ROM_GUID:ROM" 2>/dev/null | sed -e 's/^[^\t]*\t//') || return 1
  [ -n "$raw" ] || return 1
  local out="" i c
  for ((i = 0; i < ${#raw}; i++)); do
    c=${raw:$i:1}
    if [ "$c" = "%" ]; then out+=${raw:$((i + 1)):2}; i=$((i + 2)); else out+=$(printf '%02x' "'$c"); fi
  done
  printf '%s' "$out" | tr 'A-F' 'a-f'
}

identity() {
  local serial mac rom
  serial=$(ioreg -rd1 -c IOPlatformExpertDevice 2>/dev/null | awk -F'"' '/IOPlatformSerialNumber/{print $4; exit}')
  case "$serial" in
    "") bad "no serial number is reported: iCloud, iMessage and the App Store cannot sign in" ;;
    A0000000009|A000000000000000Z|W00000000001|W00000000000) bad "the serial number $serial is a placeholder shared by every PC that has it" ;;
    *) if [[ "$serial" =~ ^[A-Z0-9]{10,12}$ ]]; then ok "serial number $serial has an Apple serial's shape"; else bad "the serial number $serial is not the shape of an Apple serial (10 to 12 letters and digits)"; fi ;;
  esac
  mac=$(ifconfig en0 2>/dev/null | awk '/ether/{print $2; exit}')
  if [ -z "$mac" ]; then
    bad "there is no en0 interface: Apple counts a Mac's accounts by en0"
  else
    ok "en0 is $mac"
    rom=$(rom_hex)
    if [ -z "$rom" ]; then
      bad "the ROM is not set in NVRAM, so iMessage and FaceTime have no hardware address to register"
    elif [ "$rom" = "$(printf '%s' "$mac" | tr -d ':' | tr 'A-F' 'a-f')" ]; then
      ok "the ROM equals en0's address, as on a real Mac"
    else
      bad "the ROM $rom differs from en0's address $mac. A real Mac reports its own; rebuild the EFI with en0's address as the ROM"
    fi
  fi
  if networksetup -listallhardwareports 2>/dev/null | awk '/Device: en0/{f=1} END{exit !f}'; then
    ok "en0 is a network port macOS lists"
  fi
}

model_kind() { case "$(sysctl -n hw.model 2>/dev/null)" in MacBook*) echo laptop ;; *) echo desktop ;; esac; }

# The sleep settings OpenCore's post-install sleep guide turns off because PC firmware mishandles the wake they cause.
# Desktop-only: hibernatemode 0 (a PC drive is not a Mac's, so resume from the sleep image fails).
profile_keys() { echo "powernap standby autopoweroff proximitywake"; [ "$(model_kind)" = desktop ] && echo "hibernatemode"; }
profile_want() { echo 0; }

current() { pmset -g custom 2>/dev/null | awk -v k="$1" '$1==k{print $2; exit}'; }

power_check() {
  local k cur
  for k in $(profile_keys | tr '\n' ' '); do
    cur=$(current "$k")
    if [ -z "$cur" ]; then say "n/a     $k is not a setting on this Mac"
    elif [ "$cur" = "$(profile_want)" ]; then ok "$k is already 0"
    else say "differs $k is $cur; the sleep profile sets it to 0"; problems=1; fi
  done
}

power_apply() {
  [ "$(id -u)" = 0 ] || { say "power apply needs root"; exit 2; }
  mkdir -p "$STATE_DIR" || exit 2
  [ -f "$BACKUP" ] || : >"$BACKUP"
  local k cur
  for k in $(profile_keys | tr '\n' ' '); do
    cur=$(current "$k")
    [ -n "$cur" ] || continue
    grep -q "^$k " "$BACKUP" || echo "$k $cur" >>"$BACKUP"
    pmset -a "$k" "$(profile_want)" && say "set     $k $cur -> 0"
  done
}

power_restore() {
  [ "$(id -u)" = 0 ] || { say "power restore needs root"; exit 2; }
  [ -s "$BACKUP" ] || { say "no saved settings: nothing to restore"; exit 0; }
  local k v
  while read -r k v; do
    [ -n "$k" ] && pmset -a "$k" "$v" && say "restored $k $v"
  done <"$BACKUP"
  rm -f "$BACKUP"
}

case "${1:-}" in
  identity) identity ;;
  power) case "${2:-}" in check) power_check ;; apply) power_apply ;; restore) power_restore ;; *) say "usage: $0 power check|apply|restore"; exit 2 ;; esac ;;
  *) say "usage: $0 identity | power check|apply|restore"; exit 2 ;;
esac
exit "$problems"
