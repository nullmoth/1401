#!/usr/bin/env python3
"""1401 for Linux: check this PC, build the OpenCore setup, show the BIOS steps, and write the macOS stick.

GTK 4 and PyGObject. The window only collects choices and runs the same engine commands the Windows app runs; every
step that needs root (ACPI tables, the USB erase) goes through policykit.
"""
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import threading
import uuid

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gio, GLib, Gtk  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, REPO)

from p1401 import linuxusb  # noqa: E402

APP_NAME = "1401"
STEPS = ["Introduction", "Check this PC", "Build the Mac setup", "Your BIOS steps", "Create the macOS stick", "Done"]
OS_CHOICES = [("macOS 15 Sequoia", "24", False), ("macOS 26 Tahoe", "25", False),
              ("macOS 14 Sonoma (experimental)", "23", True), ("macOS 13 Ventura (experimental)", "22", True),
              ("macOS 12 Monterey (experimental)", "21", True), ("macOS 11 Big Sur (experimental)", "20", True),
              ("macOS 10.15 Catalina (experimental)", "19", True), ("macOS 10.14 Mojave (experimental)", "18", True),
              ("macOS 10.13 High Sierra (experimental)", "17", True), ("macOS 10.12 Sierra (experimental)", "16", True)]
MACOS_NAMES = {"25": "Tahoe", "24": "Sequoia", "23": "Sonoma", "22": "Ventura", "21": "Monterey", "20": "Big Sur",
               "19": "Catalina", "18": "Mojave", "17": "High Sierra", "16": "Sierra", "15": "El Capitan"}
OPEN_CORE_GUIDE = "https://dortania.github.io/OpenCore-Install-Guide/"
MAX_LOG_LINES = 5000
# The engine records the ACPI disassembler's printout as a notice when it moves on to its next question. The log keeps
# it for support; the result summary skips it, because it is thousands of characters about duplicate names in the
# firmware tables and reads like a failure even when the build passed.
_ACPI_DUMP = re.compile(r"^(?:ACPI(?::| Error:)|Firmware Error|Pass \d parse|Parsing |Disassembly |ASL Output:|"
                        r"File appears to be binary|Input file )", re.M)


def state_dir():
    base = os.environ.get("XDG_STATE_HOME") or os.path.join(os.path.expanduser("~"), ".local", "state")
    return os.path.join(base, "nullmoth", "1401")


def data_dir():
    base = os.environ.get("XDG_DATA_HOME") or os.path.join(os.path.expanduser("~"), ".local", "share")
    return os.path.join(base, "nullmoth", "1401")


def interpreter():
    return [sys.executable, "-E", "-s", "-u"]


def quoted(command):
    return " ".join(shlex.quote(part) for part in command)


