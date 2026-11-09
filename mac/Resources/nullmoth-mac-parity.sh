#!/bin/bash
# Read-only checks of the Mac features that depend on how this PC presents itself, and an opt-in sleep profile.
#
#   nullmoth-mac-parity.sh identity        Apple services: serial, ROM against the primary network adapter, en0
#   nullmoth-mac-parity.sh power check     the sleep settings in effect and what the profile would change
#   nullmoth-mac-parity.sh power apply     (root) write the profile, after saving the previous values
#   nullmoth-mac-parity.sh power restore   (root) put the saved values back
#   nullmoth-mac-parity.sh gamemode status|on|off   Game Mode's device check: on/off need root; see the notes at gamemode()
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

# Game Mode, as a DIAGNOSTIC. macOS's game policy daemon decides at start-up whether this Mac supports four things: Game
# Mode, model-manager game assertions, dynamic power splitting and sustained execution. On an Intel Mac's build of the
# daemon the Game Mode answer is a fixed "no" and the other three ask a MobileGestalt device-type list. The daemon also reads
# one preference, ignoreDeviceRestrictions, and treats every one of the four as supported when it is true.
# That preference CANNOT turn on Game Mode alone. Read from the Intel daemon's code: when forced, dynamic power splitting
# and sustained execution each ask Apple's closed-loop performance controller (CLPCPolicyInterface) for a client, which an
# Intel kernel does not have; the daemon turns the failure into a thrown Swift error and what its caller does with it was not
# determined, so a restart loop is possible. Model-manager assertions are a process-state assertion for Apple's model
# service and have no effect without it. Because the harm could not be ruled out, this stays a command the user types, never
# something an installer does. The kernel setting Game Mode relies on (kern.console_mode) does not exist on this kernel
# either, so the working path is nullmoth-gamemode-policy.py. A narrower gate exists in the daemon (one two-byte answer, see
# tools/gamemode_gate_probe.py) but patching Apple's daemon in memory is not shipped.
GM_DOMAIN=${NULLMOTH_GM_DOMAIN:-/Library/Preferences/com.apple.gamepolicyd}
gamemode() {
  case "${1:-}" in
    status)
      v=$(defaults read "$GM_DOMAIN" ignoreDeviceRestrictions 2>/dev/null)
      if [ "$v" = 1 ]; then say "on      ignoreDeviceRestrictions is set in $GM_DOMAIN"; else say "off     ignoreDeviceRestrictions is not set in $GM_DOMAIN"; problems=1; fi ;;
    on|off)
      [ "$(id -u)" = 0 ] || { say "gamemode $1 needs root"; exit 2; }
      if [ "$1" = on ]; then defaults write "$GM_DOMAIN" ignoreDeviceRestrictions -bool true; else defaults delete "$GM_DOMAIN" ignoreDeviceRestrictions 2>/dev/null; fi
      killall gamepolicyd 2>/dev/null   # launchd starts it again and it reads the preference
      say "gamemode $1: the daemon was restarted" ;;
    *) say "usage: $0 gamemode status|on|off"; exit 2 ;;
  esac
}

case "${1:-}" in
  identity) identity ;;
  gamemode) gamemode "${2:-}" ;;
  power) case "${2:-}" in check) power_check ;; apply) power_apply ;; restore) power_restore ;; *) say "usage: $0 power check|apply|restore"; exit 2 ;; esac ;;
  *) say "usage: $0 identity | power check|apply|restore | gamemode status|on|off"; exit 2 ;;
esac
exit "$problems"
