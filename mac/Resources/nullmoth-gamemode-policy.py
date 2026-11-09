#!/usr/bin/env python3
"""What Game Mode does for a game, done by this PC's own tools, because the Apple-silicon kernel setting that does it
(kern.console_mode) does not exist on this kernel.

While a game is in the foreground:
  * the game gets a higher CPU priority (nice -5) and the interactive QoS class for its disk I/O;
  * a fixed list of background indexing and analysis jobs is moved to the background class (taskpolicy -b), so they stop
    competing with it for the CPU, the disk and, through their Metal use, the GPU.
When the game stops being in the foreground, every change is undone from the record this script kept.

The GPU side is not here: the Vulkan driver advertises a single queue priority (medium), so a game's GPU work cannot be
raised through the Vulkan API without a change in the driver's channel scheduling.

  nullmoth-gamemode-policy.py status                 what would be treated as a game right now
  nullmoth-gamemode-policy.py apply <pid>            (root) raise the game, demote the background jobs, write the record
  nullmoth-gamemode-policy.py restore                (root) undo from the record
  nullmoth-gamemode-policy.py watch [seconds]        (root) apply and restore as the foreground app changes

Off unless the user runs it: nothing starts it. Exit status: 0 done, 1 nothing to do, 2 bad usage or not root.
"""
import json
import os
import plistlib
import subprocess
import sys
import time

STATE = os.environ.get("NULLMOTH_STATE_DIR", "/Library/NullMoth") + "/gamemode-policy.json"
GAME_NICE = -5
# Jobs that index, analyse or back up in the background. Matched by exact process name. Nothing the user is running by
# hand is on the list.
BACKGROUND_JOBS = ("mds_stores", "mdworker_shared", "photoanalysisd", "mediaanalysisd", "backupd", "suggestd",
                   "spotlightknowledged", "knowledge-agent")


def is_game(info):
    """True for a bundle that says it is a game: the games category, or it opts in to Game Mode (LSSupportsGameMode), the
    two things macOS's own Game Mode daemon reads from an Info.plist."""
    if not isinstance(info, dict):
        return False
    return info.get("LSApplicationCategoryType") == "public.app-category.games" or info.get("LSSupportsGameMode") is True


def plan(game_pid, procs):
    """The actions for a game. procs is [(pid, name)]. Returns [(action, pid)] with action in raise, background."""
    acts = [("raise", game_pid)]
    for pid, name in procs:
        if name in BACKGROUND_JOBS and pid != game_pid:
            acts.append(("background", pid))
    return acts


def run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True)


def current_nice(pid, runner=run):
    r = runner(["/bin/ps", "-o", "nice=", "-p", str(pid)])
    try:
        return int(r.stdout.strip())
    except ValueError:
        return None


ACTIVE_KEY = "com.nullmoth.gamemode.active"
ACTIVE_FILE = os.environ.get("NULLMOTH_STATE_DIR", "/Library/NullMoth") + "/gamemode-active"


def publish_active(active, notifier=None, active_file=ACTIVE_FILE):
    """Tells every Metal client on the Mac whether a game is active: the notify(3) key's state (1 or 0) and a root-owned file
    that exists only while a game is active. notifier(name, value) can be replaced in tests."""
    if notifier is None:
        notifier = _notify
    notifier(ACTIVE_KEY, 1 if active else 0)
    try:
        if active:
            os.makedirs(os.path.dirname(active_file), exist_ok=True)
            with open(active_file + ".tmp", "w") as f:
                f.write("1\n")
            os.replace(active_file + ".tmp", active_file)
            os.chmod(active_file, 0o644)
        elif os.path.exists(active_file):
            os.remove(active_file)
    except OSError:
        pass


def _notify(name, value):
    """notify_set_state then notify_post, through libSystem. A failure is not an error: the file still says it."""
    try:
        import ctypes
        lib = ctypes.CDLL("/usr/lib/libSystem.B.dylib")
        token = ctypes.c_int(0)
        if lib.notify_register_check(name.encode(), ctypes.byref(token)) == 0:
            lib.notify_set_state(token, ctypes.c_uint64(value))
        lib.notify_post(name.encode())
    except (OSError, AttributeError):
        pass


