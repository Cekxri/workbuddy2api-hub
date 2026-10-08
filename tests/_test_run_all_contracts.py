"""Contract tests for tests/run_all.py - the runner's reliability promises.

run_all.py owns behavior no single suite can check for itself: a per-suite wall
clock, tree cleanup when that clock runs out, a failure line that names the real
error instead of a bare "Node.js v20.20.2", log retention, argument validation,
and "a pattern that matches nothing is not a pass". Today only the console
encoding failure mode has dedicated coverage (_test_run_all_encoding.py), so
every other promise rests on the full CI matrix noticing indirectly.

These tests drive the real runner as a subprocess against throwaway probe
suites, so each contract is exercised end to end. Nothing is mocked: the failing
probe really exits non-zero, and the hanging probe really has to be killed.

Isolation: the runner discovers suites next to itself (os.listdir(HERE)), so a
byte-identical copy of run_all.py is placed in a temporary directory with the
probe suites beside it. Nothing is ever written into the repository's tests/
directory, and the copy is compared against the real file first, so these tests
cannot silently drift away from the code they cover.

Run with: python tests/_test_run_all_contracts.py
No network, no credentials. Every probe file, process and log directory this
suite creates is removed in a finally block.
"""
import ctypes
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
REAL_RUNNER = os.path.join(HERE, "run_all.py")

#: A passing probe writes more lines than the runner keeps in its tail, so the
#: --logs assertion can tell "the full output" apart from "the last 25 lines".
FILLER_LINES = 40

#: Bounds are deliberately loose: they only have to separate "bounded by
#: --timeout" from "waited for the probe", which sleeps for ten minutes.
HANG_TIMEOUT = 5
HANG_SECONDS = 600
HANG_BUDGET = 60

if os.name == "nt":
    _KERNEL32 = ctypes.windll.kernel32
    _PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    _STILL_ACTIVE = 259

    def alive(pid):
        """Liveness through the OS, not tasklist.

        A locked-down host answers "Access denied" to tasklist and prints
        nothing, and a helper that greps that output then calls every pid dead.
        OpenProcess/GetExitCodeProcess answers about the process itself.
        """
        handle = _KERNEL32.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION,
                                       False, pid)
        if not handle:
            return False
        try:
            code = ctypes.c_ulong()
            if not _KERNEL32.GetExitCodeProcess(handle, ctypes.byref(code)):
                return False
            return code.value == _STILL_ACTIVE
        finally:
            _KERNEL32.CloseHandle(handle)
else:
    def alive(pid):
        try:
            os.kill(pid, 0)
        except OSError:
            return False
        return True


def wait_gone(pid, seconds=10.0):
    """True once the pid is gone; a killed process is not gone instantly."""
    deadline = time.time() + seconds
    while time.time() < deadline:
        if not alive(pid):
            return True
        time.sleep(0.2)
    return not alive(pid)


def kill_best_effort(pid):
    """Tidy up a probe process the runner could not reach on this host."""
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/F", "/PID", str(pid)],
                           stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, timeout=30)
        else:
            os.kill(pid, signal.SIGKILL)
    except Exception:
        pass


#: A parent that starts a grandchild and reports its pid. Used both as the
#: hanging probe and, unmodified, to ask the host what it permits. The
#: grandchild is given a working directory outside the scenario tree, so a host
#: that cannot kill it still leaves the scenario directory removable.
TREE_PROBE = (
    "import json, os, subprocess, sys, tempfile, time\n"
    "child = subprocess.Popen([sys.executable, '-c',\n"
    "    'import time; time.sleep(%d)'], cwd=tempfile.gettempdir())\n"
    "with open(os.environ['PROBE_PID_FILE'], 'w', encoding='utf-8') as fh:\n"
    "    json.dump({'parent': os.getpid(), 'child': child.pid}, fh)\n"
    "print('probe started', flush=True)\n"
    "time.sleep(%d)\n"
)

#: The grandchild outlives the check but not the test session, so a host that
#: refuses the tree kill cannot leave a ten-minute orphan behind.
ORPHAN_SECONDS = 120