class Window(Gtk.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title=APP_NAME)
        self.set_default_size(1040, 760)
        self.set_size_request(860, 620)
        self.work = state_dir()
        os.makedirs(self.work, exist_ok=True)
        self.log_path = os.path.join(self.work, "1401.log")
        self._rotate_log()
        self.log_file = open(self.log_path, "a", encoding="utf-8", buffering=1)
        self.busy = False
        self.page = 0
        self.scanned = False
        self.built = False
        self.written = False
        self.scan_id = None
        self.scan_dir = None
        self.efi_dir = os.path.join(self.work, "efi")
        self.guide_file = None
        self.macos_full = ""
        self.darwin = "24"
        self.summary = ""
        self.usb_disks = []
        self.full_pkg = None
        self.recovery_dir = os.path.join(data_dir(), "Recovery")
        self.last_lines = []
        self._pulse_id = None
        self._have_progress = False
        self._log_lines = 0
        self.busy_controls = []

        self.header = Gtk.HeaderBar()
        self.header.set_title_widget(Gtk.Label(label=APP_NAME))
        self.set_titlebar(self.header)

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.set_child(root)
        main = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        main.set_vexpand(True)
        root.append(main)

        sidebar = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        sidebar.set_size_request(228, -1)
        sidebar.set_margin_top(18)
        sidebar.set_margin_bottom(18)
        sidebar.set_margin_start(12)
        sidebar.set_margin_end(12)
        main.append(sidebar)
        self.side_labels = []
        for index, step in enumerate(STEPS):
            label = Gtk.Label(label=f"{index + 1}.  {step}", xalign=0)
            label.set_margin_top(6)
            label.set_margin_bottom(6)
            label.set_margin_start(8)
            label.set_margin_end(8)
            sidebar.append(label)
            self.side_labels.append(label)
        sidebar.append(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL))
        self.side_note = Gtk.Label(label="Nothing on this PC is uploaded. Logs stay in " + self.work, xalign=0)
        self.side_note.set_wrap(True)
        self.side_note.add_css_class("dim-label")
        self.side_note.set_margin_top(12)
        sidebar.append(self.side_note)

        main.append(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL))

        right = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        right.set_hexpand(True)
        right.set_margin_top(18)
        right.set_margin_bottom(12)
        right.set_margin_start(20)
        right.set_margin_end(20)
        main.append(right)

        self.title = Gtk.Label(xalign=0)
        self.title.add_css_class("title-1")
        right.append(self.title)
        self.note = Gtk.Label(xalign=0)
        self.note.set_wrap(True)
        right.append(self.note)

        self.stack = Gtk.Stack()
        self.stack.set_vexpand(True)
        self.stack.set_vhomogeneous(False)
        self.stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        # A page can be taller than the window (the build result, a small screen). Scroll the page, not the whole
        # window: the Back/Continue buttons below the stack have to stay reachable.
        page_scroller = Gtk.ScrolledWindow()
        page_scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        page_scroller.set_vexpand(True)
        page_scroller.set_child(self.stack)
        right.append(page_scroller)
        self.pages = [self._page_intro(), self._page_check(), self._page_build(), self._page_bios(),
                      self._page_write(), self._page_done()]
        for index, page in enumerate(self.pages):
            self.stack.add_named(page, f"page{index}")

        self.progress = Gtk.ProgressBar()
        self.progress.set_show_text(True)
        self.progress.set_text("")
        self.progress.set_visible(False)
        right.append(self.progress)

        self.log_view = Gtk.TextView()
        self.log_view.set_editable(False)
        self.log_view.set_cursor_visible(False)
        self.log_view.set_monospace(True)
        self.log_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        scroller = Gtk.ScrolledWindow()
        scroller.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scroller.set_child(self.log_view)
        scroller.set_size_request(-1, 180)
        self.log_scroller = scroller
        right.append(scroller)

        footer = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        footer.set_margin_top(4)
        self.back = Gtk.Button(label="Back")
        self.back.connect("clicked", lambda _b: self.go(self.page - 1))
        footer.append(self.back)
        spacer = Gtk.Box()
        spacer.set_hexpand(True)
        footer.append(spacer)
        self.next = Gtk.Button()
        self.next.add_css_class("suggested-action")
        self.next.connect("clicked", lambda _b: self.on_next())
        footer.append(self.next)
        right.append(footer)

        self.busy_controls = [self.back, self.next, self.check_again, self.stick_refresh, self.open_guide]
        self.connect("close-request", self._on_close)
        self.go(0)
        self.fill_sticks()
        self._resume_session()
        GLib.idle_add(self._check_engine)

    def _rotate_log(self):
        try:
            if os.path.getsize(self.log_path) > 4 * 1024 * 1024:
                os.replace(self.log_path, self.log_path + ".old")
        except OSError:
            pass

    def _session_file(self):
        return os.path.join(self.work, "1401-session.json")

    def _save_session(self):
        """Keep the last scan and build across a restart; the USB write itself is never resumed."""
        if not self.scan_id or not self.scan_dir:
            return
        state = {"scan_id": self.scan_id, "built": self.built, "macos_version": self.macos_full,
                 "darwin": self.darwin, "summary": self.summary,
                 "guide": os.path.basename(self.guide_file) if self.guide_file else "",
                 "experimental": self.experimental.get_active(), "persistent": self.persistent.get_active(),
                 "external": self.external.get_active(), "new_identity": self.new_identity.get_active()}
        try:
            with open(self._session_file() + ".tmp", "w", encoding="utf-8") as fh:
                json.dump(state, fh)
            os.replace(self._session_file() + ".tmp", self._session_file())
        except OSError:
            pass   # losing the resume point is not worth stopping a finished build for

    def _resume_session(self):
        """Start from the last finished scan, and from its build when the EFI and session agree."""
        try:
            with open(self._session_file(), encoding="utf-8") as fh:
                state = json.load(fh)
        except (OSError, ValueError):
            return
        if not isinstance(state, dict):
            return
        scan_id = state.get("scan_id")
        if not isinstance(scan_id, str) or not re.fullmatch(r"[0-9a-f]{32}", scan_id):
            return
        scan_dir = os.path.join(self.work, "scan-" + scan_id)
        if not (os.path.isfile(os.path.join(scan_dir, "Report.json")) and
                os.path.isdir(os.path.join(scan_dir, "ACPI"))):
            return
        self.scan_id, self.scan_dir, self.scanned = scan_id, scan_dir, True
        self.load_facts()
        self.check_note.set_text("This PC was checked. Continue to build the startup files.")
        self.go(1)
        darwin = str(state.get("darwin") or "")
        index = next((i for i, (_, value, _) in enumerate(OS_CHOICES) if value == darwin), None)
        if index is not None:
            self.os_pick.set_selected(index)
            self.darwin = darwin
        for key, button in (("experimental", self.experimental), ("persistent", self.persistent),
                            ("external", self.external), ("new_identity", self.new_identity)):
            button.set_active(bool(state.get(key)))
        if not state.get("built") or not os.path.isfile(os.path.join(self.work, "efi", "EFI", "OC", "config.plist")):
            return
        self.macos_full = str(state.get("macos_version") or "")
        self.summary = str(state.get("summary") or "")
        self.built = True
        self.build_summary.set_text(self.summary)
        guide = os.path.join(self.work, os.path.basename(str(state.get("guide") or "")))
        if state.get("guide") and os.path.isfile(guide):
            self.guide_file = guide
            self.guide_label.set_text(guide)
        self.go(2)
        if not self.guide_file:
            self._make_guide()

    # --- pages --------------------------------------------------------------------------------------------------

    def _page_intro(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        text = Gtk.Label(xalign=0)
        text.set_wrap(True)
        text.set_text("1401 turns a USB stick into a macOS installer built for this PC, the way Boot Camp put "
                      "Windows on a Mac.\n\nIt checks this PC, builds the startup files macOS needs for the exact "
                      "hardware, shows the BIOS settings this board needs, and writes the install stick. Windows on "
                      "this PC is not touched.\n\nYou need an internet connection and a USB stick of 4 GB or more "
                      "that can be erased.")
        box.append(text)
        caution = Gtk.Label(xalign=0)
        caution.set_wrap(True)
        caution.add_css_class("dim-label")
        caution.set_text("1401 is new and may not work on every PC. If it does not work on yours, set up OpenCore "
                         "by hand with the guide below; the NullMoth app works on any OpenCore setup.")
        box.append(caution)
        link = Gtk.LinkButton(uri=OPEN_CORE_GUIDE, label="OpenCore Install Guide")
        box.append(link)
        return box

    def _page_check(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.facts = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        box.append(self.facts)
        self.check_note = Gtk.Label(xalign=0)
        self.check_note.set_wrap(True)
        self.check_note.add_css_class("dim-label")
        self.check_note.set_text("The check reads the processor, board, graphics, network and storage, then copies "
                                 "this PC's ACPI tables. It takes about a minute. Linux will ask for your password "
                                 "once so the tables can be read.")
        box.append(self.check_note)
        self.check_again = Gtk.Button(label="Check this PC again")
        self.check_again.set_halign(Gtk.Align.START)
        self.check_again.connect("clicked", lambda _b: self.start_scan(force=True))
        box.append(self.check_again)
        return box

    def _page_build(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        row.append(Gtk.Label(label="macOS version"))
        self.os_pick = Gtk.DropDown.new_from_strings([name for name, _, _ in OS_CHOICES])
        self.os_pick.set_selected(0)
        self.os_pick.connect("notify::selected", lambda *_a: self._build_options_changed())
        row.append(self.os_pick)
        box.append(row)
        self.experimental = Gtk.CheckButton(label="Include experimental community drivers (off unless you need them)")
        self.experimental.connect("toggled", lambda *_a: self._build_options_changed())
        box.append(self.experimental)
        self.persistent = Gtk.CheckButton(label="Persistent NVRAM on AMD (for iMessage and the startup disk)")
        self.persistent.connect("toggled", lambda *_a: self._build_options_changed())
        box.append(self.persistent)
        self.external = Gtk.CheckButton(label="Install macOS on a drive macOS can see when the internal drives are hidden")
        self.external.connect("toggled", lambda *_a: self._build_options_changed())
        box.append(self.external)
        self.new_identity = Gtk.CheckButton(label="Use a new serial number instead of the previous build's")
        self.new_identity.connect("toggled", lambda *_a: self._build_options_changed())
        box.append(self.new_identity)
        self.build_summary = Gtk.Label(xalign=0)
        self.build_summary.set_wrap(True)
        self.build_summary.set_selectable(True)
        box.append(self.build_summary)
        self.build_note = Gtk.Label(xalign=0)
        self.build_note.set_wrap(True)
        self.build_note.add_css_class("dim-label")
        self.build_note.set_text("1401 downloads OpenCore and the drivers, builds the startup files for the chosen "
                                 "macOS, and checks them with OpenCore's own validator.")
        box.append(self.build_note)
        return box

    def _page_bios(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        text = Gtk.Label(xalign=0)
        text.set_wrap(True)
        text.set_text("The BIOS steps follow this scan and the startup files just built. Check the menu names in "
                      "your board manual, and take a photo of the settings you change before restarting.")
        box.append(text)
        self.open_guide = Gtk.Button(label="Open the BIOS steps")
        self.open_guide.set_halign(Gtk.Align.START)
        self.open_guide.connect("clicked", lambda _b: self.show_guide())
        box.append(self.open_guide)
        self.guide_label = Gtk.Label(xalign=0, label="The steps appear here after a build.")
        self.guide_label.set_wrap(True)
        self.guide_label.set_selectable(True)
        self.guide_label.add_css_class("dim-label")
        box.append(self.guide_label)
        link = Gtk.LinkButton(uri=OPEN_CORE_GUIDE, label="OpenCore Install Guide, for reference")
        box.append(link)
        return box

    def _page_write(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        warning = Gtk.Label(xalign=0)
        warning.set_wrap(True)
        warning.add_css_class("warning")
        warning.set_text("Everything on the chosen stick is erased. Pick the stick carefully.")
        box.append(warning)
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        row.append(Gtk.Label(label="USB stick"))
        self.stick_drop = Gtk.DropDown.new_from_strings(["No USB stick found"])
        self.stick_drop.set_hexpand(True)
        self.stick_drop.connect("notify::selected", lambda *_a: self._stick_changed())
        row.append(self.stick_drop)
        self.stick_refresh = Gtk.Button(label="Refresh")
        self.stick_refresh.connect("clicked", lambda _b: self.fill_sticks())
        row.append(self.stick_refresh)
        box.append(row)
        self.stick_info = Gtk.Label(xalign=0)
        self.stick_info.set_wrap(True)
        self.stick_info.add_css_class("dim-label")
        box.append(self.stick_info)
        self.full_installer = Gtk.CheckButton(
            label="Put Apple's full macOS installer on the stick too (32 GB or more, second exFAT partition)")
        self.full_installer.connect("toggled", lambda *_a: self._stick_changed())
        box.append(self.full_installer)
        recovery_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        self.recovery_button = Gtk.Button(label="Use a recovery image I already have...")
        self.recovery_button.connect("clicked", lambda _b: self.pick_recovery())
        recovery_row.append(self.recovery_button)
        self.recovery_label = Gtk.Label(xalign=0)
        self.recovery_label.set_hexpand(True)
        self.recovery_label.set_wrap(True)
        self.recovery_label.add_css_class("dim-label")
        self.recovery_label.set_text("Apple's recovery image is downloaded after the stick is erased.")
        recovery_row.append(self.recovery_label)
        box.append(recovery_row)
        self.write_note = Gtk.Label(xalign=0)
        self.write_note.set_wrap(True)
        self.write_note.add_css_class("dim-label")
        self.write_note.set_text("1401 downloads macOS from Apple onto the stick, adds the startup files, and "
                                 "reads them back. A 16 GB stick is enough for the online installer.")
        box.append(self.write_note)
        return box

    def _page_done(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        text = Gtk.Label(xalign=0)
        text.set_wrap(True)
        text.set_text("The macOS stick is ready.\n\n"
                      "1. Restart and open the board's boot menu (the key is in the BIOS steps), then choose the "
                      "stick.\n"
                      "2. In the 1401 boot menu choose \"Install macOS\" and follow Apple's installer. The screen can "
                      "stay still for up to two minutes while macOS is read from the stick: do not restart.\n"
                      "3. When macOS is running, open the NullMoth folder on the stick to finish the NVIDIA driver, "
                      "if this PC needed it.")
        box.append(text)
        return box

    # --- state --------------------------------------------------------------------------------------------------

    def go(self, page):
        if self.busy or page < 0 or page >= len(STEPS):
            return
        self.page = page
        self.stack.set_visible_child_name(f"page{page}")
        self.title.set_text(STEPS[page])
        for index, label in enumerate(self.side_labels):
            label.remove_css_class("heading")
            label.remove_css_class("dim-label")
            if index == page:
                label.add_css_class("heading")
            elif index > page:
                label.add_css_class("dim-label")
        self.back.set_sensitive(0 < page < len(STEPS) - 1)
        text = "Continue"
        if page == 0:
            text = "Get started"
        elif page == 1 and not self.scanned:
            text = "Check this PC"
        elif page == 2 and not self.built:
            text = "Build"
        elif page == 4 and not self.written:
            text = "Erase and create"
        elif page == 5:
            text = "Close"
        self.next.set_label(text)
        self._set_note(page)
        self.log_scroller.set_visible(page in (1, 2, 4))
        self.progress.set_visible(self.busy and page in (1, 2, 4))
        if page == 4:
            self.fill_sticks()

    def on_next(self):
        if self.busy:
            return
        if self.page == 0:
            self.go(1)
        elif self.page == 1:
            self.start_scan()
        elif self.page == 2:
            if self.built:
                self.go(3)
            else:
                self.start_build()
        elif self.page == 3:
            self.go(4)
        elif self.page == 4:
            if self.written:
                self.go(5)
            else:
                self._confirm_write()
        elif self.page == 5:
            self.close()

    def _set_note(self, page):
        if page == 0:
            self.note.set_text("A guided macOS install for this PC, built from the hardware the check finds.")
        elif page == 1:
            self.note.set_text("This PC was checked. Continue, or check it again." if self.scanned else
                               "1401 reads this PC's hardware and firmware tables. Nothing is changed.")
        elif page == 2:
            self.note.set_text(self.summary.splitlines()[0] if self.built and self.summary else
                               "Choose the macOS release for this PC, then build and validate the startup files.")
        elif page == 3:
            self.note.set_text("These BIOS suggestions follow your scan and startup files. Changes here happen by "
                               "hand in the firmware setup.")
        elif page == 4:
            self.note.set_text("Plug in the USB stick that will become the macOS installer. Everything on it is "
                               "erased.")
        else:
            self.note.set_text("Done. Keep the stick until macOS is installed and running.")

    def _check_engine(self):
        report = os.path.join(REPO, "p1401", "scan.py")
        if not os.path.isfile(report):
            self._message("The engine is missing",
                          f"p1401 was not found at {REPO}. Run 1401 from the repository, or from the folder the "
                          "Linux build installed it in.", Gtk.MessageType.ERROR)
            self.next.set_sensitive(False)
            return False
        return False

    def _set_busy(self, busy):
        self.busy = busy
        for control in self.busy_controls:
            control.set_sensitive(not busy)
        if busy:
            self.next.set_sensitive(False)
            self.progress.set_visible(self.page in (1, 2, 4))
            self.progress.set_fraction(0)
            self.progress.set_text("Working...")
            self._have_progress = False
            if self._pulse_id is None:
                self._pulse_id = GLib.timeout_add(180, self._pulse)
        else:
            self.back.set_sensitive(0 < self.page < len(STEPS) - 1)
            self.next.set_sensitive(True)
            self.progress.set_fraction(0)
            self.progress.set_text("")
            self.progress.set_visible(False)
            if self._pulse_id is not None:
                GLib.source_remove(self._pulse_id)
                self._pulse_id = None

    def _pulse(self):
        if self.busy and not self._have_progress:
            self.progress.pulse()
        return self.busy

    def _append(self, line):
        buffer = self.log_view.get_buffer()
        buffer.insert(buffer.get_end_iter(), line + "\n")
        self._log_lines += 1
        if self._log_lines > MAX_LOG_LINES:
            start = buffer.get_start_iter()
            end = buffer.get_iter_at_line(500)
            buffer.delete(start, end)
            self._log_lines -= 500
        end = buffer.get_end_iter()
        self.log_view.scroll_to_iter(end, 0.0, False, 0.0, 0.0)
        if self.log_file:
            try:
                self.log_file.write(line + "\n")
            except OSError:
                pass

    def _run(self, label, command, done):
        if self.busy:
            return
        self._set_busy(True)
        self.last_lines = []
        self._append(f"--- {label} ---")
        self._append("$ " + quoted(command))
        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"
        env["PYTHONPATH"] = REPO + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")

        def worker():
            process = None
            try:
                process = subprocess.Popen(command, cwd=REPO, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                           stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                                           errors="replace", bufsize=1, env=env)
                for line in process.stdout:
                    GLib.idle_add(self._line, line.rstrip("\r\n"))
                code = process.wait()
            except Exception as error:  # noqa: BLE001 - shown in the window, not raised out of the thread
                GLib.idle_add(self._line, f"Could not run {command[0]}: {error}")
                code = 1
            GLib.idle_add(self._finished, code, done)

        threading.Thread(target=worker, daemon=True).start()

    def _line(self, line):
        if line.startswith("PROGRESS "):
            parts = line.split(" ", 2)
            try:
                percent = max(0, min(100, int(parts[1])))
            except (IndexError, ValueError):
                percent = 0
            self._have_progress = True
            self.progress.set_fraction(percent / 100)
            self.progress.set_text(parts[2] + f"  {percent}%" if len(parts) > 2 else f"{percent}%")
        self.last_lines.append(line)
        self._append(line)
        return False

    def _finished(self, code, done):
        self._set_busy(False)
        done(code)
        return False

    # --- check --------------------------------------------------------------------------------------------------

    def start_scan(self, force=False):
        if self.busy:
            return
        if self.scanned and not force:
            self.go(2)
            return
        self.scanned = self.built = self.written = False
        self.summary = ""
        self.guide_file = None
        self.scan_id = uuid.uuid4().hex
        self.scan_dir = os.path.join(self.work, "scan-" + self.scan_id)
        self._clear_log()
        self._run("check this PC", interpreter() + ["-m", "p1401.scan", self.scan_dir, "--run-id", self.scan_id],
                  self._scan_done)

    def _scan_done(self, code):
        report = os.path.join(self.scan_dir or "", "Report.json")
        if code != 0 or not os.path.isfile(report):
            self._message("The check did not finish",
                          "The lines in the window say why. If the password prompt was dismissed, press Check this "
                          "PC again and approve it. The log was saved to " + self.log_path,
                          Gtk.MessageType.ERROR)
            return
        self.scanned = True
        self.load_facts()
        self.check_note.set_text("This PC was checked. Continue to build the startup files.")
        self.go(1)
        self.next.set_label("Continue")
        self._save_session()

    def load_facts(self):
        while (child := self.facts.get_first_child()) is not None:
            self.facts.remove(child)
        try:
            with open(os.path.join(self.scan_dir, "Report.json"), encoding="utf-8") as fh:
                report = json.load(fh)
        except (OSError, ValueError) as error:
            self._fact("Report", f"could not be read: {error}")
            return
        board = (report.get("Motherboard") or {}).get("Name") or "unknown board"
        cpu = report.get("CPU") or {}
        cores = cpu.get("Core Count") or "?"
        processor = f"{cpu.get('Processor Name') or 'unknown processor'} ({cores} threads)"
        if cpu.get("Manufacturer"):
            processor = f"{cpu['Manufacturer']} {processor}"
        gpus = list((report.get("GPU") or {}).keys())
        network = list((report.get("Network") or {}).keys())
        drives = list((report.get("Storage Drives") or {}).keys())
        self._fact("Board", board)
        self._fact("Processor", processor)
        self._fact("Graphics", "; ".join(gpus) if gpus else "none reported")
        self._fact("Network", "; ".join(network[:3]) if network else "none reported")
        if drives:
            self._fact("Storage", "; ".join(drives[:3]))
        self._fact("Firmware", f"{(report.get('BIOS') or {}).get('Firmware Type') or 'unknown'}, "
                               f"Secure Boot {(report.get('BIOS') or {}).get('Secure Boot') or 'unknown'}")

    def _fact(self, name, value):
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        key = Gtk.Label(label=name, xalign=0)
        key.set_size_request(110, -1)
        key.add_css_class("dim-label")
        row.append(key)
        text = Gtk.Label(label=value, xalign=0)
        text.set_wrap(True)
        text.set_selectable(True)
        text.set_hexpand(True)
        row.append(text)
        self.facts.append(row)

    # --- build ---------------------------------------------------------------------------------------------------

    def _chosen_os(self):
        index = self.os_pick.get_selected()
        if index < 0 or index >= len(OS_CHOICES):
            index = 0
        return OS_CHOICES[index]

    def _build_options_changed(self):
        if self.busy:
            return
        was_built = self.built
        self.built = False
        self.written = False
        self.guide_file = None
        if was_built:
            self.build_summary.set_text("The options changed; build the startup files again.")
            self.guide_label.set_text("The steps appear here after a build.")
        if self.page == 2:
            self.next.set_label("Build")
            self.note.set_text("Choose the macOS release for this PC, then build and validate the startup files.")

    def start_build(self):
        if self.busy:
            return
        if not self.scanned:
            self.go(1)
            return
        name, darwin, legacy = self._chosen_os()
        self.efi_dir = os.path.join(self.work, "efi")
        # The build writes into the same EFI folder and starts with a clean result page. If it fails or the app is
        # closed halfway, the previous build is no longer what is on disk, so the session must not offer it.
        self.built = self.written = False
        self.summary = ""
        self.guide_file = None
        self.guide_label.set_text("The steps appear here after a build.")
        self._save_session()
        report = os.path.join(self.scan_dir, "Report.json")
        acpi = os.path.join(self.scan_dir, "ACPI")
        command = interpreter() + ["-m", "p1401", "build", report, acpi, self.efi_dir, "--json", "--macos", darwin]
        if legacy:
            command.append("--legacy")
        if self.experimental.get_active():
            command.append("--experimental-drivers")
        if self.persistent.get_active():
            command.append("--persistent-nvram-amd")
        if self.external.get_active():
            command.append("--external-target")
        if self.new_identity.get_active():
            command.append("--new-identity")
        self._clear_log()
        self.build_summary.set_text("")
        self._run("build the Mac setup", command, self._build_done)

    def _build_done(self, code):
        result = None
        start = next((i for i, line in enumerate(self.last_lines) if line.lstrip().startswith("{")), None)
        if start is not None:
            try:
                result = json.JSONDecoder().raw_decode("\n".join(self.last_lines[start:]))[0]
            except ValueError:
                result = None
        if code != 0 or not isinstance(result, dict) or not result.get("ok"):
            detail = (result or {}).get("error") or "The lines in the window say why."
            self._message("The build stopped", str(detail) + f"\n\nThe full log is in {self.log_path}.",
                          Gtk.MessageType.ERROR)
            return
        self.macos_full = str(result.get("macos_version") or "")
        self.darwin = self.macos_full.split(".")[0] or self._chosen_os()[1]
        name = MACOS_NAMES.get(self.darwin, self.darwin)
        self.summary = (f"macOS {name} for this PC, as a {result.get('smbios') or 'Mac'}. The startup files passed "
                        f"OpenCore's own check.")
        for notice in result.get("notices") or []:
            if notice and _ACPI_DUMP.search(str(notice)):
                continue
            self.summary += "\n" + str(notice)
        plan = result.get("storage_plan") or {}
        if plan.get("steps"):
            self.summary += "\n" + ("This PC's drives are behind Intel VMD, which macOS cannot read. Plan:"
                                    if plan.get("kind") == "vmd-off" else
                                    "Install macOS on a drive macOS can see. Plan:")
            for index, step in enumerate(plan["steps"], 1):
                self.summary += f"\n  {index}. {step}"
            if plan.get("bios_path"):
                self.summary += "\nBIOS: " + str(plan["bios_path"])
        for change in result.get("policy_changes") or []:
            if change.get("rule") == "known-machine":
                self.summary += f"\nSetting known to work on this processor: {change.get('after')} ({change.get('why')})"
            elif change.get("rule") == "usb-map-import":
                self.summary += f"\nUSB port map: {change.get('after')} ({change.get('why')})"
        self.build_summary.set_text(self.summary)
        self.built = True
        self.written = False
        self._save_session()
        self._make_guide()

    def _make_guide(self):
        report = os.path.join(self.scan_dir, "Report.json")
        config = os.path.join(self.efi_dir, "EFI", "OC", "config.plist")
        guide = os.path.join(self.work, "BIOS-steps.html")
        self._run("write the BIOS steps",
                  interpreter() + ["-m", "p1401.guide", report, config, "--macos", self.macos_full, "--html", guide],
                  lambda code: self._guide_done(code, guide))

    def _guide_done(self, code, guide):
        if code == 0 and os.path.isfile(guide):
            self.guide_file = guide
            self.guide_label.set_text(guide)
        else:
            self._message("The BIOS steps could not be written",
                          "The startup files are built and valid. The BIOS page is missing; check the log and press "
                          "Open the BIOS steps to try again.", Gtk.MessageType.WARNING)
        self._save_session()
        self.go(2)
        self.next.set_label("Continue")

    def show_guide(self):
        if not self.guide_file or not os.path.isfile(self.guide_file):
            if self.built:
                self._make_guide()
            return
        try:
            Gio.AppInfo.launch_default_for_uri(GLib.filename_to_uri(self.guide_file, None), None)
        except GLib.Error as error:
            self._message("Could not open the guide", str(error), Gtk.MessageType.ERROR)

    # --- stick ---------------------------------------------------------------------------------------------------

    def fill_sticks(self):
        if self.busy:
            return
        try:
            disks = linuxusb.list_disks()
        except linuxusb.UsbError as error:
            self.usb_disks = []
            self.stick_drop.set_model(Gtk.StringList.new(["Could not list disks"]))
            self.stick_info.set_text(str(error))
            return
        usable = []
        for disk in disks:
            if disk.get("BusType") != "USB" or disk.get("IsSystem") or disk.get("IsReadOnly"):
                continue
            if int(disk.get("Size") or 0) < linuxusb.MIN_DISK:
                continue
            usable.append(disk)
        self.usb_disks = usable
        labels = [f"{linuxusb.stick_name(d)}  -  {d['Path']}" for d in usable]
        if not labels:
            labels = ["No USB stick found - plug one in and press Refresh"]
        self.stick_drop.set_model(Gtk.StringList.new(labels))
        self.stick_drop.set_selected(0)
        self._stick_changed()

    def _chosen_stick(self):
        index = self.stick_drop.get_selected()
        if index < 0 or index >= len(self.usb_disks):
            return None
        return self.usb_disks[index]

    def _stick_changed(self):
        disk = self._chosen_stick()
        if disk is None:
            self.stick_info.set_text("Plug in a USB stick that can be erased. Internal disks are never offered.")
            return
        text = f"{disk['FriendlyName']}, {linuxusb.size_text(disk['Size'])}, {disk['Path']}"
        if disk["Size"] > linuxusb.MAX_DISK:
            text += ". This is larger than a normal USB stick; 1401 asks once more before erasing a drive this size."
        if self.full_installer.get_active() and disk["Size"] < 32 * linuxusb.GiB:
            text += ". The full installer needs a stick of 32 GB or more."
        self.stick_info.set_text(text)

    def pick_recovery(self):
        # Gtk.FileChooserNative rather than Gtk.FileDialog: the latter arrived in GTK 4.10 and Debian 12 ships 4.8.
        dialog = Gtk.FileChooserNative(title="Folder with BaseSystem.dmg and BaseSystem.chunklist",
                                       transient_for=self, action=Gtk.FileChooserAction.SELECT_FOLDER,
                                       accept_label="Use this folder", cancel_label="Cancel")
        dialog.connect("response", self._recovery_chosen)
        dialog.show()

    def _recovery_chosen(self, dialog, response):
        try:
            if response == Gtk.ResponseType.ACCEPT:
                folder = dialog.get_file()
                path = folder.get_path() if folder else None
                if path:
                    self.recovery_dir = path
                    self.recovery_label.set_text(path)
        finally:
            dialog.destroy()

    def _confirm_write(self):
        disk = self._chosen_stick()
        if disk is None:
            self._message("No USB stick", "Plug in a USB stick, press Refresh, and pick it from the list.",
                          Gtk.MessageType.INFO)
            return
        ok, why = linuxusb.eligible(disk, allow_large=True)
        if not ok:
            self._message("This stick cannot be used", "; ".join(why), Gtk.MessageType.ERROR)
            return
        if disk["Size"] > linuxusb.MAX_DISK and not self._ask(
                "A very large USB drive",
                f"{linuxusb.stick_name(disk)} is larger than any USB stick 1401 expects. A drive this big is usually "
                "a backup disk. Erase it anyway?", "Use this drive"):
            return
        if self.full_installer.get_active():
            if self.darwin not in ("24", "25"):
                self._message("The full installer is not available for this release",
                              "Apple publishes the full installer for macOS 15 and macOS 26 only. Turn the option off "
                              "for an older release.", Gtk.MessageType.INFO)
                return
            if disk["Size"] < 32 * linuxusb.GiB:
                self._message("The stick is too small for the full installer",
                              "The full installer needs a stick of 32 GB or more. Pick a larger stick or turn the "
                              "option off.", Gtk.MessageType.INFO)
                return
        if not self._ask("Erase this stick?",
                         f"{linuxusb.stick_name(disk)} will become the macOS installer. Everything on it will be "
                         "lost.", "Erase and create"):
            return
        if not self.full_installer.get_active():
            self.full_pkg = None
        self._prepare_driver()

    def _prepare_driver(self):
        if not os.path.isfile(os.path.join(self.efi_dir, "EFI", "OC", "config.plist")):
            self._message("The startup files are missing",
                          "Build the Mac setup again, then return to this page. The stick was not touched.",
                          Gtk.MessageType.ERROR)
            return
        self._clear_log()
        self._run("check the NVIDIA driver packages",
                  interpreter() + ["-m", "p1401.linuxusb", "prepare-driver", self.efi_dir],
                  self._driver_done)

    def _driver_done(self, code):
        if code != 0:
            self._message("The driver package could not be prepared",
                          "The stick was not touched. Check the connection and try again; the log says which "
                          "download failed.", Gtk.MessageType.ERROR)
            return
        if self.full_installer.get_active():
            self._fetch_full_installer()
        else:
            self.start_write()

    def _fetch_full_installer(self):
        folder = os.path.join(self.work, "full-installer", self.darwin)
        package = os.path.join(folder, "InstallAssistant.pkg")
        if os.path.isfile(package):
            self.full_pkg = package
            self._append(f"Using the full installer already downloaded at {package}")
            self.start_write()
            return
        os.makedirs(folder, exist_ok=True)
        self._clear_log()
        self._run("download the full macOS installer",
                  interpreter() + ["-m", "p1401.fullinstaller", "fetch", self.darwin, folder],
                  lambda code: self._full_installer_done(code, package))

    def _full_installer_done(self, code, package):
        if code != 0 or not os.path.isfile(package):
            self._message("The full installer could not be downloaded",
                          "The stick was not touched. Turn the option off to write the usual online installer, or "
                          "check the connection and try again.", Gtk.MessageType.ERROR)
            return
        self.full_pkg = package
        self.start_write()

    def start_write(self, erase_os=False):
        disk = self._chosen_stick()
        if disk is None:
            self.fill_sticks()
            return
        # linuxroot.py usb takes the writer's own arguments (write ...), not the `python -m` part: pkexec runs the
        # root helper with this list, while an already-root app runs the module directly.
        args = ["write", disk["Path"], self.efi_dir, self.darwin,
                "--profile", os.path.join(self.scan_dir, "Report.json"),
                "--stick-id", disk.get("UniqueId") or "",
                "--stick-size", str(disk["Size"]),
                "--stick-name", disk.get("FriendlyName") or "",
                "--recovery-dir", self.recovery_dir]
        if disk["Size"] > linuxusb.MAX_DISK:
            args.append("--allow-large")
        if self.full_pkg:
            args += ["--full-installer", self.full_pkg]
        if erase_os:
            args.append("--erase-os-partitions")
        if os.geteuid() == 0:
            elevated = interpreter() + ["-m", "p1401.linuxusb"] + args
        else:
            pkexec = shutil.which("pkexec")
            if not pkexec:
                self._message("policykit is missing",
                              "Writing a USB stick needs root, and pkexec was not found. Install polkit, or run "
                              "1401 from a root terminal.", Gtk.MessageType.ERROR)
                return
            elevated = [pkexec, sys.executable, os.path.join(REPO, "p1401", "linuxroot.py"), "usb"] + args
        self._clear_log()
        self._run("create the macOS stick", elevated,
                  lambda code: self._write_done(code, erase_os))

    def _write_done(self, code, erase_os):
        if code == 0:
            self.written = True
            self.built = True
            self.go(5)
            return
        held = next((line for line in self.last_lines if "1401-OS-PARTITIONS:" in line), None)
        if held and not erase_os:
            detail = held.split("1401-OS-PARTITIONS:", 1)[1].strip()
            if self._ask("This stick is not empty",
                         f"It holds {detail}\n\nThat is usually an old macOS installer, but it can also be a Mac "
                         "backup or a system. Erase it anyway?", "Erase it anyway"):
                self.start_write(erase_os=True)
                return
        if any("1401-DISK-RENUMBERED" in line for line in self.last_lines):
            self.fill_sticks()
        stop = next((line[5:].strip() for line in reversed(self.last_lines) if line.startswith("STOP ")), "")
        detail = (stop + "\n\n" if stop else "The lines in the window say why. ") + (
            "The stick may be partly written. The log is saved to " + self.log_path)
        self._message("Writing the stick did not finish", detail, Gtk.MessageType.ERROR)

    # --- small dialogs -------------------------------------------------------------------------------------------

    def _message(self, title, detail, kind=Gtk.MessageType.INFO):
        dialog = Gtk.MessageDialog(transient_for=self, modal=True, message_type=kind,
                                   buttons=Gtk.ButtonsType.OK, text=title)
        dialog.set_property("secondary-text", detail)
        loop = GLib.MainLoop()

        def response(d, _r):
            d.destroy()
            loop.quit()
        dialog.connect("response", response)
        dialog.present()
        loop.run()

    def _ask(self, title, detail, ok_label="Continue"):
        dialog = Gtk.MessageDialog(transient_for=self, modal=True, message_type=Gtk.MessageType.WARNING,
                                   buttons=Gtk.ButtonsType.NONE, text=title)
        dialog.set_property("secondary-text", detail)
        dialog.add_button("Cancel", Gtk.ResponseType.CANCEL)
        dialog.add_button(ok_label, Gtk.ResponseType.OK)
        dialog.set_default_response(Gtk.ResponseType.CANCEL)
        answer = {"ok": False}
        loop = GLib.MainLoop()

        def response(d, result):
            answer["ok"] = result == Gtk.ResponseType.OK
            d.destroy()
            loop.quit()
        dialog.connect("response", response)
        dialog.present()
        loop.run()
        return answer["ok"]

    def _clear_log(self):
        self.log_view.get_buffer().set_text("")
        self._log_lines = 0

    def _on_close(self, _window):
        if self.busy:
            self._message("1401 is still working",
                          "Wait for the current step to finish. Closing the window in the middle of a USB write can "
                          "leave the stick half erased.", Gtk.MessageType.WARNING)
            return True
        try:
            self.log_file.close()
        except OSError:
            pass
        return False


class App(Gtk.Application):
    def __init__(self, selftest=False):
        flags = Gio.ApplicationFlags.DEFAULT_FLAGS
        if selftest:
            flags |= Gio.ApplicationFlags.NON_UNIQUE
        super().__init__(application_id="com.nullmothsystems.FourteenOhOne", flags=flags)
        self.window = None
        self.selftest = selftest
        self.selftest_ok = True

    def do_activate(self):
        if self.window is None:
            self.window = Window(self)
            if self.selftest:
                GLib.idle_add(self._selftest)
                return
            self.window.present()
        else:
            self.window.present()

    def _selftest(self):
        """Build every page without touching hardware, then leave. Run with a display; no scan, no disk write."""
        try:
            for page in range(len(STEPS)):
                self.window.go(page)
                shown = self.window.stack.get_visible_child_name()
                if shown != f"page{page}":
                    raise RuntimeError(f"page {page} is not the visible page ({shown})")
            self.window.go(0)
            self.window.on_next()
            if self.window.page != 1:
                raise RuntimeError("Get started did not lead to the check")
            self.window.go(3)
            self.window.on_next()
            if self.window.page != 4:
                raise RuntimeError("the BIOS page did not lead to the stick")
            self.window.go(0)
            print("selftest: all pages built", flush=True)
        except Exception as error:  # noqa: BLE001 - the exit status carries the failure
            print(f"selftest: {type(error).__name__}: {error}", file=sys.stderr, flush=True)
            self.selftest_ok = False
            self.quit()
            return False
        self.quit()
        return False


def main():
    args = [arg for arg in sys.argv if arg != "--selftest"]
    selftest = len(args) != len(sys.argv)
    os.makedirs(state_dir(), exist_ok=True)
    app = App(selftest)
    status = app.run(args)
    if selftest and not app.selftest_ok:
        return 1
    return status


if __name__ == "__main__":
    sys.exit(main())