def apply(game_pid, procs, runner=run, state=STATE, publish=None):
    """Carries out plan(), recording what each change needs to be undone. Returns the record."""
    record = {"game": game_pid, "raised": [], "backgrounded": []}
    for act, pid in plan(game_pid, procs):
        if act == "raise":
            before = current_nice(pid, runner)
            if before is not None and runner(["/usr/bin/renice", str(GAME_NICE), "-p", str(pid)]).returncode == 0:
                record["raised"].append({"pid": pid, "nice": before})
        else:
            if runner(["/usr/sbin/taskpolicy", "-b", "-p", str(pid)]).returncode == 0:
                record["backgrounded"].append(pid)
    os.makedirs(os.path.dirname(state), exist_ok=True)
    with open(state + ".tmp", "w") as f:
        json.dump(record, f)
    os.replace(state + ".tmp", state)
    (publish or publish_active)(True)
    return record


def restore(runner=run, state=STATE, publish=None):
    """Undoes what the record says, for the processes that still exist. Returns how many changes were undone."""
    try:
        with open(state) as f:
            record = json.load(f)
    except (OSError, ValueError):
        return 0
    n = 0
    for r in record.get("raised", []):
        if runner(["/usr/bin/renice", str(r["nice"]), "-p", str(r["pid"])]).returncode == 0:
            n += 1
    for pid in record.get("backgrounded", []):
        if runner(["/usr/sbin/taskpolicy", "-B", "-p", str(pid)]).returncode == 0:
            n += 1
    try:
        os.remove(state)
    except OSError:
        pass
    (publish or publish_active)(False)
    return n


def processes(runner=run):
    out = runner(["/bin/ps", "-axo", "pid=,comm="]).stdout.splitlines()
    procs = []
    for line in out:
        parts = line.strip().split(None, 1)
        if len(parts) == 2 and parts[0].isdigit():
            procs.append((int(parts[0]), os.path.basename(parts[1])))
    return procs


def frontmost(runner=run):
    """(pid, bundle path) of the foreground app, or None. Uses lsappinfo, which ships with macOS."""
    asn = runner(["/usr/bin/lsappinfo", "front"]).stdout.strip()
    if not asn:
        return None
    pid = runner(["/usr/bin/lsappinfo", "info", "-only", "pid", asn]).stdout
    path = runner(["/usr/bin/lsappinfo", "info", "-only", "bundlepath", asn]).stdout
    try:
        pid = int(pid.split("=")[-1].strip())
    except ValueError:
        return None
    path = path.split("=", 1)[-1].strip().strip('"')
    return pid, path


def bundle_info(path):
    try:
        with open(os.path.join(path, "Contents", "Info.plist"), "rb") as f:
            return plistlib.load(f)
    except (OSError, ValueError, plistlib.InvalidFileException):
        return None


def main(argv):
    cmd = argv[1] if len(argv) > 1 else ""
    if cmd == "status":
        fm = frontmost()
        info = bundle_info(fm[1]) if fm else None
        print("foreground game: " + (fm[1] if fm and is_game(info) else "none"))
        return 0
    if cmd in ("apply", "restore", "watch") and os.getuid() != 0:
        print(f"{cmd} needs root")
        return 2
    if cmd == "apply" and len(argv) > 2 and argv[2].isdigit():
        rec = apply(int(argv[2]), processes())
        print(f"raised {len(rec['raised'])}, backgrounded {len(rec['backgrounded'])}")
        return 0
    if cmd == "restore":
        n = restore()
        print(f"undid {n} change(s)")
        return 0 if n else 1
    if cmd == "watch":
        every = float(argv[2]) if len(argv) > 2 else 5.0
        active = None
        while True:
            fm = frontmost()
            game = fm[0] if fm and is_game(bundle_info(fm[1])) else None
            if game != active:
                if active is not None:
                    restore()
                if game is not None:
                    apply(game, processes())
                active = game
            time.sleep(every)
    print("usage: nullmoth-gamemode-policy.py status | apply <pid> | restore | watch [seconds]")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
