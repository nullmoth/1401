#!/bin/bash
# nullmoth-ryzen-power.sh: a power-limit profile for Ryzen laptops, applied at every start and refreshed while running.
#
# A Ryzen laptop under macOS runs at the firmware's default limits, which are tuned for Windows' power plans and run hot
# and loud on a battery. This installs a small LaunchDaemon that calls RyzenAdj (https://github.com/FlyGoat/RyzenAdj, LGPL)
# with limits you choose. RyzenAdj is not shipped here: install your own build and give its path with --ryzenadj.
#
#   nullmoth-ryzen-power.sh install [--stapm W] [--slow W] [--fast W] [--temp C] [--ryzenadj PATH]
#   nullmoth-ryzen-power.sh remove
#   nullmoth-ryzen-power.sh status
#
# Watts are whole numbers from 5 to 65 (sustained limit <= slow limit <= fast limit); the temperature limit is 50-100 C.
# The defaults are a quiet battery profile: 13 W sustained, 14 W slow, 15 W fast, 70 C.
# NM_ROOT=<dir> puts every file under <dir> instead of / and skips the root and CPU checks (used by the tests).
set -u
LABEL=com.nullmoth.ryzen-power
ROOT=${NM_ROOT:-}
PLIST=$ROOT/Library/LaunchDaemons/$LABEL.plist
STAPM=13 SLOW=14 FAST=15 TEMP=70 RYZENADJ=/usr/local/bin/ryzenadj

die() { echo "nullmoth-ryzen-power: $*" >&2; exit 1; }
num() { case "$2" in ''|*[!0-9]*) die "$1 needs a whole number, got '$2'";; esac; }
range() { num "$1" "$2"; [ "$2" -ge "$3" ] && [ "$2" -le "$4" ] || die "$1 must be $3 to $4, got $2"; }

cmd=${1:-}; [ $# -gt 0 ] && shift
while [ $# -gt 0 ]; do
  case $1 in
    --stapm) STAPM=${2:-}; shift 2;; --slow) SLOW=${2:-}; shift 2;; --fast) FAST=${2:-}; shift 2;;
    --temp) TEMP=${2:-}; shift 2;; --ryzenadj) RYZENADJ=${2:-}; shift 2;;
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
    case $RYZENADJ in *[\<\>\&\"\']*) die "--ryzenadj has a character a property list cannot hold";; esac
    [ -n "$ROOT" ] || [ -x "$RYZENADJ" ] || die "$RYZENADJ is not an executable RyzenAdj"
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
		<string>$RYZENADJ</string>
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
    rm -f "$PLIST"; echo "removed";;
  status)
    if [ -f "$PLIST" ]; then echo "installed"; grep -o -e '--[a-z-]*=[0-9]*' "$PLIST" | tr '\n' ' '; echo; else echo "not installed"; fi;;
  *) die "usage: $0 install|remove|status [options]";;
esac
