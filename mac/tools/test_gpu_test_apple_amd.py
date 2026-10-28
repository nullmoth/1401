#!/usr/bin/env python3
"""The AMD/Intel test driver leaves AMD GPUs that Apple's own drivers list (they already run with Metal) and still
takes the ones macOS has no driver for. Runs the setup's real block with a stubbed ioreg and kexts made in a temp dir."""
import os, pathlib, plistlib, subprocess, tempfile, unittest

SETUP = pathlib.Path(__file__).resolve().parents[1] / "Resources/nullmoth-setup.sh"
START = "  # An AMD GPU that Apple's own drivers on this Mac list"
END = '  if [ "$GPUTEST" = on ]; then\n    [ -n "$WANT" ] || stop'


def run(gpus, want):
    s = SETUP.read_text()
    assert s.count(START) == 1 and s.count(END) == 1, "anchors moved in nullmoth-setup.sh"
    t = tempfile.mkdtemp()
    ext = os.path.join(t, "Extensions")
    for name, ids in (("AMD9500Controller", "0x67DF1002 0x67EF1002"), ("AMDRadeonX6000", "0x73BF1002 0x73A51002")):
        os.makedirs(os.path.join(ext, name + ".kext", "Contents"))
        with open(os.path.join(ext, name + ".kext", "Contents", "Info.plist"), "wb") as f:
            plistlib.dump({"IOKitPersonalities": {name: {"IOPCIMatch": ids}}}, f)
    lines = []
    for vendor, dev in gpus:   # ioreg prints both ids little-endian
        lines += ["+-o GFX", f'  "vendor-id" = <{vendor[2:]}{vendor[:2]}0000>', f'  "device-id" = <{dev[2:].lower()}{dev[:2].lower()}0000>',
                  '  "class-code" = <00000300>']
    b = os.path.join(t, "bin"); os.makedirs(b)
    with open(os.path.join(b, "ioreg"), "w") as f:
        f.write("#!/bin/bash\ncat <<'EOF'\n" + "\n".join(lines) + "\nEOF\n")
    os.chmod(os.path.join(b, "ioreg"), 0o755)
    block = s[s.index(START):s.index(END)].replace("/System/Library/Extensions", ext)
    script = (f'GPUTEST=on; WANT="{want}"\nnote() {{ echo "NOTE $*"; }}; stop() {{ echo "STOP $*"; exit 3; }}\n'
              + block + '\necho "WANT=[$WANT]"\n')
    r = subprocess.run(["/bin/bash", "-c", script], capture_output=True, text=True, timeout=30,
                       env=dict(os.environ, PATH=b + ":" + os.environ["PATH"]))
    return r.returncode, r.stdout + r.stderr


class AppleAmd(unittest.TestCase):
    def test_an_rx580_alone_is_left_to_apple_and_says_why(self):
        rc, out = run([("1002", "67DF")], "-nmxamd")
        self.assertEqual(rc, 3, out)
        self.assertIn("already runs on Apple's own driver", out)

    def test_an_rx7600_macos_has_no_driver_for_still_gets_the_test_driver(self):
        rc, out = run([("1002", "7480")], "-nmxamd")
        self.assertEqual(rc, 0, out)
        self.assertIn("WANT=[-nmxamd]", out)

    def test_apple_amd_plus_intel_goes_ahead_for_intel_only(self):
        rc, out = run([("1002", "73BF"), ("8086", "9A49")], "-nmxamd -nmxintel")
        self.assertEqual(rc, 0, out)
        self.assertIn("WANT=[-nmxintel]", out)
        self.assertIn("1002:73BF runs on Apple's own driver", out)

    def test_an_unsupported_amd_igpu_beside_an_apple_card_keeps_the_amd_driver(self):
        rc, out = run([("1002", "67DF"), ("1002", "164E")], "-nmxamd")
        self.assertEqual(rc, 0, out)
        self.assertIn("WANT=[-nmxamd]", out)


if __name__ == "__main__":
    unittest.main()
