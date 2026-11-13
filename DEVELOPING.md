# Developing 1401

This is the guide for working on 1401's source. To report a bug, see `CONTRIBUTING.md`.

## How changes get in

1401 has one maintainer, who reviews and merges every change. You work in your own fork and send a pull request to
`main`; nothing lands without review. A small pull request with a clear test is merged much faster than a big one.

1. Fork the repository and clone your fork with full history (`git clone` without `--depth`): some tests compare
   against an earlier commit and fail on a shallow clone.
2. Make one change on its own branch.
3. Run the tests (below). They must pass on your machine before you open the pull request.
4. Sign off every commit (`git commit -s`, see "Sign-off" below) and open the pull request with the template filled in.

## What you need

| Part | Folder | Runs on | Needs |
|---|---|---|---|
| Engine (scan, build, BIOS guide, stick writer) | `p1401/` | any OS for the tests; Windows in the app | Python 3.12 or newer |
| Windows app (the window) | `windows/App/` | Windows | .NET SDK 8.0.425 (`global.json` pins it), Visual Studio C++ tools for `native/` |
| Mac app (after the install) | `mac/` | macOS 15 or newer | Xcode (Swift 6.3 and 6.4 both build it) |
| UEFI loader (experimental, unused by the app) | `loader/` | QEMU | Rust |
| Upstream engines (pinned copies) | `upstream/` | | do not edit; `PINNED.json` names the commits |

Most work is in the engine, and the engine's tests need no special hardware.

## Repository map

- `p1401/`: the engine. Each step the window runs is a module: `scan.py` (Check this PC), `engine.py` and
  `nullmoth.py` (Build the Mac setup and its rules), `guide.py` (Your BIOS steps), `usbwriter.py` (Create the macOS
  stick), `report.py` (Send logs). `community_gpu.py` lists other people's GPU drivers and when to mention them.
- `windows/App/`: the C# window. It runs each engine step as `python -u -m <module>` and shows its output.
- `mac/`: the Mac app that finishes the setup after macOS is installed. `mac/build.sh` builds it and runs its own tests.
- `tests/`: unit tests (`test_*.py`), the hardware corpus (`tests/corpus/`), and the corpus runner (`run_corpus.py`).
- `tools/`: release, packaging and corpus tools.
- `docs/HOW-IT-WORKS.md`: what each step does, in order. Read it before changing a step.

## Tests

### Unit tests: no hardware, about 40 seconds

```bash
python3 -m unittest discover -s tests -t . -p 'test_*.py'
```

A few tests are skipped outside Windows or without optional downloads; the skip message says why. These run on every
pull request.

### The hardware corpus: real machines, offline

The corpus is a set of public Hardware Sniffer reports from real PCs. Building all of them checks that a change to
the rules does not break a machine that worked before.

```bash
python3 tests/corpus/fetch.py          # download the reports, pinned by commit
python3 tests/run_corpus.py build      # build every machine, apply the rules, run ocvalidate
```

The fetch and build take about three minutes and about 300 MB in `out/`, and need internet access (the engine
downloads OpenCore and the kexts it picks). Then the engine's own self-tests, which read the built corpus:

```bash
python3 -m p1401.guide --selftest && python3 -m p1401.apple --selftest && python3 -m p1401.usbwriter --selftest \
  && python3 -m p1401.scan --selftest && python3 -m p1401.nullmoth --selftest
```

A self-test that says "can't run" is missing the corpus; fetch and build it first. `python3 -m p1401.selftest` is
behind the engine and fails today (its fake downloads predate the ZIP check in `p1401/archive_download.py`, and two
later arms no longer match the engine); bringing it up to date is an open task. Run the corpus whenever you change
a rule, a kext choice or anything in `p1401/engine.py` or `p1401/nullmoth.py`, and say in the pull request that it
passed.

## Building

**Windows app:**

```powershell
dotnet build windows/App/App.csproj --configuration Release --output build
```

`.github/workflows/windows-candidate.yml` is the full packaging run, step by step.

**Mac app:**

```bash
bash mac/build.sh /tmp/1401-mac
```

It builds and runs the app's own tests first, then the app, in under a minute. `mac/Resources/NullMothSafe.efi` is
checked in; rebuild it only if you change `mac/efi-safe/` (rustup's `x86_64-unknown-uefi` target, then
`cargo build --release --target x86_64-unknown-uefi` in that folder, and copy `nullmoth-safe.efi` over it). The build stops with a `STOP:` line naming the test that failed. Its output is ad-hoc signed and is for testing only;
releases are built and signed by the maintainer.

## Testing on real hardware

- **Writing a stick erases it.** Use a spare stick with nothing on it, and check the disk number 1401 shows before you
  confirm.
- Never test a change on a machine whose data you cannot lose. A wrong boot setting can leave a PC unable to start
  until the BIOS is reset.
- Say in the pull request exactly what you ran it on: the board or laptop model, CPU, GPU, and what you saw.

## Rules for changes

- **No Apple code.** Nothing written by Apple goes into this repository: no binaries, no files copied from macOS or
  its installers, and nothing generated from Apple's SDK headers. 1401 downloads what it needs from the original
  source on the user's machine.
- **Other people's code keeps its licence.** If you add or update third-party code, say where it comes from, pin the
  exact version, and add it to `NOTICE.md` and `p1401/licenses.json`. Code with no licence cannot be added; it can only
  be linked so the user downloads it from its author.
- **Downloads are pinned.** Anything 1401 downloads names its exact URL, size and SHA-256, and the engine refuses a
  file that does not match.
- **No secrets, keys or personal data** in code, tests or fixtures. Hardware reports in the corpus are public ones.
- **Fail loud.** If a step cannot do what it says, it stops and tells the user why. It never carries on as if it had
  worked.
- Keep comments plain: explain why the code does what it does.

## Sign-off

Every commit must be signed off: `git commit -s` adds a `Signed-off-by:` line with your name and email. It certifies
that you wrote the change, or have the right to submit it, under this repository's licence, as set out in the
Developer Certificate of Origin (<https://developercertificate.org>). Pull requests with unsigned commits cannot be
merged.

## Where to start

Issues labelled `help wanted` are open for anyone. Good first areas:

- A machine that fails to build: add its public Hardware Sniffer report to the corpus and fix the rule it breaks.
- The BIOS guide (`p1401/guide.py`): missing or wrong steps for a board or laptop you own.
- Bring `p1401/selftest.py` back up to date with the engine (see Tests above).
- Community GPU drivers (`p1401/community_gpu.py`): a driver that is missing, or one whose release has moved on.

Ask in the issue before starting something large, so two people do not build the same thing.