def tree_start_kwargs():
    """The same group/session flags run_all.start_kwargs() gives a suite."""
    if os.name == "nt":
        return {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
    return {"start_new_session": True}


def host_can_kill_trees():
    """Ask this host whether the runner's tree kill actually works on it.

    Returns (can, reason). The probe repeats exactly what run_all.kill_tree()
    does - taskkill /F /T on Windows, killpg elsewhere - against a throwaway
    parent/grandchild pair. A locked-down host refuses it (taskkill answers
    "Access denied"), and the runner then falls back to killing only the direct
    child; the caller has to know which of the two it is looking at, otherwise a
    refused kill reads as a passing cleanup.
    """
    env = dict(os.environ)
    handle, pid_file = tempfile.mkstemp(prefix="runall-tree-", suffix=".json")
    os.close(handle)
    os.unlink(pid_file)
    env["PROBE_PID_FILE"] = pid_file
    proc = subprocess.Popen([sys.executable, "-c", TREE_PROBE % (ORPHAN_SECONDS,
                                                                 ORPHAN_SECONDS)],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            cwd=tempfile.gettempdir(), env=env,
                            **tree_start_kwargs())
    grand = None
    try:
        for _ in range(100):
            if os.path.exists(pid_file):
                break
            time.sleep(0.1)
        try:
            with open(pid_file, encoding="utf-8") as fh:
                grand = json.load(fh)["child"]
        except (OSError, ValueError, KeyError):
            return False, "the tree probe never reported a grandchild pid"

        permitted = False
        if os.name == "nt":
            done = subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                                  stdout=subprocess.DEVNULL,
                                  stderr=subprocess.DEVNULL, timeout=30)
            permitted = done.returncode == 0
        else:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                permitted = True
            except OSError:
                permitted = False

        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=10)
        if not permitted:
            return False, "this host refuses the tree kill"
        if wait_gone(grand, 5):
            return True, "the tree kill removed parent and grandchild"
        return False, "the tree kill was accepted but the grandchild survived"
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=10)
        if grand is not None and alive(grand):
            kill_best_effort(grand)
        try:
            os.unlink(pid_file)
        except OSError:
            pass


class Scenario(object):
    """A throwaway tests/ directory: a copy of the runner plus probe suites."""

    def __init__(self, label):
        self.uid = "%s-%s" % (label, uuid.uuid4().hex[:8])
        self.dir = tempfile.mkdtemp(prefix="runall-contracts-")
        self.tests = os.path.join(self.dir, "tests")
        os.makedirs(self.tests)
        self.runner = os.path.join(self.tests, "run_all.py")
        shutil.copyfile(REAL_RUNNER, self.runner)
        self.logs_dir = os.path.join(self.dir, "kept-logs")
        self.names = []
        self._runs = 0

    def add(self, label, body):
        """Write a probe suite and return its file name."""
        name = "_test_%s_%s.py" % (self.uid, label)
        with open(os.path.join(self.tests, name), "w", encoding="utf-8") as fh:
            fh.write(body)
        self.names.append(name)
        return name

    def run(self, *extra, **kwargs):
        """Run the sandboxed runner; return (returncode, output, seconds).

        The output goes to a file, never a pipe: a probe that survives the run
        would otherwise hold the pipe open and stall the reader.
        """
        timeout = kwargs.pop("timeout", 180)
        env = dict(os.environ)
        env.update(kwargs.pop("env", {}))
        self._runs += 1
        out_path = os.path.join(self.dir, "runner-output-%d.txt" % self._runs)
        started = time.time()
        with open(out_path, "w", encoding="utf-8") as sink:
            result = subprocess.run([sys.executable, self.runner] + list(extra),
                                    cwd=self.dir, env=env, stdout=sink,
                                    stderr=subprocess.STDOUT, timeout=timeout)
        seconds = time.time() - started
        with open(out_path, encoding="utf-8", errors="replace") as fh:
            return result.returncode, fh.read(), seconds

    def cleanup(self):
        shutil.rmtree(self.dir, ignore_errors=True)


