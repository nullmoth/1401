import Foundation

var failures = 0
func arm(_ name: String, _ ok: Bool) { print((ok ? "  ok   " : "  FAIL ") + name); if !ok { failures += 1 } }

arm("a list of known ids becomes setup's value, in the catalog's order", Experimental.argument(["icb", "kbl", "tgp"]) == "kbl,tgp,icb")
arm("an empty list means none are on", Experimental.argument([String]()) == "none")
arm("an unknown id refuses the whole list", Experimental.argument(["kbl", "fetchcopy"]) == nil && Experimental.argument(["NVMTL_FETCH_COPY"]) == nil)
arm("the HID route without the keyboard backlight is refused", Experimental.argument(["kblhid"]) == nil && Experimental.argument(["kbl", "kblhid"]) == "kbl,kblhid")
arm("a non-list and a list of non-strings are refused", Experimental.argument("kbl") == nil && Experimental.argument([1, 2]) == nil && Experimental.argument(nil) == nil)
arm("repeats are folded", Experimental.argument(["xvt", "xvt"]) == "xvt")
arm("a shell-looking id is refused", Experimental.argument(["kbl; rm -rf /"]) == nil)
arm("the record's ON= lines are read and unknown lines ignored", Experimental.on(record: "ON=kbl\nARG=kbl:nmkbl=1\nON=bogus\nON=icb\n") == ["kbl", "icb"])
arm("the newest Intel graphics item is in the catalog", Experimental.argument(["hybrid20"]) == "hybrid20")
arm("idle GPU deep sleep is in the catalog", Experimental.argument(["rtd3"]) == "rtd3")
arm("the list has no fetch-copy entry", !Experimental.ids.contains { $0.lowercased().contains("fetch") })
if failures > 0 { exit(1) }
