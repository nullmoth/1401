#!/bin/bash
# Stages a folder that runs without the rest of the checkout: the engine, the pinned upstream copies it needs, and the
# GTK window. The engine is Python, so nothing is compiled; this is a copy plus a launcher.
set -euo pipefail
cd "$(dirname "$0")/.."

OUT=${1:-dist/1401-linux}
mkdir -p "$(dirname "$OUT")"
OUT=$(realpath -m "$OUT")

python3 -m unittest tests.test_linux_usb tests.test_linux_root \
  || { echo "STOP: the Linux stick writer tests failed"; exit 1; }

if [ -n "${DISPLAY:-}${WAYLAND_DISPLAY:-}" ]; then
  python3 linux/1401.py --selftest || { echo "STOP: the window could not build its pages"; exit 1; }
else
  echo "note: no display, skipped the window self-test"
fi

rm -rf "$OUT"
mkdir -p "$OUT"
cp -a p1401 upstream vendor linux "$OUT/"
rm -f "$OUT/linux/1401.desktop"  # the staged copy gets one with an absolute Exec below
find "$OUT" -name __pycache__ -type d -prune -exec rm -rf {} +
rm -rf "$OUT/upstream/OpCore-Simplify/OCK_Files" "$OUT/upstream/OpCore-Simplify/Results"
cp LICENSE NOTICE.md README.md "$OUT/"

cat > "$OUT/1401" <<'LAUNCHER'
#!/bin/sh
# Starts 1401 from the folder this script is in. The engine downloads OpenCore and the kexts into upstream/ on first use.
set -eu
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
exec python3 -u "$here/linux/1401.py" "$@"
LAUNCHER
chmod 755 "$OUT/1401"

case $OUT in
  *[[:space:]]*) echo "STOP: the output path has a space, which a desktop entry cannot express"; exit 1 ;;
esac
sed "s|@EXEC@|$OUT/1401|" linux/1401.desktop > "$OUT/1401.desktop"
echo "built $OUT"