class RunnerContractTests(unittest.TestCase):
    def setUp(self):
        self._scenarios = []

    def tearDown(self):
        for scenario in self._scenarios:
            scenario.cleanup()

    def scenario(self, label):
        created = Scenario(label)
        self._scenarios.append(created)
        return created

    # -- the copy under test ------------------------------------------------

    def test_the_sandbox_runner_is_the_real_one(self):
        """Every other check is meaningless unless the copy is byte-identical."""
        scenario = self.scenario("identity")
        with open(REAL_RUNNER, "rb") as real, open(scenario.runner, "rb") as copy:
            self.assertEqual(real.read(), copy.read(),
                             "the sandbox runner is not the repository's run_all.py")

    # -- argument validation ------------------------------------------------

    def test_a_non_positive_jobs_value_is_a_usage_error(self):
        scenario = self.scenario("jobs")
        for bad in ("0", "-3"):
            with self.subTest(jobs=bad):
                code, output, _ = scenario.run("--jobs", bad, timeout=60)
                self.assertEqual(code, 2, "expected a usage error:\n" + output)
                self.assertIn("--jobs must be a positive number of suites", output)
                self.assertIn("usage:", output)

    def test_a_non_positive_timeout_is_a_usage_error(self):
        scenario = self.scenario("timeout")
        for bad in ("0", "-1"):
            with self.subTest(timeout=bad):
                code, output, _ = scenario.run("--timeout", bad, timeout=60)
                self.assertEqual(code, 2, "expected a usage error:\n" + output)
                self.assertIn("--timeout must be a positive number of seconds",
                              output)

    def test_a_pattern_that_matches_nothing_is_not_a_pass(self):
        """A typo must not be reported as "0 passed, 0 failed" and exit 0."""
        scenario = self.scenario("nomatch")
        code, output, _ = scenario.run("no-such-suite-" + uuid.uuid4().hex,
                                       timeout=60)
        self.assertEqual(code, 2, output)
        self.assertIn("no suite matches", output)
        self.assertNotIn("0 passed", output)

    # -- failure reporting --------------------------------------------------

    def test_a_failing_probe_reports_the_real_error(self):
        """The probe really runs and really exits non-zero; nothing is mocked."""
        scenario = self.scenario("failing")
        name = scenario.add("fail", (
            "import sys\n"
            "print('probe is running')\n"
            "raise RuntimeError('probe-boom-%s')\n" % scenario.uid))
        code, output, _ = scenario.run(scenario.uid, timeout=120)
        self.assertEqual(code, 1, output)
        self.assertIn("[FAIL] %s" % name, output)
        self.assertIn("RuntimeError: probe-boom-%s" % scenario.uid, output)
        self.assertIn("0 passed, 1 failed", output)
        self.assertIn("failed: %s" % name, output)
        self.assertIn("--- last 25 lines of %s ---" % name, output)

    def test_the_failure_line_survives_a_node_style_tail(self):
        """A JS suite dies with a bare "Node.js v20.20.2"; name the reason."""
        scenario = self.scenario("nodetail")
        name = scenario.add("nodetail", (
            "import sys\n"
            "print('Traceback (most recent call last):')\n"
            "print('  File \"probe.js\", line 1, in <module>')\n"
            "print('TypeError: probe-not-a-function-%s')\n"
            "print('Node.js v20.20.2')\n"
            "sys.exit(1)\n" % scenario.uid))
        code, output, _ = scenario.run(scenario.uid, timeout=120)
        self.assertEqual(code, 1, output)
        line = [l for l in output.splitlines() if "[FAIL]" in l and name in l]
        self.assertEqual(len(line), 1, output)
        self.assertIn("TypeError: probe-not-a-function-%s" % scenario.uid,
                      line[0])
        self.assertNotIn("Node.js v20.20.2", line[0])

    # -- log retention ------------------------------------------------------

    def test_logs_dir_keeps_the_full_output_not_just_the_tail(self):
        scenario = self.scenario("logs")
        sentinel = "first-line-%s" % scenario.uid
        name = scenario.add("verbose", (
            "import sys\n"
            "print('%s')\n"
            "for i in range(%d):\n"
            "    print('filler %%d' %% i)\n"
            "print('probe-summary-%s')\n" % (sentinel, FILLER_LINES, scenario.uid)))
        code, output, _ = scenario.run(scenario.uid, "--logs", scenario.logs_dir,
                                       timeout=120)
        self.assertEqual(code, 0, output)
        kept = os.path.join(scenario.logs_dir, name + ".log")
        self.assertTrue(os.path.exists(kept), "no log kept in %s" % scenario.logs_dir)
        with open(kept, encoding="utf-8") as fh:
            kept_text = fh.read()
        # The runner echoes only the last line of a passing suite, so the first
        # line proves the kept log is the whole output rather than that echo.
        self.assertNotIn(sentinel, output)
        self.assertIn(sentinel, kept_text)
        self.assertIn("filler %d" % (FILLER_LINES - 1), kept_text)
        self.assertIn("probe-summary-%s" % scenario.uid, kept_text)

    def test_a_failed_probe_points_at_its_kept_log(self):
        scenario = self.scenario("logsfail")
        name = scenario.add("logfail", (
            "import sys\n"
            "print('probe is running')\n"
            "sys.exit(3)\n"))
        code, output, _ = scenario.run(scenario.uid, "--logs", scenario.logs_dir,
                                       timeout=120)
        self.assertEqual(code, 1, output)
        self.assertIn("full output: %s" % os.path.join(scenario.logs_dir,
                                                       name + ".log"), output)

    # -- the wall clock -----------------------------------------------------

    def test_a_hanging_probe_is_bounded_and_its_tree_is_reaped(self):
        """The probe sleeps for ten minutes; --timeout has to end it."""
        scenario = self.scenario("hang")
        name = scenario.add("hang", TREE_PROBE % (ORPHAN_SECONDS, HANG_SECONDS))
        pid_file = os.path.join(scenario.dir, "hang-pids.json")
        code, output, seconds = scenario.run(scenario.uid, "--timeout",
                                             str(HANG_TIMEOUT), timeout=HANG_BUDGET + 60,
                                             env={"PROBE_PID_FILE": pid_file})
        self.assertEqual(code, 1, output)
        self.assertIn("timed out after %ds" % HANG_TIMEOUT, output)
        self.assertIn("[FAIL] %s" % name, output)
        self.assertLess(seconds, HANG_BUDGET,
                        "run_all.py was not bounded by --timeout: %.1fs" % seconds)

        with open(pid_file, encoding="utf-8") as fh:
            pids = json.load(fh)
        parent, grand = pids["parent"], pids["child"]

        can, why = host_can_kill_trees()
        if can:
            self.assertTrue(wait_gone(grand, 10),
                            "the timed-out suite's grandchild %d survived; "
                            "tree cleanup did not happen" % grand)
        else:
            # The runner falls back to killing the direct child here, so the
            # descendant check cannot be made on this host. Say so loudly
            # instead of turning a refused kill into a green check.
            print("  [NOTE] %s; only the direct child is checked here" % why,
                  flush=True)
        try:
            self.assertTrue(wait_gone(parent, 10),
                            "the timed-out suite %d was not reaped" % parent)
        finally:
            if alive(grand):
                kill_best_effort(grand)

    # -- serial and parallel agree -----------------------------------------

    def test_jobs_1_and_4_agree_on_the_pass_fail_set(self):
        scenario = self.scenario("jobsagree")
        for label in ("alpha", "beta"):
            scenario.add(label, "print('probe-%s-ok')\n" % label)
        for label in ("gamma", "delta"):
            scenario.add(label, (
                "import sys\n"
                "print('probe-%s-running')\n"
                "raise RuntimeError('probe-%s-boom')\n" % (label, label)))

        serial_code, serial, _ = scenario.run(scenario.uid, "--jobs", "1",
                                              timeout=180)
        parallel_code, parallel, _ = scenario.run(scenario.uid, "--jobs", "4",
                                                  timeout=180)

        self.assertEqual(serial_code, 1, serial)
        self.assertEqual(parallel_code, 1, parallel)
        self.assertIn("2 passed, 2 failed", serial)
        self.assertIn("2 passed, 2 failed", parallel)
        # Completion order is not fixed under --jobs > 1, so compare the sets.
        self.assertEqual(_failed_set(serial), _failed_set(parallel),
                         "serial and parallel disagreed:\n%s\n%s"
                         % (serial, parallel))
        self.assertEqual(_failed_set(serial), set(scenario.names[2:]))
        self.assertIn("--jobs 1", serial)
        self.assertIn("--jobs 4", parallel)


def _failed_set(output):
    for line in output.splitlines():
        if line.strip().startswith("failed:"):
            return {part.strip() for part in line.split(":", 1)[1].split(",")}
    return set()


if __name__ == "__main__":
    unittest.main(verbosity=2)
