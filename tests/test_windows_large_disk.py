"""A USB disk above the writer's large-disk limit gets its own warning, not an automatic --allow-large.

The writer refuses a USB disk larger than 256 GiB unless --allow-large is passed. The window added that flag by
itself after the single erase prompt, so a 1-4 TB backup or data drive was one click away from being wiped as if it
were an installer stick.
"""
import pathlib
import unittest

APP = pathlib.Path(__file__).resolve().parents[1] / "windows" / "App"


class LargeDisk(unittest.TestCase):
    def test_a_large_disk_is_not_auto_allowed(self):
        src = (APP / "MainForm.cs").read_text(encoding="utf-8")
        self.assertNotIn('if (d.Size > 256UL * 1024 * 1024 * 1024) args += " --allow-large";', src)
        self.assertIn("bool allowLarge = false;", src)
        self.assertIn("1401 - erase a large USB disk?", src)
        self.assertIn("if (allowLarge) args += \" --allow-large\";", src)

    def test_the_confirmation_names_the_disk_and_defaults_to_no(self):
        src = (APP / "MainForm.cs").read_text(encoding="utf-8")
        block = src.split("bool allowLarge = false;", 1)[1].split("busy = true", 1)[0]
        self.assertIn('d.Name + " (" + d.UniqueId + ")"', block)
        self.assertIn("MessageBoxDefaultButton.Button2", block)
        self.assertIn("Cancelled: the large USB disk was not erased.", block)

    def test_the_warning_is_translated(self):
        loc = (APP / "Loc.cs").read_text(encoding="utf-8")
        self.assertIn("擦除大容量 USB 磁盘？", loc)
        self.assertIn("已取消：未擦除这块大容量 USB 磁盘。", loc)


if __name__ == "__main__":
    unittest.main()
