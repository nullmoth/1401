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
  nullmoth-gamemode-policy.py observe                (as the logged-in user) print the foreground app and the full-screen windows as JSON
  nullmoth-gamemode-policy.py apply <pid>            (root) raise the game, demote the background jobs, write the record
  nullmoth-gamemode-policy.py restore                (root) undo from the record
  nullmoth-gamemode-policy.py watch [seconds]        (root) Game Mode on while a game is in front AND full screen, off when it is not

The trigger: the foreground app is a game (games category, or it opts in to Game Mode) and one of its windows covers a whole
display. A window server session belongs to the logged-in user, so `watch` (root, from a LaunchDaemon) asks `observe` to run
inside that user's session with `launchctl asuser`. Whatever it changed is undone when the game leaves full screen or the
foreground, when the game quits, and when the daemon is stopped.

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


def covers(window_bounds, display_bounds, slack=2.0):
    """True when a window rectangle (x, y, w, h) covers a whole display rectangle, within a couple of points."""
    wx, wy, ww, wh = window_bounds
    dx, dy, dw, dh = display_bounds
    return wx <= dx + slack and wy <= dy + slack and wx + ww >= dx + dw - slack and wy + wh >= dy + dh - slack


def fullscreen_pids(windows, displays):
    """Pids that own a normal-layer window covering a whole display. windows: [{"pid", "layer", "bounds": (x, y, w, h)}]."""
    out = set()
    for w in windows:
        if w.get("layer") == 0 and any(covers(w["bounds"], d) for d in displays):
            out.add(w["pid"])
    return out


def desired_game(front, info, fullscreen):
    """The pid of the game that should have Game Mode now, or None: the foreground app is a game and is full screen."""
    if front and is_game(info) and front[0] in fullscreen:
        return front[0]
    return None


class Watcher:
    """Turns a stream of observations into apply and restore calls. step(game_pid) with the pid that should have Game Mode, or
    None. A change of game restores the old one first; a game that has quit counts as gone."""

    def __init__(self, do_apply, do_restore, alive=None):
        self.active = None
        self.do_apply, self.do_restore = do_apply, do_restore
        self.alive = alive or (lambda pid: True)

    def step(self, game):
        if self.active is not None and not self.alive(self.active):
            self.do_restore()
            self.active = None
        if game != self.active:
            if self.active is not None:
                self.do_restore()
                self.active = None
            if game is not None:
                self.do_apply(game)
                self.active = game
        return self.active

    def stop(self):
        if self.active is not None:
            self.do_restore()
            self.active = None


