"""WhateverXe: the exact releases, settings and post-install step the Windows EFI builder shares with the Mac app.

WhateverXe is a Lilu plugin that runs Apple's Tiger Lake graphics driver for selected Intel Xe-LP GPUs. The Windows
builder gets it through OpCore Simplify, which asks GitHub for the latest release; the Mac app pins 0.8.0 and its
WhateverXe Graphics package. Two builders that silently pick different versions could put a kext and a graphics stack
from different releases on one Mac, so this module is the one place the Windows side reads its pin from, and
tests/test_whateverxe_integration.py fails when it drifts from mac/Resources/nullmoth-setup.sh.

The requirements below are from the upstream README at tag 0.8.0 and the WhateverXe Graphics README at v0.4.1
(read 2026-11-11):

  - Lilu, WhateverXe.kext and the author's AMFIPass 1.4.1 Mod; WEX after Lilu; WhateverGreen off; never both AMFIPass builds.
  - csr-active-config 0x803; -allow3d -disablegfxfirmware (add -igfxdvmt only for a 60 MB DVMT).
  - macOS 15.8.x or 26.7+, and the WhateverXe Graphics package installed from macOS after the first start.

A7A0 is in upstream's Raptor Lake-H/P device table, but upstream's tested-hardware list has only Raptor Lake-U, and it
says internal eDP on Raptor Lake-H/P/U is implemented but not tested. The notice code must not turn that into a claim.
"""
VERSION = "0.8.0"
RELEASE_URL = "https://github.com/b00t0x/WhateverXe/releases/download/0.8.0/WhateverXe-0.8.0-RELEASE.zip"
RELEASE_SHA256 = "5b71e14ce10c673f6baba276183f268d7f04766d298cd34f1df0bb96f11c8e4b"
RELEASE_SIZE = 2099802

# The author's modified AMFIPass, pinned to the WhateverXe-Graphics commit whose release was read (88d64a3). Upstream
# AMFIPass is not a substitute; the graphics stack is signed for this build only.
AMFIPASS_MOD_URL = ("https://github.com/b00t0x/WhateverXe-Graphics/raw/"
                    "88d64a340e6f0d52e3f32a136c920d190ac43c53/extras/AMFIPass-v1.4.1-Mod-RELEASE.zip")
AMFIPASS_MOD_SHA256 = "71f41de42e355d2a83e6f093ef34a5b24d0a9c9a9085830b2317f1b874f56250"
AMFIPASS_MOD_SIZE = 185766

# The graphics payloads are Apple's drivers, adapted and re-signed by the author. 1401 never mirrors or redistributes
# them: the Mac app downloads this pinned package on the user's Mac after macOS starts. The Windows builder does not
# install it (it cannot: the package installs into /Library of a running macOS).
GRAPHICS_VERSION = "0.4.1"
GRAPHICS_URL = "https://github.com/b00t0x/WhateverXe-Graphics/releases/download/v0.4.1/WhateverXe-Graphics-0.4.1.pkg"
GRAPHICS_SHA256 = "7f7ce3b924ad421cff0c4f30534598858474b8c9539c4b889a461bc1d5fed02c"
GRAPHICS_SIZE = 95200578

SIP = 0x803                     # upstream README: csr-active-config 03080000
BOOT_ARGS = ("-allow3d", "-disablegfxfirmware")
DVMT_ARG = "-igfxdvmt"          # only with a 60 MB DVMT; the engine adds it and the 60 MB framebuffer properties together


def pin_downloads():
    """Make OpCore Simplify fetch the same WhateverXe and AMFIPass Mod builds the Mac app pins.

    Called once after the engine is loaded. The engine's download history compares id, URL and SHA-256, and its
    downloader verifies a non-empty sha256 before unpacking, so the pin is checked, not just recorded."""
    from Scripts.datasets import kext_data  # noqa: PLC0415 - importable once the engine is loaded

    idx = kext_data.kext_index_by_name.get("WhateverXe")
    if idx is not None:
        kext_data.kexts[idx].download_info = {"id": 721068791, "url": RELEASE_URL, "sha256": RELEASE_SHA256,
                                              "size": RELEASE_SIZE}
    info = getattr(kext_data, "AMFIPassModDownloadInfo", None)
    if isinstance(info, dict):
        info.clear()
        info.update({"id": 764696123, "url": AMFIPASS_MOD_URL, "sha256": AMFIPASS_MOD_SHA256, "size": AMFIPASS_MOD_SIZE})
