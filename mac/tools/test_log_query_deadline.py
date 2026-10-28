"""Every bounded command in the collector stops at the run's deadline, so the watcher's 360 s kill never fires.

A Ryzen 7 5825U report (10-17, batch afb9) ended with the watcher's status 124 and a partial previous-boot kernel log:
the query was still inside its tail when the whole run was killed. With COLLECT_DEADLINE set, a query takes at most what
is left of the run, and one that starts after the deadline is skipped and says so; the files already written stay whole.
Exercises the production lshow/bounded helpers against an owned stalling command."""
from pathlib import Path
import os, re, shlex, subprocess, sys, tempfile, time, unittest
# Timings are checked against what they prove, not to the second: the suite runs these beside ~100 other tests, so a
# shell can start a second late ("after 1 s" for a 2 s deadline). A helper that ignored the deadline would run to the
# stub's 30 s stall and hit the 8 s subprocess timeout, so every bound below still fails it.
ROOT = Path(__file__).resolve().parents[1]


def helpers():
    source = (ROOT / 'Resources/nullmoth-setup.sh').read_text()
    return 'lshow() {' + source.split('lshow() {', 1)[1].split('# Copy newest files', 1)[0]


class Deadline(unittest.TestCase):
    def run_helper(self, script, deadline_in, stall=True, timeout=8):
        with tempfile.TemporaryDirectory() as directory:
            fake = Path(directory) / 'query'
            fake.write_text('#!' + sys.executable + '\nimport os,time\nprint("retained evidence",flush=True)\n'
                            'if os.environ.get("STALL"):time.sleep(30)\nraise SystemExit(3)\n')
            fake.chmod(0o755)
            text = helpers().replace('/usr/bin/log show', shlex.quote(str(fake)))
            env = dict(os.environ, QUERY=str(fake))
            if stall:
                env['STALL'] = '1'
            env['COLLECT_DEADLINE'] = str(int(time.time()) + deadline_in)
            start = time.monotonic()
            run = subprocess.run(['/bin/bash', '-c', text + '\n' + script], env=env, capture_output=True, text=True, timeout=timeout)
            return run, time.monotonic() - start

    def test_a_query_is_cut_at_the_runs_deadline_not_its_own_cap(self):
        run, elapsed = self.run_helper('lshow 30 fixture; echo STATUS=$?', deadline_in=2)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertIn('retained evidence', run.stdout)
        self.assertRegex(run.stdout, r'log query stopped after [12] s')
        self.assertIn('STATUS=143', run.stdout)
        self.assertLess(elapsed, 7)

    def test_a_query_after_the_deadline_is_skipped_and_says_so(self):
        run, elapsed = self.run_helper('lshow 30 fixture; echo STATUS=$?', deadline_in=-1)
        self.assertIn('log query skipped: the collection', run.stdout)
        self.assertNotIn('retained evidence', run.stdout)
        self.assertIn('STATUS=124', run.stdout)
        self.assertLess(elapsed, 5)

    def test_a_query_well_inside_the_deadline_keeps_its_own_cap(self):
        run, elapsed = self.run_helper('lshow 1 fixture; echo STATUS=$?', deadline_in=300)
        self.assertIn('log query stopped after 1 s', run.stdout)
        self.assertLess(elapsed, 7)

    def test_without_a_deadline_the_helper_behaves_as_before(self):
        run, _ = self.run_helper('unset COLLECT_DEADLINE; lshow 1 fixture; echo STATUS=$?', deadline_in=-100, stall=False)
        self.assertIn('STATUS=3', run.stdout)
        self.assertNotIn('skipped', run.stdout)

    def test_bounded_wraps_any_command_the_same_way(self):
        run, elapsed = self.run_helper('bounded 30 "$QUERY" extra; echo STATUS=$?', deadline_in=2)
        self.assertIn('retained evidence', run.stdout)
        self.assertRegex(run.stdout, r'stopped after [12] s')
        self.assertLess(elapsed, 7)
        run, _ = self.run_helper('bounded 5 "$QUERY"; echo STATUS=$?', deadline_in=-1)
        self.assertIn('skipped: the collection', run.stdout)
        self.assertIn('STATUS=124', run.stdout)

    def test_the_collection_sets_its_deadline_under_the_watchers_kill(self):
        source = (ROOT / 'Resources/nullmoth-setup.sh').read_text()
        self.assertIn('COLLECT_DEADLINE=$(( $(date +%s) + ${NULLMOTH_COLLECT_BUDGET:-320} ))', source)
        watch = (ROOT / 'RuntimeCheck/log_watch.c').read_text()
        self.assertIn('>= 360.0', watch)
        for command in ('bounded 40 system_profiler SPDisplaysDataType', 'bounded 30 ioreg -r -c IOPCIDevice -l -w0', 'bounded 30 kmutil showloaded'):
            self.assertIn(command, source)


if __name__ == '__main__':
    unittest.main()
