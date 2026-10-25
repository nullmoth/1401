"""Every Comment in a built config.plist must pass ocvalidate's character rule (1401 #101: a "~" failed the build)."""
import glob
import os
import pathlib
import platform
import plistlib
import subprocess
import tempfile
import unittest
import zipfile

from p1401 import community, policy, validate


def _config(comments):
    return {"UEFI": {"Drivers": [{"Arguments": "", "Comment": c, "Enabled": True, "LoadEarly": False,
                                  "Path": f"D{i}.efi"} for i, c in enumerate(comments)]},
            "Kernel": {"Add": [{"Comment": "keeps — dashes", "BundlePath": "Lilu.kext"}]}}


class LegalComments(unittest.TestCase):
    def test_tilde_and_non_ascii_are_removed_and_plain_text_is_kept(self):
        self.assertEqual(policy._legal_comment("reserves ~155 MB"), "reserves 155 MB")
        self.assertEqual(policy._legal_comment("a — b é"), "a - b ")
        self.assertEqual(policy._legal_comment("AMD USB (fix) 1.0.0, ok"), "AMD USB (fix) 1.0.0, ok")

    def test_every_comment_in_the_config_is_rewritten(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "config.plist")
            with open(path, "wb") as fh:
                plistlib.dump(_config(["fine", "reserves ~155 MB"]), fh)
            changes = policy.legal_comments(path)
            with open(path, "rb") as fh:
                cfg = plistlib.load(fh)
            self.assertEqual([c["rule"] for c in changes], ["legal-comments", "legal-comments"])
            self.assertEqual(cfg["UEFI"]["Drivers"][1]["Comment"], "reserves 155 MB")
            self.assertEqual(cfg["Kernel"]["Add"][0]["Comment"], "keeps - dashes")
            self.assertEqual(cfg["UEFI"]["Drivers"][0]["Comment"], "fine")

    def test_a_clean_config_is_left_untouched(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "config.plist")
            with open(path, "wb") as fh:
                plistlib.dump({"UEFI": {"Drivers": [{"Comment": "plain"}]}}, fh)
            before = os.stat(path).st_mtime_ns
            self.assertEqual(policy.legal_comments(path), [])
            self.assertEqual(os.stat(path).st_mtime_ns, before)

    def test_no_community_driver_text_needs_rewriting(self):
        bad = [d["what"] for d in community.DRIVERS if policy._legal_comment(d["what"]) != d["what"]]
        self.assertEqual(bad, [])


class LegalCommentsValidator(unittest.TestCase):
    """The real ocvalidate refuses the unclean comment and accepts the cleaned one."""

    @classmethod
    def setUpClass(cls):
        zips = sorted(glob.glob(os.path.join(validate.CACHE, "OpenCore-*-RELEASE.zip")))
        if not zips:
            raise unittest.SkipTest("an OpenCore release archive is required for the validator arms")
        with zipfile.ZipFile(zips[-1]) as z:
            cls.sample = plistlib.loads(z.read("Docs/Sample.plist"))
            name = {"Windows": "ocvalidate.exe", "Linux": "ocvalidate.linux"}.get(platform.system(), "ocvalidate")
            cls.validator = z.read("Utilities/ocvalidate/" + name)

    def run_validator(self, comment, clean):
        with tempfile.TemporaryDirectory() as d:
            cfg = dict(self.sample)
            cfg["UEFI"] = dict(cfg["UEFI"])
            cfg["UEFI"]["Drivers"] = [dict(e) for e in cfg["UEFI"]["Drivers"]]
            cfg["UEFI"]["Drivers"][0]["Comment"] = comment
            path = os.path.join(d, "config.plist")
            with open(path, "wb") as fh:
                plistlib.dump(cfg, fh)
            if clean:
                policy.legal_comments(path)
            exe = pathlib.Path(d) / "ocvalidate"
            exe.write_bytes(self.validator)
            exe.chmod(0o755)
            out = subprocess.run([str(exe), path], capture_output=True, text=True, timeout=60)
            return out.stdout + out.stderr

    def test_validator_refuses_the_tilde(self):
        self.assertIn("Comment contains illegal character", self.run_validator("reserves ~155 MB", clean=False))

    def test_validator_accepts_the_cleaned_comment(self):
        self.assertNotIn("Comment contains illegal character", self.run_validator("reserves ~155 MB", clean=True))


if __name__ == "__main__":
    unittest.main()
