#!/bin/bash
# nullmoth-ryzen-power.sh: a power-limit profile for Ryzen laptops, applied at every start and refreshed while running.
#
# A Ryzen laptop under macOS runs at the firmware's default limits, which are tuned for Windows' power plans and run hot
# and loud on a battery. This installs a small LaunchDaemon that calls RyzenAdj (https://github.com/FlyGoat/RyzenAdj, LGPL)
# with limits you choose. RyzenAdj is not shipped here: give your own build with --ryzenadj and its SHA-256 with --sha256
# (it must be listed in ryzenadj.sha256 beside this script; no other build is installed). The job runs as root every 30 s, so the build is never run
# from where you put it: it must be a regular file reached through no symlink, its SHA-256 must match, and a verified copy
# is installed as /Library/PrivilegedHelperTools/ryzenadj (root:wheel, 755) in directories only root can write. The job
# runs that copy and nothing else.
#
#   nullmoth-ryzen-power.sh install --ryzenadj PATH [--sha256 HEX] [--stapm W] [--slow W] [--fast W] [--temp C]
#   nullmoth-ryzen-power.sh remove
#   nullmoth-ryzen-power.sh status
#
# Watts are whole numbers from 5 to 65 (sustained limit <= slow limit <= fast limit); the temperature limit is 50-100 C.
# The defaults are a quiet battery profile: 13 W sustained, 14 W slow, 15 W fast, 70 C.
# Test mode: NM_ROOT=<dir> (every file under <dir>, no root or CPU check) and NM_TRUST_UID=<uid> (the owner that counts as
# root) are honoured ONLY when the file .nullmoth-test-harness exists beside this script. The package never ships that file,
# so in a shipped copy both variables are ignored: a root-run install cannot be redirected or relaxed by its environment.
set -u
LABEL=com.nullmoth.ryzen-power
HERE=$(cd "$(dirname "$0")" && pwd -P)
ROOT=; ROOT_UID=0
if [ -f "$HERE/.nullmoth-test-harness" ]; then ROOT=${NM_ROOT:-}; ROOT_UID=${NM_TRUST_UID:-0}; fi
PLIST=$ROOT/Library/LaunchDaemons/$LABEL.plist
STAPM=13 SLOW=14 FAST=15 TEMP=70 RYZENADJ= SHA=
DEST_DIR=$ROOT/Library/PrivilegedHelperTools
DEST=$DEST_DIR/ryzenadj

die() { echo "nullmoth-ryzen-power: $*" >&2; exit 1; }
num() { case "$2" in ''|*[!0-9]*) die "$1 needs a whole number, got '$2'";; esac; }
range() { num "$1" "$2"; [ "$2" -ge "$3" ] && [ "$2" -le "$4" ] || die "$1 must be $3 to $4, got $2"; }

# every directory from $1 up to the root of the install must belong to root and not be writable by group or others
trusted_chain() {
  d=$1
  while :; do
    set -- $(stat -f '%u %Lp' "$d" 2>/dev/null) || return 1
    [ "${1:-}" = "$ROOT_UID" ] && [ $((8#${2:-777} & 8#022)) -eq 0 ] || return 1
    [ "$d" = "${ROOT:-/}" ] || [ "$d" = / ] && return 0
    d=$(dirname "$d")
  done
}
# the file at $1 reached through no symlink: not a link itself, and its directory resolves to itself
plain_file() {
  [ -f "$1" ] && [ ! -L "$1" ] && [ "$(cd "$(dirname "$1")" 2>/dev/null && pwd -P)/$(basename "$1")" = "$1" ]
}
sha_of() { shasum -a 256 "$1" | cut -d' ' -f1; }

cmd=${1:-}; [ $# -gt 0 ] && shift
while [ $# -gt 0 ]; do
  case $1 in
    --stapm) STAPM=${2:-}; shift 2;; --slow) SLOW=${2:-}; shift 2;; --fast) FAST=${2:-}; shift 2;;
    --temp) TEMP=${2:-}; shift 2;; --ryzenadj) RYZENADJ=${2:-}; shift 2;; --sha256) SHA=${2:-}; shift 2;;
    *) die "unknown option $1";;
  esac
done

