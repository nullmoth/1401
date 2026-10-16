#!/usr/bin/env python3
"""Exercise production release parsing and numeric comparison for two-part versions."""
from pathlib import Path
import subprocess,tempfile

root=Path(__file__).resolve().parents[1]
source=(root/'Sources/main.swift').read_text()
start=source.index('    static func releaseDriverVersion(')
end=source.index('    func installedDriverVersion()',start)
production=source[start:end]
checks=r'''
for version in ["1.1", "1.11", "1.12", "1.13", "1.0.8", "1.0.12"] {
    assert(App.releaseDriverVersion("nullmoth-nvidia-" + version + ".tar.gz") == version)
}
for name in ["nullmoth-nvidia-1.tar.gz", "nullmoth-nvidia-1.1.2.3.tar.gz", "nullmoth-nvidia-1.1-beta.tar.gz", "other-1.1.tar.gz", "nullmoth-nvidia-1.1.zip"] {
    assert(App.releaseDriverVersion(name) == nil)
}
for pair in [("1.1", "1.0.12"), ("1.11", "1.1"), ("1.12", "1.11"), ("1.13", "1.12")] {
    assert(App.newer(pair.0, than: pair.1))
    assert(!App.newer(pair.1, than: pair.0))
}
assert(!App.newer("1.1.0", than:"1.1"))
assert(!App.newer("1.1", than:"1.1.0"))
print("Two-part release discovery, legacy assets and numeric update ordering passed.")
'''
with tempfile.TemporaryDirectory() as directory:
    p=Path(directory)/'versions.swift';p.write_text('import Foundation\nfinal class App {\n'+production+'}\n'+checks)
    subprocess.run(['xcrun','swift',str(p)],check=True)
