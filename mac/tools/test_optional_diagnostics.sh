#!/bin/bash
set -euo pipefail
nd_root=$(cd "$(dirname "$0")/.." && pwd)
nd_app=${1:?Provide the built private app path}
nd_tmp=$(mktemp -d -t nullmoth-diagnostics-tests)
chmod 700 "$nd_tmp"
trap 'rm -rf "$nd_tmp"' EXIT
xcrun swiftc -Onone "$nd_root/Sources/diagnostics.swift" "$nd_root/tests/diagnostics/main.swift" -o "$nd_tmp/receipt-tests"
"$nd_tmp/receipt-tests"
xcrun clang -O1 -Wall -Wextra -Werror "$nd_root/tests/diagnostics/worker/fixture.c" -o "$nd_tmp/good"
for nd_name in forged invalid failure oversized slow; do cp "$nd_tmp/good" "$nd_tmp/$nd_name"; done
xcrun swiftc -Onone "$nd_root/Sources/diagnostics.swift" "$nd_root/tests/diagnostics/worker/main.swift" -o "$nd_tmp/worker-tests"
"$nd_tmp/worker-tests" "$nd_tmp"
node "$nd_root/tests/diagnostics/ui.cjs" "$nd_root/Resources/app.js" "$nd_root/Resources/index.html"
python3 "$nd_root/tools/test_diagnostics_prerequisites.py" "$nd_app/Contents/Resources/nullmoth-diagnostics-preflight"