case $cmd in
  install)
    if [ -z "$ROOT" ]; then
      [ "$(id -u)" = 0 ] || die "run with sudo"
      case "$(sysctl -n machdep.cpu.brand_string 2>/dev/null)" in *AMD*Ryzen*) ;; *) die "this Mac does not have a Ryzen CPU";; esac
    fi
    range --stapm "$STAPM" 5 65; range --slow "$SLOW" 5 65; range --fast "$FAST" 5 65; range --temp "$TEMP" 50 100
    [ "$STAPM" -le "$SLOW" ] && [ "$SLOW" -le "$FAST" ] || die "limits must satisfy stapm <= slow <= fast ($STAPM, $SLOW, $FAST)"
    case $RYZENADJ in /*) ;; *) die "--ryzenadj needs an absolute path";; esac
    plain_file "$RYZENADJ" || die "$RYZENADJ must be a regular file reached through no symlink"
    # only a build whose SHA-256 is listed in ryzenadj.sha256 (one hash per line, '#' comments) is installed
    PINNED=$(grep -E '^[0-9a-fA-F]{64}([[:space:]]|$)' "$HERE/ryzenadj.sha256" 2>/dev/null | cut -c1-64 | tr 'A-F' 'a-f')
    [ -n "$PINNED" ] || die "no RyzenAdj build is pinned for this release (ryzenadj.sha256 lists none); nothing installed"
    ACTUAL=$(sha_of "$RYZENADJ")
    if [ -n "$SHA" ] && [ "$(printf %s "$SHA" | tr 'A-F' 'a-f')" != "$ACTUAL" ]; then die "$RYZENADJ does not match the --sha256 given; nothing installed"; fi
    printf '%s\n' "$PINNED" | grep -qx "$ACTUAL" || die "$RYZENADJ ($ACTUAL) is not a pinned build; nothing installed"
    SHA=$ACTUAL
    mkdir -p "$DEST_DIR" || die "cannot create $DEST_DIR"
    trusted_chain "$DEST_DIR" || die "$DEST_DIR or a parent directory is not owned by root or is writable by others; nothing installed"
    [ ! -L "$DEST" ] || die "$DEST is a symlink; nothing installed"
    cp "$RYZENADJ" "$DEST.new.$$" || die "cannot copy RyzenAdj"
    if [ -z "$ROOT" ]; then chown 0:0 "$DEST.new.$$"; fi
    chmod 755 "$DEST.new.$$"
    [ "$(sha_of "$DEST.new.$$")" = "$SHA" ] || { rm -f "$DEST.new.$$"; die "the copy does not match the SHA-256; nothing installed"; }
    mv -f "$DEST.new.$$" "$DEST" || die "cannot place $DEST"
    mkdir -p "$(dirname "$PLIST")" || die "cannot create $(dirname "$PLIST")"
    tmp=$PLIST.tmp.$$
    cat > "$tmp" <<PL || die "cannot write $tmp"
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
	<key>Label</key><string>$LABEL</string>
	<key>ProgramArguments</key>
	<array>
		<string>$DEST</string>
		<string>--stapm-limit=$((STAPM * 1000))</string>
		<string>--slow-limit=$((SLOW * 1000))</string>
		<string>--fast-limit=$((FAST * 1000))</string>
		<string>--tctl-temp=$TEMP</string>
		<string>--power-saving</string>
	</array>
	<key>RunAtLoad</key><true/>
	<key>StartInterval</key><integer>30</integer>
	<key>UserName</key><string>root</string>
</dict>
</plist>
PL
    mv -f "$tmp" "$PLIST" || die "cannot place $PLIST"
    if [ -z "$ROOT" ]; then
      chown 0:0 "$PLIST"; chmod 644 "$PLIST"
      launchctl bootout system/$LABEL 2>/dev/null; launchctl bootstrap system "$PLIST" || die "launchctl refused the job"
    fi
    echo "installed: $STAPM W sustained, $SLOW W slow, $FAST W fast, $TEMP C";;
  remove)
    [ -n "$ROOT" ] || { [ "$(id -u)" = 0 ] || die "run with sudo"; launchctl bootout system/$LABEL 2>/dev/null; }
    rm -f "$PLIST" "$DEST"; echo "removed";;
  status)
    if [ -f "$PLIST" ]; then echo "installed"; grep -o -e '--[a-z-]*=[0-9]*' "$PLIST" | tr '\n' ' '; echo; else echo "not installed"; fi;;
  *) die "usage: $0 install|remove|status [options]";;
esac
