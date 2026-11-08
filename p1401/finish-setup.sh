#!/bin/bash
# 1401: finish a new macOS install without the setup screens.
#
# Run it in macOS Recovery (Utilities > Terminal), with the 1401 stick plugged in:
#     sh /Volumes/1401/NullMoth/finish-setup.sh
#
# Without a graphics driver, macOS 26 cannot draw its first setup screens (the language chooser, Setup Assistant):
# the screen stays black with only a cursor, and the NVIDIA driver can only be installed once macOS is running. This
# makes the first account on the installed system and marks setup as done, so the next start goes to the desktop, where
# the 1401 Mac app installs the driver. It changes nothing on a system that already has an account.
#
# Options (for support): --data <mounted Data volume>   --user <short name>   --name <full name>   --no-autologin
set -u
# Recovery's own PATH first (it is the only one there); the system folders are added in case it is empty
PATH=${PATH:+$PATH:}/usr/bin:/bin:/usr/sbin:/sbin

DATA=""; SHORT=""; FULL=""; AUTOLOGIN=1
while [ $# -gt 0 ]; do
  case "$1" in
    --data) DATA="${2:-}"; shift 2;;
    --user) SHORT="${2:-}"; shift 2;;
    --name) FULL="${2:-}"; shift 2;;
    --no-autologin) AUTOLOGIN=0; shift;;
    *) echo "unknown option: $1"; exit 2;;
  esac
done

say() { echo "1401: $*"; }
stop() { echo "1401: STOP $*"; echo "1401: nothing was changed."; exit 1; }