def _core_graphics_windows():
    """(windows, displays) from CoreGraphics, through ctypes. Must run inside the user's window server session."""
    import ctypes

    class CGRect(ctypes.Structure):
        _fields_ = [("x", ctypes.c_double), ("y", ctypes.c_double), ("w", ctypes.c_double), ("h", ctypes.c_double)]

    cf = ctypes.CDLL("/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation")
    cg = ctypes.CDLL("/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics")
    cf.CFArrayGetCount.restype = ctypes.c_long
    cf.CFArrayGetCount.argtypes = [ctypes.c_void_p]
    cf.CFRelease.argtypes = [ctypes.c_void_p]
    cf.CFArrayGetValueAtIndex.restype = ctypes.c_void_p
    cf.CFArrayGetValueAtIndex.argtypes = [ctypes.c_void_p, ctypes.c_long]
    cf.CFDictionaryGetValue.restype = ctypes.c_void_p
    cf.CFDictionaryGetValue.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    cf.CFStringCreateWithCString.restype = ctypes.c_void_p
    cf.CFStringCreateWithCString.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_uint32]
    cf.CFNumberGetValue.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p]
    cg.CGWindowListCopyWindowInfo.restype = ctypes.c_void_p
    cg.CGWindowListCopyWindowInfo.argtypes = [ctypes.c_uint32, ctypes.c_uint32]
    cg.CGRectMakeWithDictionaryRepresentation.argtypes = [ctypes.c_void_p, ctypes.POINTER(CGRect)]
    cg.CGDisplayBounds.restype = CGRect
    cg.CGDisplayBounds.argtypes = [ctypes.c_uint32]

    def key(name):
        return cf.CFStringCreateWithCString(None, name.encode(), 0x08000100)

    def number(ref, kind, ctype):
        v = ctype()
        return v.value if ref and cf.CFNumberGetValue(ref, kind, ctypes.byref(v)) else None

    arr = cg.CGWindowListCopyWindowInfo(1 | 16, 0)   # on screen only, no desktop elements
    windows = []
    k_pid, k_layer, k_bounds = key("kCGWindowOwnerPID"), key("kCGWindowLayer"), key("kCGWindowBounds")
    for i in range(cf.CFArrayGetCount(arr) if arr else 0):
        d = cf.CFArrayGetValueAtIndex(arr, i)
        pid = number(cf.CFDictionaryGetValue(d, k_pid), 3, ctypes.c_int)           # kCFNumberSInt32Type
        layer = number(cf.CFDictionaryGetValue(d, k_layer), 3, ctypes.c_int)
        r = CGRect()
        bref = cf.CFDictionaryGetValue(d, k_bounds)
        if pid is None or not bref or not cg.CGRectMakeWithDictionaryRepresentation(bref, ctypes.byref(r)):
            continue
        windows.append({"pid": pid, "layer": layer, "bounds": (r.x, r.y, r.w, r.h)})
    if arr:
        cf.CFRelease(arr)
    ids = (ctypes.c_uint32 * 16)()
    n = ctypes.c_uint32(0)
    cg.CGGetActiveDisplayList(16, ids, ctypes.byref(n))
    displays = []
    for i in range(n.value):
        r = cg.CGDisplayBounds(ids[i])
        displays.append((r.x, r.y, r.w, r.h))
    return windows, displays


def observe(runner=run, cg=None):
    """What the user's session shows now: {"front": [pid, path] or null, "fullscreen": [pids]}."""
    fm = frontmost(runner)
    try:
        windows, displays = (cg or _core_graphics_windows)()
    except (OSError, AttributeError):
        windows, displays = [], []
    return {"front": list(fm) if fm else None, "fullscreen": sorted(fullscreen_pids(windows, displays))}


def console_uid():
    try:
        return os.stat("/dev/console").st_uid
    except OSError:
        return None


def observe_as_user(runner=run, uid=None):
    """Runs `observe` inside the logged-in user's session (root only) and parses it; None when nobody is logged in."""
    uid = console_uid() if uid is None else uid
    if not uid:
        return None
    r = runner(["/bin/launchctl", "asuser", str(uid), "/usr/bin/python3", os.path.abspath(__file__), "observe"])
    try:
        return json.loads(r.stdout)
    except ValueError:
        return None


def alive(pid):
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def watch(every=5.0, observer=None, sleep=time.sleep, rounds=None):
    """The root loop. observer() returns observe()'s dict or None. rounds limits the loop for tests."""
    import signal
    w = Watcher(lambda pid: apply(pid, processes()), restore, alive)
    signal.signal(signal.SIGTERM, lambda *_: (w.stop(), sys.exit(0)))
    n = 0
    try:
        while rounds is None or n < rounds:
            obs = (observer or observe_as_user)()
            game = None
            if obs and obs.get("front"):
                front = (obs["front"][0], obs["front"][1])
                game = desired_game(front, bundle_info(front[1]), set(obs.get("fullscreen", [])))
            w.step(game)
            n += 1
            sleep(every)
    finally:
        w.stop()


def main(argv):
    cmd = argv[1] if len(argv) > 1 else ""
    if cmd == "status":
        o = observe()
        fm = o["front"]
        info = bundle_info(fm[1]) if fm else None
        game = desired_game(tuple(fm) if fm else None, info, set(o["fullscreen"]))
        print("full-screen game: " + (fm[1] if game else "none"))
        return 0
    if cmd == "observe":
        print(json.dumps(observe()))
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
        watch(float(argv[2]) if len(argv) > 2 else 5.0)
        return 0
    print("usage: nullmoth-gamemode-policy.py status | observe | apply <pid> | restore | watch [seconds]")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
