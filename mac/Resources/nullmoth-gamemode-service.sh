#!/bin/bash
# Installs, removes and reports NullMoth's own Game Mode: a root LaunchDaemon that turns Game Mode on while a game is in front
# and full screen, and a per-user menu-bar indicator that shows when it is on.
#
#   nullmoth-gamemode-service.sh install <policy script> <indicator program>     (root)
#   nullmoth-gamemode-service.sh remove                                           (root)
#   nullmoth-gamemode-service.sh status                                           prints  installed|not installed , running|stopped
#
# Both files are copied into /Library/NullMoth/gamemode, which only root can write, and the services run from there, never
# from the app bundle (which belongs to the user). Nothing here runs unless the user turns Game Mode on in 1401 or an
# installer is run with its game-mode flag; removing it restores everything Game Mode changed.
# Exit status: 0 done, 1 refused with the reason on stdout, 2 bad usage or not root.
set -u
PREFIX=${NULLMOTH_GM_PREFIX:-}           # a test prefix; empty on a real Mac
DIR=$PREFIX/Library/NullMoth/gamemode
DAEMON_PLIST=$PREFIX/Library/LaunchDaemons/com.nullmoth.gamemode.plist
AGENT_PLIST=$PREFIX/Library/LaunchAgents/com.nullmoth.gamemode.indicator.plist
LAUNCHCTL=${NULLMOTH_GM_LAUNCHCTL:-/bin/launchctl}
PY=${NULLMOTH_GM_PYTHON:-/usr/bin/python3}

need_root() { [ -n "$PREFIX" ] || [ "$(id -u)" = 0 ] || { echo "$1 needs root"; exit 2; }; }
console_uid() { stat -f %u /dev/console 2>/dev/null; }

case "${1:-}" in
  install)
    need_root install
    [ "$#" = 3 ] && [ -f "$2" ] && [ -f "$3" ] || { echo "usage: $0 install <policy script> <indicator program>"; exit 2; }
    if [ -z "$PREFIX" ] && ! /usr/bin/xcode-select -p >/dev/null 2>&1; then
      echo "Game Mode needs the Command Line Tools (for python3). Install them from 1401 > ARM apps > Command Line Tools, then try again."
      exit 1
    fi
    /bin/mkdir -p "$DIR" "$PREFIX/Library/LaunchDaemons" "$PREFIX/Library/LaunchAgents" || exit 1
    /bin/cp -X "$2" "$DIR/nullmoth-gamemode-policy.py" && /bin/cp -X "$3" "$DIR/nullmoth-gamemode-indicator" || { echo "could not copy the files"; exit 1; }
    /bin/chmod 755 "$DIR" "$DIR/nullmoth-gamemode-policy.py" "$DIR/nullmoth-gamemode-indicator"
    [ -n "$PREFIX" ] || /usr/sbin/chown -R root:wheel "$DIR"
    cat >"$DAEMON_PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>Label</key><string>com.nullmoth.gamemode</string>
<key>ProgramArguments</key><array><string>$PY</string><string>/Library/NullMoth/gamemode/nullmoth-gamemode-policy.py</string><string>watch</string><string>5</string></array>
<key>RunAtLoad</key><true/>
<key>KeepAlive</key><true/>
<key>ProcessType</key><string>Background</string>
</dict></plist>
EOF
    cat >"$AGENT_PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>Label</key><string>com.nullmoth.gamemode.indicator</string>
<key>ProgramArguments</key><array><string>/Library/NullMoth/gamemode/nullmoth-gamemode-indicator</string></array>
<key>RunAtLoad</key><true/>
<key>KeepAlive</key><true/>
<key>LimitLoadToSessionType</key><string>Aqua</string>
</dict></plist>
EOF
    /bin/chmod 644 "$DAEMON_PLIST" "$AGENT_PLIST"
    [ -n "$PREFIX" ] || /usr/sbin/chown root:wheel "$DAEMON_PLIST" "$AGENT_PLIST"
    "$LAUNCHCTL" bootout system/com.nullmoth.gamemode >/dev/null 2>&1
    "$LAUNCHCTL" bootstrap system "$DAEMON_PLIST" || { echo "launchd refused the Game Mode service"; exit 1; }
    uid=$(console_uid)
    if [ -n "$uid" ] && [ "$uid" != 0 ]; then
      "$LAUNCHCTL" bootout "gui/$uid/com.nullmoth.gamemode.indicator" >/dev/null 2>&1
      "$LAUNCHCTL" bootstrap "gui/$uid" "$AGENT_PLIST" >/dev/null 2>&1   # at the next login it loads by itself if this is refused
    fi
    echo "installed"
    ;;
  remove)
    need_root remove
    uid=$(console_uid)
    [ -n "$uid" ] && [ "$uid" != 0 ] && "$LAUNCHCTL" bootout "gui/$uid/com.nullmoth.gamemode.indicator" >/dev/null 2>&1
    "$LAUNCHCTL" bootout system/com.nullmoth.gamemode >/dev/null 2>&1      # SIGTERM: the loop restores what it changed
    [ -x "$DIR/nullmoth-gamemode-policy.py" ] && "$PY" "$DIR/nullmoth-gamemode-policy.py" restore >/dev/null 2>&1   # a record left by a crash
    /bin/rm -f "$DAEMON_PLIST" "$AGENT_PLIST"
    /bin/rm -rf "$DIR"
    echo "removed"
    ;;
  status)
    if [ -f "$DAEMON_PLIST" ] && [ -d "$DIR" ]; then inst="installed"; else inst="not installed"; fi
    if "$LAUNCHCTL" print system/com.nullmoth.gamemode >/dev/null 2>&1; then run="running"; else run="stopped"; fi
    echo "$inst , $run"
    ;;
  *)
    echo "usage: $0 install <policy script> <indicator program> | remove | status"
    exit 2
    ;;
esac
exit 0
