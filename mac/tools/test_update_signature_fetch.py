#!/usr/bin/env python3
"""The update's signature fetch (syncGet in main.swift) works from inside a shared-session completion handler.

User report 10-17: "my app can NEVER update itself ... it always says signature could not be downloaded", while the
.sig sat on the release page and downloaded fine with curl. updateApp() fetches the signature from inside the
URLSession.shared download completion handler; the shared session runs its handlers on one serial queue, so a nested
shared-session task's handler could never run until the outer one returned, and the synchronous wait expired every
time. syncGet now uses a session of its own.

This compiles the shipping syncGet (lifted from main.swift, https guard relaxed to the test's local server) with a
probe that calls it from inside a URLSession.shared completion handler, against a local HTTP server. The negative
control is the old shape (shared session) in the same position: it must come back empty after its timeout."""
import http.server
import os
import pathlib
import re
import subprocess
import sys
import tempfile
import threading
import time

root = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else pathlib.Path(__file__).resolve().parents[1])
src = (root / 'Sources/main.swift').read_text()
fails = 0


def check(name, ok, detail=''):
    global fails
    print(('ok   ' if ok else 'FAIL ') + name + (f' ({detail})' if detail else ''))
    if not ok:
        fails += 1


start = src.index('func syncGet(_ url: URL, timeout: TimeInterval) -> Data? {')
end = src.index('\n}\n', start) + 3
shipping = src[start:end]
guard = 'guard url.scheme == "https" else { return nil }'
if shipping.count(guard) != 1:
    sys.exit('syncGet changed shape (the https guard) - this check is UNKNOWN, not clean')
shipping = shipping.replace(guard, 'guard url.scheme == "http" else { return nil }')
check('syncGet does not run on URLSession.shared', 'URLSession.shared' not in shipping)
check('syncGet still refuses anything but https', guard in src[start:end])

OLD = '''
func oldGet(_ url: URL, timeout: TimeInterval) -> Data? {
    var out: Data? = nil
    let sem = DispatchSemaphore(value: 0)
    var rq = URLRequest(url: url); rq.timeoutInterval = timeout
    URLSession.shared.dataTask(with: rq) { d, resp, _ in
        if (resp as? HTTPURLResponse)?.statusCode == 200 { out = d }
        sem.signal()
    }.resume()
    _ = sem.wait(timeout: .now() + timeout + 5)
    return out
}
'''
PROBE = '''
import Foundation
%s
%s
let url = URL(string: CommandLine.arguments[1])!
let mode = CommandLine.arguments[2]
let done = DispatchSemaphore(value: 0)
// The outer task is on URLSession.shared, exactly like updateApp()'s download: its handler is where the fetch runs.
URLSession.shared.dataTask(with: url) { _, _, _ in
    let t0 = Date()
    let got = mode == "new" ? syncGet(url, timeout: 2) : oldGet(url, timeout: 2)
    print(got.map { "GOT \\($0.count) " } ?? "NIL ", Int(Date().timeIntervalSince(t0)))
    done.signal()
}.resume()
_ = done.wait(timeout: .now() + 30)
'''


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


with tempfile.TemporaryDirectory() as tmp:
    pathlib.Path(tmp, 'app.zip.sig').write_text('c2lnbmF0dXJlLWJ5dGVz\n')
    handler = lambda *a, **k: Quiet(*a, directory=tmp, **k)  # noqa: E731
    server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f'http://127.0.0.1:{server.server_address[1]}/app.zip.sig'
    probe = pathlib.Path(tmp, 'probe.swift')
    probe.write_text(PROBE % (shipping, OLD))
    binary = pathlib.Path(tmp, 'probe')
    build = subprocess.run(['xcrun', 'swiftc', '-O', str(probe), '-o', str(binary)], capture_output=True, text=True)
    check('the probe compiles with the shipping syncGet', build.returncode == 0, build.stderr.strip()[-400:])
    if build.returncode == 0:
        t = time.monotonic()
        new = subprocess.run([str(binary), url, 'new'], capture_output=True, text=True, timeout=60).stdout.strip()
        check('the shipping fetch returns the signature from inside a shared-session handler',
              new.startswith('GOT 21'), new)
        check('and it comes back at once, not at the timeout', time.monotonic() - t < 5, f'{time.monotonic() - t:.1f} s')
        old = subprocess.run([str(binary), url, 'old'], capture_output=True, text=True, timeout=60).stdout.strip()
        check('negative control: the old shared-session fetch in the same position comes back empty after its timeout',
              old.startswith('NIL') and re.search(r'\d+$', old) and int(old.rsplit(' ', 1)[1]) >= 2, old)
    server.shutdown()

print(f'update signature fetch: {"PASS" if fails == 0 else f"{fails} FAIL"}')
sys.exit(1 if fails else 0)