# --- the installed system's Data volume -------------------------------------------------------------------------------
if [ -z "$DATA" ]; then
  # Every APFS volume with the Data role, by device (names carry Unicode isolation marks in newer diskutil output).
  devs=$(diskutil apfs list 2>/dev/null | sed -n 's/.*APFS Volume Disk (Role): *\(disk[0-9]*s[0-9]*\) (Data).*/\1/p')
  [ -n "$devs" ] || stop "no macOS Data volume found (diskutil apfs list shows none). Install macOS first, then run this again."
  found=""
  for dev in $devs; do
    mp=$(diskutil info "$dev" 2>/dev/null | sed -n 's/^ *Mount Point: *//p')
    if [ -z "$mp" ]; then diskutil mount "$dev" >/dev/null 2>&1; mp=$(diskutil info "$dev" 2>/dev/null | sed -n 's/^ *Mount Point: *//p'); fi
    # Recovery's own volumes and the running system are not an install to finish
    case "$mp" in ''|/|/System/Volumes/*) continue;; esac
    [ -d "$mp/private/var/db" ] && found="$found
$mp"
  done
  found=$(echo "$found" | sed '/^$/d')
  count=$(echo "$found" | sed '/^$/d' | wc -l | tr -d ' ')
  [ "$count" -ge 1 ] || stop "the macOS Data volume did not mount. If FileVault is on, unlock it in Disk Utility first."
  if [ "$count" -gt 1 ]; then
    say "more than one macOS install is on this Mac:"; echo "$found" | sed 's/^/    /'
    printf "1401: type the one to finish (as shown above): "; read -r pick
    echo "$found" | grep -qxF "$pick" || stop "\"$pick\" is not one of them."
    found=$pick
  fi
  DATA=$found
fi
[ -d "$DATA/private/var/db" ] || stop "$DATA is not a macOS Data volume (no private/var/db)."
NODE="$DATA/private/var/db/dslocal/nodes/Default"
[ -d "$NODE/users" ] || stop "$DATA has no local account database yet. Start the installed macOS once, then run this again."

# --- nothing to do on a system that is already set up ----------------------------------------------------------------
if [ -e "$DATA/private/var/db/.AppleSetupDone" ]; then
  stop "setup on $DATA is already finished (it has .AppleSetupDone). Log in with your account."
fi
for f in "$NODE"/users/*.plist; do
  [ -f "$f" ] || continue
  id=$(dscl -f "$NODE" localhost -read "/Local/Default/Users/$(basename "$f" .plist)" UniqueID 2>/dev/null | awk '{print $2}')
  case "$id" in ''|*[!0-9]*) continue;; esac
  [ "$id" -ge 501 ] && [ "$id" -lt 1000 ] && stop "$DATA already has an account ($(basename "$f" .plist)). Log in with it."
done

# --- the account ---------------------------------------------------------------------------------------------------
if [ -z "$SHORT" ]; then printf "1401: account name (lower case, no spaces, e.g. alex): "; read -r SHORT; fi
# grep in the C locale: a bash [a-z] follows the locale's collation, where it also matched "Alex"
printf '%s' "$SHORT" | LC_ALL=C grep -qE '^[a-z0-9._-]+$' || stop "the account name must be lower-case letters, digits, '.', '_' or '-'."
printf '%s' "$SHORT" | LC_ALL=C grep -qE '^[a-z]' || stop "the account name must start with a letter."
[ ${#SHORT} -le 31 ] || stop "the account name is longer than 31 characters."
case "$SHORT" in root|daemon|nobody|admin|staff|wheel|guest) stop "\"$SHORT\" is a name macOS uses itself.";; esac
if [ -z "$FULL" ]; then printf "1401: full name (Enter for %s): " "$SHORT"; read -r FULL; fi
[ -n "$FULL" ] || FULL=$SHORT
printf "1401: password: "; stty -echo 2>/dev/null; read -r PW; stty echo 2>/dev/null; echo
printf "1401: the same password again: "; stty -echo 2>/dev/null; read -r PW2; stty echo 2>/dev/null; echo
[ "$PW" = "$PW2" ] || stop "the two passwords differ."
[ -n "$PW" ] || stop "the password is empty."

U="/Local/Default/Users/$SHORT"
GUID=$(od -An -N16 -tx1 /dev/urandom | tr -d ' \n' | sed 's/^\(........\)\(....\)\(....\)\(....\)\(............\)$/\1-\2-\3-\4-\5/' | tr a-f A-F)
d() { dscl -f "$NODE" localhost "$@" || { echo "1401: dscl $* failed"; FAILED=1; }; }
FAILED=0
d -create "$U"
d -create "$U" UserShell /bin/zsh
d -create "$U" RealName "$FULL"
d -create "$U" UniqueID 501
d -create "$U" PrimaryGroupID 20
d -create "$U" NFSHomeDirectory "/Users/$SHORT"
d -create "$U" GeneratedUID "$GUID"
d -passwd "$U" "$PW"
d -append /Local/Default/Groups/admin GroupMembership "$SHORT"
if [ "$FAILED" != 0 ]; then
  dscl -f "$NODE" localhost -delete "$U" >/dev/null 2>&1
  stop "the account could not be written; the partial account was removed."
fi
mkdir -p "$DATA/Users/$SHORT" && chown 501:20 "$DATA/Users/$SHORT" && chmod 755 "$DATA/Users/$SHORT" \
  || say "NOTE: the home folder could not be made; macOS makes it at the first login."

# --- straight to the desktop ------------------------------------------------------------------------------------------
# The login window is drawn by the same missing driver: it can stay black too. Logging in automatically skips it, so
# the desktop and the 1401 Mac app come up by themselves. kcpassword is the password XOR macOS's fixed 11-byte key,
# NUL-terminated and padded to a multiple of 12 bytes. Turn it off later in System Settings > Users & Groups.
if [ "$AUTOLOGIN" = 1 ]; then
  key="125 137 82 35 210 188 221 234 163 185 31"
  bytes=$(printf '%s' "$PW" | od -An -tu1 | tr -s ' \n' ' ')
  n=$(echo $bytes | wc -w | tr -d ' ')
  pad=$(( 12 - (n % 12) ))
  i=0; out=""
  set -- $key; k=("$@")
  for b in $bytes $(yes 0 | head -n "$pad"); do
    out="$out$(printf '\\%03o' $(( b ^ ${k[$((i % 11))]} )))"
    i=$((i + 1))
  done
  printf "$out" > "$DATA/private/etc/kcpassword" && chmod 600 "$DATA/private/etc/kcpassword" && chown 0:0 "$DATA/private/etc/kcpassword" \
    && defaults write "$DATA/Library/Preferences/com.apple.loginwindow" autoLoginUser "$SHORT" \
    && say "this account logs in by itself at start-up" \
    || say "NOTE: automatic login could not be set; at the login window click the middle of the screen, type the password, press Enter."
fi

touch "$DATA/private/var/db/.AppleSetupDone" || stop "could not mark setup as done."
say "done: account \"$SHORT\" (an administrator) on ${DATA#/Volumes/}. Restart and choose macOS."
say "then install the NVIDIA driver with the 1401 Mac app."
exit 0
