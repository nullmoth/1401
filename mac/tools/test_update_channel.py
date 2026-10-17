#!/usr/bin/env python3
"""Early updates (Sources/UpdateChannel.swift): an install that has not turned it on asks GitHub for /releases/latest
and is never shown a pre-release. One that has reads the site's channels file (/download/channels.json) and asks GitHub
for the pre-release it names, by tag; with no file, a bad file, or no newer pre-release it gets the full release. The
Swift is compiled against fixtures of the channels file and GitHub's answers; the update check, page and web view are
checked for wiring the switch through."""
import json
import pathlib
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
src = (ROOT / "Sources/UpdateChannel.swift").read_text()
main = (ROOT / "Sources/main.swift").read_text()
js = (ROOT / "Resources/app.js").read_text()
html = (ROOT / "Resources/index.html").read_text()
fails = 0


def arm(name, ok, detail=""):
    global fails
    print(("ok   " if ok else "FAIL ") + name + (f" ({detail})" if detail and not ok else ""))
    fails += not ok


check = main.split("func checkUpdate()", 1)[1].split("func startDownload(", 1)[0]
arm("without early updates the check goes straight to the full release",
    "guard UpdateChannel.isOn else { return checkRelease(UpdateChannel.latestURL, early: false) }" in check)
arm("early updates read the channels file first and fall back to the full release when it cannot be read",
    "URLRequest(url: UpdateChannel.channelsURL)" in check and "UpdateChannel.releaseURL(early: true, channels: doc)" in check
    and 'nvidia-macos-driver/releases/latest")' not in check)
arm("the release check takes the release UpdateChannel picks for the channel", "UpdateChannel.pick(payload, early: early)" in check)
arm("the page is told which channel answered and whether it is a pre-release", '"channel": early ? "early" : "stable", "prerelease": prerelease' in check)
arm("the early switch is a web view action that reports its state", 'case "early":' in main and 'send("early", ["on": UpdateChannel.isOn])' in main)
arm("the page has the switch and asks where it stands on load",
    'id="earlyon"' in html and 'id="earlyoff"' in html and 'post({ act: "early" })' in js and 'm.event === "early"' in js)
arm("a pre-release is named as such in the update line", 'data.prerelease ? "early release "' in js)
arm("the app build compiles UpdateChannel.swift", "Sources/UpdateChannel.swift" in (ROOT / "build.sh").read_text())
arm("the choice is a file in Application Support, off by default",
    'appendingPathComponent("NullMoth/early-updates.json")' in src and 'return false }' in src)
arm("the channels file is the site's /download/channels.json", '"https://nullmothsystems.com/download/channels.json"' in src)

# the channels file exactly as the site's release pipeline writes it (stable + pre-release entries)
entry = lambda v: {"version": v, "tag": "v" + v, "release": "https://github.com/nullmoth/nvidia-macos-driver/releases/tag/v" + v,  # noqa: E731
                   "set": "2026-10-17T00:00:00Z"}
fixtures = {
    "ch_pre": {"stable": entry("2.3.3"), "prerelease": entry("2.3.4"), "updated": "x"},
    "ch_none": {"stable": entry("2.3.3"), "prerelease": None, "updated": "x"},
    "ch_old": {"stable": entry("2.3.3"), "prerelease": entry("2.3.3"), "updated": "x"},   # not newer than stable
    "ch_bad": {"stable": entry("2.3.3"), "prerelease": {"tag": "v2.3.4/../../x"}},       # not a plain tag
    "rel_stable": {"tag_name": "v2.3.3", "prerelease": False, "draft": False, "assets": [{"name": "SHA256SUMS.txt"}]},
    "rel_pre": {"tag_name": "v2.3.4", "prerelease": True, "draft": False, "assets": [{"name": "x"}]},
    "rel_draft": {"tag_name": "v2.3.5", "prerelease": True, "draft": True, "assets": [{"name": "x"}]},
    "rel_noassets": {"tag_name": "v2.3.4", "prerelease": True, "draft": False},
}
with tempfile.TemporaryDirectory() as d:
    d = pathlib.Path(d)
    for k, v in fixtures.items():
        (d / f"{k}.json").write_text(json.dumps(v))
    (d / "main.swift").write_text(f'''import Foundation
func load(_ k: String) -> Any {{ try! JSONSerialization.jsonObject(with: Data(contentsOf: URL(fileURLWithPath: "{d}/" + k + ".json"))) }}
func tag(_ r: [String: Any]?) -> String {{ r?["tag_name"] as? String ?? "nil" }}
func url(_ early: Bool, _ ch: Any?) -> String {{ UpdateChannel.releaseURL(early: early, channels: ch).absoluteString }}
print(url(true, load("ch_pre")))
print(url(false, load("ch_pre")))
print(url(true, load("ch_none")), url(true, nil), url(true, load("ch_old")), url(true, load("ch_bad")))
print(tag(UpdateChannel.pick(load("rel_stable"), early: false)), tag(UpdateChannel.pick(load("rel_pre"), early: false)))
print(tag(UpdateChannel.pick(load("rel_pre"), early: true)), tag(UpdateChannel.pick(load("rel_draft"), early: true)), tag(UpdateChannel.pick(load("rel_noassets"), early: true)))
print(UpdateChannel.newer("v2.3.10", than: "v2.3.9"), UpdateChannel.newer("v2.3.2", than: "v2.3.2"))
''')
    try:
        subprocess.run(["xcrun", "swiftc", "-Onone", str(ROOT / "Sources/UpdateChannel.swift"), str(d / "main.swift"), "-o", str(d / "t")],
                       check=True, capture_output=True, text=True, timeout=600)
        out = subprocess.run([str(d / "t")], capture_output=True, text=True, timeout=60).stdout.split("\n")
    except subprocess.CalledProcessError as e:
        out = []
        arm("UpdateChannel.swift compiles", False, e.stderr[-400:])
    if out:
        latest = "https://api.github.com/repos/nullmoth/nvidia-macos-driver/releases/latest"
        arm("early updates with a newer pre-release in the channels file ask GitHub for that tag",
            out[0] == "https://api.github.com/repos/nullmoth/nvidia-macos-driver/releases/tags/v2.3.4", out[0])
        arm("the stable channel ignores the channels file", out[1] == latest, out[1])
        arm("no pre-release, no file, one not newer than stable, or a malformed tag: the full release",
            out[2] == " ".join([latest] * 4), out[2])
        arm("the stable channel takes the full release and refuses a pre-release", out[3] == "v2.3.3 nil", out[3])
        arm("the early channel takes the pre-release; a draft or an asset-less release is never offered", out[4] == "v2.3.4 nil nil", out[4])
        arm("tags compare by number, 2.3.10 above 2.3.9", out[5] == "true false", out[5])

print("Early updates: the stable channel can never be offered a pre-release; the early channel takes the one the site names."
      if not fails else f"{fails} FAILED")
sys.exit(1 if fails else 0)
