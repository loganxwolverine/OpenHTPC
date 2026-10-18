#!/usr/bin/env python3
"""1.3.2 — behavioural contracts of the menu-regeneration lifecycle.

v2 fixed the budget, the execution cap and the guarded fallback.  v3 fixed the
descendant that outlives its leader (finding Codex).  v4 fixes WHO OWNS THE
GROUP, and WHEN it is released (findings AGY on v3): the group is captured at
spawn, released before any retry / supersession / new generation, never
re-derived from a pid the caller has already reaped, and never asserted when
/proc cannot be read.

v5 closed the six blockers of the Codex review of v4 (all listed, all addressed):

- A  a supervised worker's group (``start_new_session=True``) that could not be
     CAPTURED is UNPROVEN ownership: the single-process fallback may never be
     reported as "cleaned";
- B  ownership is RETAINED until a release is PROVEN (``CLEANUP_PROVEN`` /
     ``CLEANUP_UNPROVEN``): an unproven release blocks any new worker, retry,
     next generation or success publication, with a bounded recovery transition;
- C  a partially-unreadable /proc scan is INCOMPLETE, never an empty group — it
     answers UNKNOWN, while a genuinely vanished entry is still a tolerated race;
- D  the leader is observed WITHOUT reaping (``waitid`` ``WNOWAIT``), never with
     ``proc.poll()`` before the release;
- E  the controller never calls ``poll()``/``wait()`` on ``supervisor.proc``: the
     supervisor is the sole authority and hands back a proven-successful render;
- F  test cleanup is identity-safe: a recycled pid is never signalled.

v6 closes the blockers AGY and Codex raised CONVERGENTLY against v5:

- A  ownership is a PRECONDITION (checked BEFORE the terminator, never after): a
     supervised worker whose group is absent or not proven ours NEVER reaches
     ``_terminate_single_process``, is never polled, never waited on, never
     reaped, and never signalled as a bare pid.  ``owns_group`` is strict
     (non-null, > 0, ``pgid == pid``, and never the controller's own session),
     and ``NO_GROUP`` / ``NO_GROUP_UNPROVEN`` / ``GROUP_NOT_OURS`` are UNPROVEN;
- B  the leader is reaped ONLY after a release is PROVEN — v5 still collected it
     on ``LIVENESS_UNKNOWN``, which freed the pid, dissolved the pgid that pinned
     the group and made a surviving descendant unreachable for ever;
- C  an EMPTY /proc scan is not a gone group: the kernel is asked a second time
     and only ESRCH answers GONE; a group the kernel still names is UNKNOWN;
- D  a retained generation carries an INTENT in ONE explicit slot: a blocked
     success is RESUMED rather than lost, a failure or a stall never publishes a
     fallback while a descendant may still write, and a stale publication never
     crosses into a new generation;
- E  ``RegenerationSupervisor.shutdown()`` drains, bounded and with the same
     ownership rules, on EVERY exit path — including the Flex-recovery ``execv``,
     which is REFUSED rather than replacing a controller over a retained group;
- F  test hygiene: real ``Popen`` objects are wrapped in ``try/finally``,
     collected after teardown, and the capture-failure tests exercise the REAL
     ``terminate_worker_group`` through the REAL supervisor instead of a lambda.

Measured incident (.229, 2026-10-17), reproduced TWICE on the witness machine:

- 05:09:34 a DVD insertion raised the canonical optical state to generation 93,
  the controller requested a menu regeneration, and the worker was killed by a
  fixed 5 s watchdog while it was still running — 5.17 s after the request.
  Nothing was published: flex-v1.ini kept the generation-92 content, so the DVD
  section kept answering "AUCUN DISQUE DÉTECTÉ" while the live optical badge of
  the same menu already read the DVD.
- 06:18:43 the same shape replayed on generation 94 (eject boundary): a valid
  render was published at 06:18:47.36 and destroyed by the fallback at 06:18:48.88.

This file EXECUTES the production code instead of reading it:

- real ``subprocess.Popen`` workers, started with ``start_new_session=True``,
  exactly as the controller starts them;
- the production ``RegenerationSupervisor`` — the object the controller drives —
  so the execution cap, the stale-failure rejection and the process-group
  termination are measured, not described;
- the real payload modules for the title resolution and the enrichment signature.

The assertions that still read the controller's source are labelled STRUCTURAL
and check only ORDER and ABSENCE — invariants a grep can honestly establish.
The controller's main loop itself cannot be started hermetically (importing
openhtpc-home.py renders the menu and launches Flex), which is why every
decision it takes was moved into the engine and is executed below.
"""
import ast
import importlib.util
import fcntl
import hashlib
import json
import os
import pathlib
import signal
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
PAYLOAD = ROOT / "payload"
CONTROLLER = PAYLOAD / "openhtpc-home.py"


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


session = load("optical_refresh_session_v2", PAYLOAD / "openhtpc-session-engine.py")
tmdb_module = load("optical_refresh_tmdb_v2", PAYLOAD / "openhtpc-tmdb.py")

# Real worker stand-ins.  They are processes, not mocks: the supervisor's
# accounting depends on poll(), returncode and the process group.
FAILING_WORKER = "import sys; sys.exit(3)"
SLEEPING_WORKER = "import time; time.sleep(120)"
GROUP_WITH_CHILD_WORKER = (
    "import subprocess, sys, time\n"
    "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(120)'])\n"
    "open(sys.argv[1], 'w').write(str(child.pid))\n"
    "time.sleep(120)\n"
)
# v3 — a descendant that IGNORES SIGTERM: the leader dies on SIGTERM, the
# descendant does not, so the group outlives its leader.
SIGTERM_IGNORING_CHILD = "'import signal, time; signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(120)'"
RESISTANT_DESCENDANT_WORKER = (
    "import subprocess, sys, time\n"
    "child = subprocess.Popen([sys.executable, '-c', " + SIGTERM_IGNORING_CHILD + "])\n"
    "open(sys.argv[1], 'w').write(str(child.pid))\n"
    "time.sleep(120)\n"
)
# v3 — the same descendant, but the leader exits on its own and leaves it behind.
ORPHANING_WORKER = (
    "import subprocess, sys, time\n"
    "child = subprocess.Popen([sys.executable, '-c', " + SIGTERM_IGNORING_CHILD + "])\n"
    "open(sys.argv[1], 'w').write(str(child.pid))\n"
    "time.sleep(0.6)\n"
)


def state(generation, canonical="DVD_VIDEO", legacy="DVD", **extra):
    value = {"generation": generation, "canonical_state": canonical, "state": legacy,
             "device": "/dev/sr0", "ui_state_hash": f"hash-{generation}"}
    value.update(extra)
    return value


def process_state(pid):
    """Return the single-letter process state from /proc, or None if the pid is gone."""
    try:
        return pathlib.Path(f"/proc/{pid}/stat").read_text().split(") ", 1)[1].split()[0]
    except (OSError, IndexError):
        return None


def wait_dead(pid, timeout=10.0):
    """True once the pid is gone OR is a zombie.

    A zombie has been killed and simply not reaped yet (in a container the
    reaper may be the agent process rather than init); "the child does not
    survive the termination" holds in both cases, and the caller reports which
    one it observed when that distinction matters.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        current = process_state(pid)
        if current is None or current == "Z":
            return True
        time.sleep(0.02)
    return False


def wait_pidfile(path, timeout=15.0):
    """Wait until the stand-in has WRITTEN its child's pid, then return it.

    Existence is not enough.  The file is created by ``open(..., 'w')`` and
    written just after, so reading it the instant it appears can return an empty
    string — and a RED run would then die of a ``ValueError`` instead of the
    assertion it was written for.
    """
    target = pathlib.Path(path)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            text = target.read_text().strip()
        except OSError:
            text = ""
        if text.isdigit():
            return remember(int(text))
        time.sleep(0.02)
    raise AssertionError(f"the worker stand-in never wrote a pid into {target}")


# ── identity-safe cleanup (v5, finding F) ───────────────────────────────────
# A bare ``os.kill(pid, ...)`` after the process may have been reaped can hit an
# UNRELATED process that recycled the number.  Every pid a test learns is
# recorded with its incarnation (start time) the instant it is learned, and the
# helpers refuse to signal a pid whose incarnation has since changed.
IDENTITY = {}


def remember(pid):
    """Record the current incarnation of ``pid`` (its start time); return it."""
    if pid:
        IDENTITY[int(pid)] = session.worker_starttime(int(pid))
    return pid


def kill_identity_safe(pid, sig=signal.SIGKILL):
    """Signal ``pid`` ONLY if it is still the very incarnation we recorded.

    Returns True when a signal was aimed at the recorded incarnation, False when
    the pid was gone, unreadable, never recorded, or RECYCLED — in which case
    NOTHING is signalled.
    """
    if not pid:
        return False
    pid = int(pid)
    expected = IDENTITY.get(pid)
    if expected is None:
        return False                              # never recorded: never guess
    current = session.worker_starttime(pid)
    if current is None or current != expected:
        return False                              # gone, or a recycled number
    try:
        os.kill(pid, sig)
        return True
    except (ProcessLookupError, PermissionError, OSError):
        return False


def cleanup_group(*targets):
    """Leave nothing behind, whatever the assertions did — IDENTITY-SAFELY.

    The RED runs matter as much as the GREEN ones: a test that stops halfway
    through must not leave a ``time.sleep(120)`` descendant running, or the next
    run measures a machine that is already dirty.  But the cleanup must never
    signal a RECYCLED pid: a ``Popen`` is signalled as a raw pid ONLY while it is
    UNREAPED (its number is then still pinned to that very process), and a bare
    pid goes through ``kill_identity_safe`` — which refuses a pid whose
    incarnation has changed.

    v6 (finding F): every ``Popen`` handed here is COLLECTED (``wait``) after its
    group has been dealt with.  A ``Popen`` left unreaped is both a zombie and the
    exact ``ResourceWarning`` the review of v5 found in tests 44-51.
    """
    for target in targets:
        if target is None:
            continue
        if isinstance(target, int):
            kill_identity_safe(target)
            continue
        # a real Popen: its group first, then the leader, then the collection
        try:
            session.terminate_worker_group(target, grace_s=0.2, kill_grace_s=0.2)
        except Exception:                                    # noqa: BLE001 - cleanup must never mask
            pass
        pid = getattr(target, "pid", None)
        if pid and getattr(target, "returncode", None) is None:
            # the leader is still UNREAPED: the pid is pinned, not recyclable
            try:
                os.kill(int(pid), signal.SIGKILL)
            except (ProcessLookupError, PermissionError, OSError):
                pass
        if getattr(target, "returncode", None) is None:
            try:
                target.wait(timeout=5.0)                     # collect it: no zombie left behind
            except Exception:                                # noqa: BLE001
                pass


class SignalSpy:
    """Records every ``killpg`` the code under test makes, and performs it.

    An instrument, not a stub: the kernel still receives the signal, so the
    assertions are about a real syscall, not about a mock's opinion.  It is what
    allows "nothing was aimed at that group" to be checked directly.
    """

    def __init__(self):
        self._real = os.killpg
        self.calls = []

    def __call__(self, pgid, sig):
        self.calls.append((int(pgid), int(sig)))
        return self._real(pgid, sig)

    @property
    def signals(self):
        """The calls that DELIVERED a signal: signal 0 is only a probe."""
        return [(pgid, sig) for pgid, sig in self.calls if sig != 0]


class PgidSpy:
    """Records every pgid resolution asked of the kernel."""

    def __init__(self):
        self._real = os.getpgid
        self.pids = []

    def __call__(self, pid):
        self.pids.append(int(pid))
        return self._real(pid)


class KillpgRaiser:
    """Makes the kernel refuse the GROUP call with one chosen error."""

    def __init__(self, error):
        self.error = error
        self.calls = []

    def __call__(self, pgid, sig):
        self.calls.append((int(pgid), int(sig)))
        raise self.error


class ProcRootAfterDeadline:
    """A /proc view that answers only after a file appears, from its SECOND
    listing taken past a deadline.

    It reproduces deterministically the window finding C is about.  The grace
    loop takes exactly one listing at or after its deadline (the first probe
    that crosses it ends the loop), and that listing must see the truth: the
    group is still alive, so the grace really expires.  The NEXT listing is the
    check that follows the grace — and by then the last live member of the group
    has died.  Only the instant at which the listing is taken is controlled; the
    listing itself is the REAL one, which is exactly what a race is.
    """

    def __init__(self, real, sentinel, deadline, gone_pid=None):
        self._real = pathlib.Path(real)
        self._sentinel = pathlib.Path(sentinel)
        self._deadline = deadline
        self._gone_pid = gone_pid
        self._seen = 0

    def iterdir(self):
        if time.monotonic() >= self._deadline:
            self._seen += 1
            if self._seen > 1:
                while not self._sentinel.exists():
                    time.sleep(0.01)
                if self._gone_pid is not None:
                    wait_dead(self._gone_pid, timeout=5.0)
        return self._real.iterdir()

    def __truediv__(self, name):
        # the per-pid reads (identity, state) are not what this double controls:
        # only the instant at which the GROUP is listed is.
        return self._real / name


# v4 — the leader exits on its own and leaves a descendant that ignores SIGTERM
# and then dies BY ITSELF, writing a sentinel on its way out.
CHILD_IGNORES_SIGTERM_THEN_DIES = (
    "'import pathlib, signal, sys, time; "
    "signal.signal(signal.SIGTERM, signal.SIG_IGN); "
    "open(sys.argv[1], \"w\").write(str(__import__(\"os\").getpid())); "
    "time.sleep(1.5); "
    "pathlib.Path(sys.argv[2]).write_text(\"gone\"); "
    "time.sleep(0.05)'"
)
DYING_GROUP_WORKER = (
    "import subprocess, sys, time\n"
    "child = subprocess.Popen([sys.executable, '-c', " + CHILD_IGNORES_SIGTERM_THEN_DIES +
    ", sys.argv[1], sys.argv[2]])\n"
    "time.sleep(0.4)\n"
)
# v4 — the leader FAILS (exit 3) after leaving a descendant that ignores SIGTERM.
FAILING_ORPHANING_WORKER = (
    "import subprocess, sys, time\n"
    "child = subprocess.Popen([sys.executable, '-c', " + SIGTERM_IGNORING_CHILD + "])\n"
    "open(sys.argv[1], 'w').write(str(child.pid))\n"
    "time.sleep(0.5)\n"
    "sys.exit(3)\n"
)


def drive(supervisor, limit=600, pause=0.01):
    """Replay the controller's iteration until the worker lifecycle settles."""
    events = []
    for _ in range(limit):
        events.extend(supervisor.tick())
        if supervisor.proc is None:
            break
        time.sleep(pause)
    return events


def drive_to_decision(supervisor, limit=600, pause=0.01):
    """Replay the controller's iterations until the supervisor STOPS deciding.

    ``drive`` stops as soon as no worker is running, which is right for the
    proven paths.  This one also follows the UNPROVEN ones (v6, finding D): it
    keeps iterating while a retained group is being recovered, so a test can
    observe the bounded recovery and its fail-closed exhaustion without
    hand-rolling the loop — and without ever mistaking "the worker is gone" for
    "the decision is taken".
    """
    events = []
    for _ in range(limit):
        events.extend(supervisor.tick())
        if supervisor.proc is not None:
            time.sleep(pause)
            continue
        if supervisor.cleanup_state == session.CLEANUP_UNPROVEN and not supervisor.fail_closed:
            time.sleep(pause)
            continue
        break
    return events


def failing_spawn(record):
    def spawn(generation):
        record.append(generation)
        return subprocess.Popen([sys.executable, "-c", FAILING_WORKER], start_new_session=True)
    return spawn


def seed_current_render(home, optical):
    """Write a disc sheet that IS current for ``optical`` (a valid render).

    v7: the content a destructive fail-closed fallback would erase.  It carries
    the exact provenance ``disc_sheet_is_current`` looks for, so the test can
    prove, by hash, that an UNPROVEN exhaustion touched nothing.
    """
    (home / ".cache/openhtpc").mkdir(parents=True, exist_ok=True)
    (home / ".local/state/openhtpc").mkdir(parents=True, exist_ok=True)
    png = home / ".cache/openhtpc/disc-sheet.png"
    png.write_bytes(b"CURRENT-VALID-RENDER\x00\x01\x02\x03")
    provenance_path = home / ".local/state/openhtpc/disc-sheet-state.json"
    provenance_path.write_text(json.dumps({
        "schema": 1, "optical_generation": int(optical.get("generation", 0) or 0),
        "canonical_state": session._optical_model.canonical_state(optical),
        "ui_state_hash": optical.get("ui_state_hash"),
        "render_identity": "real-93",
        "metadata_status": "ENRICHED", "presentation_state": "RENDERED"}))
    return png, provenance_path


def drain_via_shutdown(supervisor):
    """A drain that is EXACTLY the controller's: one bounded ``shutdown()``."""
    may_exit, _outcome, _events = supervisor.shutdown()
    return may_exit


class BudgetAndCap(unittest.TestCase):
    """The budget must outlast every inner step, and the cap must mean executions."""

    def test_01_watchdog_outlasts_every_inner_budget(self):
        self.assertGreater(session.REGENERATION_WORKER_BUDGET_S, session.DISC_VIEW_TIMEOUT_S)
        self.assertGreaterEqual(session.REGENERATION_WORKER_BUDGET_S,
                                session.DISC_VIEW_TIMEOUT_S + session.REGENERATION_WORKER_RESERVE_S)

    def test_02_the_measured_stall_of_229_is_no_longer_a_timeout(self):
        # 5.17 s is the measured elapsed time at the kill that lost generation 93.
        self.assertFalse(session.regeneration_watchdog_expired(5.17))
        self.assertFalse(session.regeneration_watchdog_expired(session.REGENERATION_WORKER_BUDGET_S))
        self.assertTrue(session.regeneration_watchdog_expired(session.REGENERATION_WORKER_BUDGET_S + 0.01))

    def test_03_the_cap_counts_executions_not_retries(self):
        self.assertEqual(session.REGENERATION_MAX_ATTEMPTS, 3)
        self.assertEqual(session.REGENERATION_MAX_RETRIES, 2)
        self.assertEqual(session.REGENERATION_MAX_RETRIES, session.REGENERATION_MAX_ATTEMPTS - 1)

    def test_04_recovery_table_is_an_execution_budget(self):
        # executions is the number of workers ALREADY started, the failed one included.
        self.assertEqual([session.regeneration_recovery("FAILED", n) for n in (1, 2, 3, 4)],
                         ["RETRY", "RETRY", "FALLBACK", "FALLBACK"])
        self.assertEqual([session.regeneration_recovery("STALLED", n) for n in (1, 2, 3, 4)],
                         ["RETRY", "RETRY", "FALLBACK", "FALLBACK"])

    def test_05_unknown_outcome_is_refused(self):
        with self.assertRaises(ValueError):
            session.regeneration_recovery("BOOL", 1)

    def test_06_the_disc_view_call_consumes_the_shared_budget(self):
        # STRUCTURAL (absence): the inner call must consume the shared constant,
        # never reintroduce a literal of its own.
        source = (PAYLOAD / "openhtpc-session-engine.py").read_text(encoding="utf-8")
        self.assertIn("timeout=DISC_VIEW_TIMEOUT_S", source)
        self.assertNotIn("timeout=12", source)


class WorkerExecutionCap(unittest.TestCase):
    """EXECUTED: the controller drives this object with real processes."""

    def test_07_a_persistently_failing_worker_runs_exactly_three_times(self):
        record = []
        supervisor = session.RegenerationSupervisor(
            spawn=failing_spawn(record),
            current_optical=lambda: state(93),
        )
        supervisor.request(93)
        events = drive(supervisor)
        self.assertEqual(len(record), 3, f"exactly 1 initial attempt + 2 retries: {record}")
        self.assertEqual(record, [93, 93, 93])
        self.assertEqual(supervisor.executions, 3)
        self.assertEqual(events.count("RETRY"), 2)
        self.assertEqual(events[-1], "FALLBACK")

    def test_08_no_fourth_execution_ever_happens(self):
        record = []
        supervisor = session.RegenerationSupervisor(
            spawn=failing_spawn(record),
            current_optical=lambda: state(93),
        )
        supervisor.request(93)
        drive(supervisor)
        for _ in range(50):
            supervisor.tick()
        self.assertEqual(len(record), 3)
        self.assertIsNone(supervisor.proc)

    def test_09_a_successful_render_frees_the_budget_again(self):
        record = []
        supervisor = session.RegenerationSupervisor(
            spawn=failing_spawn(record),
            current_optical=lambda: state(93),
        )
        try:
            supervisor.request(93)
            supervisor.executions = 3
            supervisor.note_published()
            self.assertEqual(supervisor.executions, 0)
            self.assertEqual(session.regeneration_recovery("FAILED", supervisor.executions), "RETRY")
        finally:
            cleanup_group(supervisor.proc)


class StaleFailure(unittest.TestCase):
    """EXECUTED: an error of G must never publish a fallback for G+1."""

    def _drive_with_generation_switch(self, home, switch_before_last_resolution):
        holder = {"current": state(93)}
        record = []
        supervisor = session.RegenerationSupervisor(
            spawn=failing_spawn(record),
            current_optical=lambda: holder["current"],
            home=home,
            install=PAYLOAD,
        )
        supervisor.request(93)
        events = []
        for _ in range(600):
            events.extend(supervisor.tick())
            if supervisor.proc is None:
                break
            # Let the first two attempts fail on generation 93, then let a newer
            # generation arrive while the third worker is still running.
            if switch_before_last_resolution and supervisor.executions == 3:
                holder["current"] = state(94, "DRIVE_PRESENT_NO_MEDIA", "EMPTY")
            time.sleep(0.01)
        return events, holder, record

    def test_10_a_failure_of_93_publishes_nothing_for_94(self):
        with tempfile.TemporaryDirectory() as raw:
            home = pathlib.Path(raw)
            events, holder, record = self._drive_with_generation_switch(home, True)
            self.assertEqual(len(record), 3)
            self.assertEqual(holder["current"]["generation"], 94)
            self.assertIn("STALE_FAILURE", events)
            self.assertNotIn("FALLBACK", events)
            self.assertFalse((home / ".local/state/openhtpc/disc-sheet-state.json").exists(),
                             "a stale failure must not stamp a fallback for the newer generation")
            self.assertFalse((home / ".cache/openhtpc/disc-sheet.png").exists())

    def test_11_the_same_failure_does_publish_for_its_own_generation(self):
        with tempfile.TemporaryDirectory() as raw:
            home = pathlib.Path(raw)
            events, holder, record = self._drive_with_generation_switch(home, False)
            self.assertEqual(len(record), 3)
            self.assertEqual(holder["current"]["generation"], 93)
            self.assertEqual(events[-1], "FALLBACK")
            provenance = json.loads((home / ".local/state/openhtpc/disc-sheet-state.json").read_text())
            self.assertEqual(provenance["optical_generation"], 93)
            self.assertEqual(provenance["render_identity"], "fallback-93")
            self.assertTrue((home / ".cache/openhtpc/disc-sheet.png").is_file())

    def test_12_the_engine_refuses_a_fallback_stamped_with_another_generation(self):
        with tempfile.TemporaryDirectory() as raw:
            home = pathlib.Path(raw)
            published = session.publish_generation_fallback(home, PAYLOAD, state(94), "MENU_REGENERATION_TIMEOUT",
                                                            expected_generation=93)
            self.assertFalse(published)
            self.assertFalse((home / ".local/state/openhtpc/disc-sheet-state.json").exists())

    def test_13_staleness_is_a_pure_comparison(self):
        self.assertTrue(session.regeneration_failure_is_stale(93, 94))
        self.assertFalse(session.regeneration_failure_is_stale(93, 93))
        self.assertTrue(session.regeneration_failure_is_stale(0, 94))
        self.assertFalse(session.regeneration_failure_is_stale(0, 0))


class SupersededWorker(unittest.TestCase):
    """EXECUTED: a new insertion during a retry must not leave the old group alive."""

    def test_14_new_generation_during_a_retry_kills_the_group_and_never_falls_back(self):
        with tempfile.TemporaryDirectory() as raw:
            home = pathlib.Path(raw)
            child_pid_file = home / "child.pid"
            holder = {"current": state(93)}
            record = []

            def spawn(generation):
                record.append(generation)
                if len(record) == 1:
                    return subprocess.Popen([sys.executable, "-c", FAILING_WORKER], start_new_session=True)
                if len(record) == 2:
                    return subprocess.Popen([sys.executable, "-c", GROUP_WITH_CHILD_WORKER, str(child_pid_file)],
                                            start_new_session=True)
                return subprocess.Popen([sys.executable, "-c", SLEEPING_WORKER], start_new_session=True)

            supervisor = session.RegenerationSupervisor(
                spawn=spawn, current_optical=lambda: holder["current"], home=home, install=PAYLOAD,
            )
            child_pid = None
            try:
                supervisor.request(93)
                # first worker fails -> the bounded retry starts the group worker
                for _ in range(400):
                    supervisor.tick()
                    if supervisor.proc is not None and supervisor.executions == 2:
                        break
                    time.sleep(0.01)
                self.assertEqual(supervisor.executions, 2)
                child_pid = wait_pidfile(child_pid_file)   # du CONTENU, pas une existence
                group_pid = supervisor.proc.pid

                # a new insertion arrives while the retry is running
                holder["current"] = state(94, "DRIVE_PRESENT_NO_MEDIA", "EMPTY")
                supervisor.request(94)

                self.assertEqual(supervisor.generation, 94)
                self.assertEqual(supervisor.executions, 1, "a superseded worker is not a failed attempt")
                self.assertEqual(len(record), 3)
                self.assertTrue(wait_dead(group_pid), "the superseded worker must not survive")
                self.assertTrue(wait_dead(child_pid), "nor any of its children")
                self.assertFalse((home / ".local/state/openhtpc/disc-sheet-state.json").exists(),
                                 "superseding a worker is not a failure: no fallback may be published")
                self.assertEqual(supervisor.terminations[0][0], 93)
                self.assertIn(supervisor.terminations[0][1], {"TERMINATED", "KILLED"})
            finally:
                # the third worker of this test is still sleeping: it must not
                # survive the test, whatever the assertions did before.
                cleanup_group(supervisor.proc, child_pid)


class ProcessGroupTermination(unittest.TestCase):
    """EXECUTED: the worker is a session leader; its children are its group."""

    def _start_group(self, raw):
        child_pid_file = pathlib.Path(raw) / "child.pid"
        parent = subprocess.Popen([sys.executable, "-c", GROUP_WITH_CHILD_WORKER, str(child_pid_file)],
                                  start_new_session=True)
        return parent, wait_pidfile(child_pid_file)

    def test_15_a_disc_view_like_child_does_not_survive_the_termination(self):
        with tempfile.TemporaryDirectory() as raw:
            parent, child_pid = self._start_group(raw)
            try:
                self.assertEqual(os.getpgid(parent.pid), parent.pid, "start_new_session makes it a group leader")
                self.assertEqual(os.getpgid(child_pid), parent.pid, "the child shares the worker's group")

                outcome = session.terminate_worker_group(parent)

                self.assertIn(outcome, {"TERMINATED", "KILLED"})
                self.assertTrue(wait_dead(parent.pid))
                self.assertTrue(wait_dead(child_pid), "the disc-view-like child must be dead too")
            finally:
                cleanup_group(parent, child_pid)

    def test_16_signalling_the_pid_alone_would_leave_the_child_alive(self):
        # Control case: proves the group kill is what saves us, not the SIGTERM.
        with tempfile.TemporaryDirectory() as raw:
            parent, child_pid = self._start_group(raw)
            try:
                parent.send_signal(signal.SIGTERM)
                parent.wait(timeout=10)
                self.assertTrue(wait_dead(parent.pid))
                self.assertFalse(wait_dead(child_pid, timeout=1.5),
                                 "the orphaned child survives a parent-only SIGTERM")
            finally:
                kill_identity_safe(child_pid)

    def test_17_an_already_dead_worker_is_reported_not_signalled(self):
        proc = subprocess.Popen([sys.executable, "-c", "pass"], start_new_session=True)
        proc.wait(timeout=10)
        self.assertEqual(session.terminate_worker_group(proc), "ALREADY_EXITED")
        self.assertEqual(session.terminate_worker_group(None), "NO_WORKER")

    def test_18_a_worker_outside_its_own_group_cannot_signal_our_group(self):
        # Safety property: without start_new_session the child shares OUR group.
        # The helper must fall back to signalling the pid alone.  The assertion
        # below is reached only because this test process was not killed.
        proc = subprocess.Popen([sys.executable, "-c", SLEEPING_WORKER])
        self.assertNotEqual(os.getpgid(proc.pid), proc.pid)
        self.assertEqual(session.terminate_worker_group(proc), "TERMINATED")
        self.assertTrue(wait_dead(proc.pid))
        self.assertGreater(os.getpid(), 0, "this process survived: our own group was never signalled")


class EnricherInterlock(unittest.TestCase):
    """EXECUTED: the enricher's intermediate writes must not spawn a doomed worker.

    The enricher rewrites the TMDb cache as the lookup progresses.  What is
    replayed here is the controller's iteration, in its order — the enricher
    completion branch, then the trigger — with a real enricher process and real
    cache files; the decisions themselves are the engine's.
    """

    ENRICHER_WRITES = (
        "import json, pathlib, sys, time\n"
        "target = pathlib.Path(sys.argv[1])\n"
        "target.parent.mkdir(parents=True, exist_ok=True)\n"
        "for status in ('AMBIGUOUS', 'PASS'):\n"
        "    target.write_text(json.dumps({'status': status, 'tmdb_id': 686, 'confidence': 0.9,\n"
        "                                  'title': 'The Perfect Storm (2000)', 'candidates': []}))\n"
        "    time.sleep(0.4)\n"
        "time.sleep(0.3)\n"
    )

    def test_19_intermediate_metadata_writes_never_trigger_a_regeneration(self):
        with tempfile.TemporaryDirectory() as raw:
            home = pathlib.Path(raw)
            optical = state(93, "DVD_VIDEO", "DVD", disc_id="disc-abc", volume_label="THE_PERFECT_STORM")
            cache = tmdb_module.cache_path(home, optical, optical["volume_label"])
            enricher = subprocess.Popen([sys.executable, "-c", self.ENRICHER_WRITES, str(cache)],
                                        start_new_session=True)
            try:
                key = session.enrichment_presentation_signature(home, optical, tmdb_module)
                self.assertTrue(key.endswith("NO_CACHE"), key)
                regenerations, suppressed = 0, 0
                deadline = time.monotonic() + 30
                while enricher.poll() is None and time.monotonic() < deadline:
                    now = session.enrichment_presentation_signature(home, optical, tmdb_module)
                    decision = session.regeneration_trigger(False, now != key, enricher.poll() is None)
                    key = now
                    if decision == "ENRICHMENT":
                        regenerations += 1        # must never happen while the enricher runs
                    elif decision == "SUPPRESSED_ENRICHMENT":
                        suppressed += 1
                    time.sleep(0.05)
                enricher.wait(timeout=10)
                self.assertGreaterEqual(suppressed, 1, "the intermediate writes must be seen and suppressed")
                self.assertEqual(regenerations, 0, "no regeneration may start during the enrichment")

                # the controller's completion branch: one regeneration, and it
                # consumes the metadata signature it carries
                regenerations += 1
                key = session.enrichment_presentation_signature(home, optical, tmdb_module)
                after = session.regeneration_trigger(
                    False, session.enrichment_presentation_signature(home, optical, tmdb_module) != key, False)
                if after == "ENRICHMENT":
                    regenerations += 1
                self.assertEqual(after, "NONE", "the settled write must not be triggered a second time")
                self.assertEqual(regenerations, 1, "one enrichment episode = exactly one settled regeneration")
            finally:
                session.terminate_worker_group(enricher)
                try:
                    enricher.wait(timeout=5)          # collect it: no orphan, no ResourceWarning
                except Exception:                     # noqa: BLE001 - cleanup must never mask
                    pass

    def test_20_a_write_landing_with_the_exit_does_not_regenerate_twice(self):
        """The residual race: the enricher writes its result and exits inside the
        same interval the controller polls, so the completion branch and the
        trigger see the change together.  Consuming the signature at completion is
        what makes the second decision NONE — the wiring is checked in
        ControllerContract.test_29.
        """
        with tempfile.TemporaryDirectory() as raw:
            home = pathlib.Path(raw)
            optical = state(93, "DVD_VIDEO", "DVD", disc_id="disc-abc", volume_label="THE_PERFECT_STORM")
            cache = tmdb_module.cache_path(home, optical, optical["volume_label"])
            key = session.enrichment_presentation_signature(home, optical, tmdb_module)
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_text(json.dumps({"status": "PASS", "title": "The Perfect Storm (2000)", "tmdb_id": 686}),
                             encoding="utf-8")
            regenerations = 1                       # the completion branch
            key = session.enrichment_presentation_signature(home, optical, tmdb_module)
            decision = session.regeneration_trigger(
                False, session.enrichment_presentation_signature(home, optical, tmdb_module) != key, False)
            self.assertEqual(decision, "NONE", "the completion must consume the write it publishes")
            self.assertEqual(regenerations, 1)

    def test_21_an_optical_transition_is_never_suppressed_by_a_running_enricher(self):
        self.assertEqual(session.regeneration_trigger(True, True, True), "OPTICAL")
        self.assertEqual(session.regeneration_trigger(True, False, True), "OPTICAL")

    def test_22_no_change_means_no_trigger(self):
        self.assertEqual(session.regeneration_trigger(False, False, True), "NONE")
        self.assertEqual(session.regeneration_trigger(False, False, False), "NONE")


class EnrichedTitle(unittest.TestCase):
    """EXECUTED: the title the menu displays must survive the publication refresh."""

    def _home_with_cache(self, raw, status="PASS", title="The Perfect Storm (2000)"):
        home = pathlib.Path(raw)
        optical = state(93, "DVD_VIDEO", "DVD", disc_id="disc-abc", volume_label="THE_PERFECT_STORM")
        (home / ".local/state/openhtpc").mkdir(parents=True, exist_ok=True)
        (home / ".local/state/openhtpc/optical-current.json").write_text(json.dumps(optical), encoding="utf-8")
        cache = tmdb_module.cache_path(home, optical, optical["volume_label"])
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps({"status": status, "title": title, "tmdb_id": 686}), encoding="utf-8")
        return home, optical

    def test_23_an_enriched_title_is_not_lost_by_a_regeneration(self):
        with tempfile.TemporaryDirectory() as raw:
            home, optical = self._home_with_cache(raw)
            enriched = session.enriched_optical(home, optical)
            self.assertEqual(enriched["tmdb_title"], "The Perfect Storm (2000)")
            self.assertIsNot(optical, enriched, "the raw state must not be mutated in place")

            target = session.write_live_optical_state(home, optical, pathlib.Path("icon.png"))
            lines = target.read_text(encoding="utf-8").splitlines()
            self.assertEqual(lines[4], session.normalized_disc_title("The Perfect Storm (2000)"),
                             "the live state must carry the enriched title, not the volume label")

    def test_24_without_a_cache_the_volume_label_is_kept(self):
        with tempfile.TemporaryDirectory() as raw:
            home = pathlib.Path(raw)
            optical = state(93, "DVD_VIDEO", "DVD", disc_id="disc-abc", volume_label="THE_PERFECT_STORM")
            target = session.write_live_optical_state(home, optical, pathlib.Path("icon.png"))
            lines = target.read_text(encoding="utf-8").splitlines()
            self.assertEqual(lines[4], session.normalized_disc_title("THE_PERFECT_STORM"))

    def test_25_a_non_dvd_state_is_never_enriched(self):
        with tempfile.TemporaryDirectory() as raw:
            home = pathlib.Path(raw)
            optical = state(94, "DRIVE_PRESENT_NO_MEDIA", "EMPTY")
            self.assertIs(session.enriched_optical(home, optical), optical)
            self.assertEqual(session.enriched_optical(home, {}), {})


class ControllerContract(unittest.TestCase):
    """STRUCTURAL: order and absence in the controller's source only."""

    def setUp(self):
        self.source = CONTROLLER.read_text(encoding="utf-8")

    def test_26_controller_publishes_request_only_after_generation_render(self):
        # The dev11 order, unchanged by this tranche.
        success = self.source.index("if successful and completed_generation")
        publish = self.source.index("pending_auto_open_generation, pending_eject_home_generation", success)
        detect = self.source.index("optical_navigation_event", publish)
        self.assertLess(success, publish)
        self.assertLess(publish, detect)

    def test_27_controller_holds_no_watchdog_literal_and_no_failure_path_of_its_own(self):
        self.assertNotIn("time.monotonic()-regenerator_started > 5", self.source)
        self.assertNotIn("regenerator_started", self.source)
        self.assertNotIn("handle_regeneration_failure", self.source)
        self.assertNotIn("regeneration_attempts", self.source)
        self.assertIn("supervisor.tick()", self.source)
        self.assertIn("engine.RegenerationSupervisor(", self.source)

    def test_28_the_controller_worker_is_a_session_leader(self):
        # Precondition of the process-group termination: without this the worker
        # is not its own group leader and its children cannot be reached.
        start = self.source.index("def spawn_regeneration_worker")
        block = self.source[start:self.source.index("def log_controller_event", start)]
        self.assertIn("start_new_session=True", block)

    def test_29_the_completion_branch_consumes_the_settled_signature(self):
        # The wiring behind test_20: the enricher-completion branch requests the
        # one settled regeneration AND refreshes the signature, so the trigger
        # that follows in the same iteration cannot request a second one.
        start = self.source.index("if enricher is not None and enricher.poll() is not None:")
        block = self.source[start:self.source.index("supervisor.tick()", start)]
        self.assertIn("request_regeneration()", block)
        self.assertIn("enrichment_key = enrichment_presentation_key()", block)
        self.assertLess(block.index("request_regeneration()"),
                        block.index("enrichment_key = enrichment_presentation_key()"))

    def test_30_the_deferral_log_reports_the_real_navigation(self):
        self.assertIn("action_type=deferred_action", self.source)
        self.assertIn("destination_page=deferred_page", self.source)
        self.assertNotIn('action_type="STATE_UPDATE", source_page="ANY", destination_page="CURRENT"', self.source)


class IncidentReplay(unittest.TestCase):
    """EXECUTED: the measured .229 timings against a real worker process."""

    def test_31_the_measured_517s_no_longer_kills_a_live_worker(self):
        clock = {"now": 0.0}
        terminations = []

        def terminate(proc):
            terminations.append(proc.pid)
            return "TERMINATED"

        proc = subprocess.Popen([sys.executable, "-c", SLEEPING_WORKER], start_new_session=True)
        try:
            supervisor = session.RegenerationSupervisor(
                spawn=lambda generation: proc,
                current_optical=lambda: state(93),
                clock=lambda: clock["now"],
                terminate=terminate,
            )
            supervisor.request(93)
            clock["now"] = 5.17                     # the measured elapsed time at the kill
            self.assertEqual(supervisor.tick(), [])
            self.assertEqual(terminations, [], "5.17 s must no longer kill the worker")
            self.assertIsNone(proc.poll(), "the real worker is still alive")

            clock["now"] = session.REGENERATION_WORKER_BUDGET_S
            self.assertEqual(supervisor.tick(), [])
            self.assertEqual(terminations, [], "the budget boundary itself does not kill")

            clock["now"] = session.REGENERATION_WORKER_BUDGET_S + 0.01
            events = supervisor.tick()
            self.assertEqual(terminations, [proc.pid])
            self.assertEqual(events, ["RETRY"], "the first stall of 93 is retried, not published")
            self.assertEqual(supervisor.executions, 2)
        finally:
            session.terminate_worker_group(proc)


class ResistantDescendant(unittest.TestCase):
    """EXECUTED (v3, finding Codex) : la mort du leader n'est pas la mort du groupe.

    V2 observait le parent — ``proc.wait()`` — et concluait « TERMINATED » alors
    qu'un descendant ignorant SIGTERM était toujours vivant.  Ces tests
    construisent ce descendant pour de vrai et exigent que le GROUPE soit mort.
    """

    def _start_resistant(self, raw):
        pidfile = pathlib.Path(raw) / "child.pid"
        parent = subprocess.Popen([sys.executable, "-c", RESISTANT_DESCENDANT_WORKER, str(pidfile)],
                                  start_new_session=True)
        child_pid = wait_pidfile(pidfile)
        time.sleep(0.3)                      # le descendant installe SIG_IGN
        return parent, child_pid

    def test_32_a_descendant_that_ignores_sigterm_does_not_survive(self):
        with tempfile.TemporaryDirectory() as raw:
            parent, child_pid = self._start_resistant(raw)
            try:
                self.assertEqual(os.getpgid(child_pid), parent.pid, "le descendant partage le groupe du worker")
                self.assertTrue(kill_identity_safe(child_pid, signal.SIGTERM),
                                "premisse : le descendant est bien signale")   # il ignore SIGTERM
                time.sleep(0.4)
                self.assertFalse(wait_dead(child_pid, timeout=0.1), "le descendant doit ignorer SIGTERM")

                # grace_s seulement : V2 accepte ce parametre, donc l'echec contre V2
                # est bien « le descendant survit », pas un TypeError de signature.
                outcome = session.terminate_worker_group(parent, grace_s=0.3)

                self.assertEqual(outcome, "KILLED",
                                 "le groupe doit recevoir SIGKILL une fois la grace expiree, "
                                 "meme si le leader est deja mort")
                self.assertTrue(wait_dead(parent.pid))
                self.assertTrue(wait_dead(child_pid), "un descendant qui ignore SIGTERM doit mourir quand meme")
            finally:
                cleanup_group(parent, child_pid)      # un run ROUGE ne laisse rien derriere lui

    def test_33_a_group_whose_leader_already_exited_is_still_killed(self):
        with tempfile.TemporaryDirectory() as raw:
            pidfile = pathlib.Path(raw) / "child.pid"
            parent = subprocess.Popen([sys.executable, "-c", ORPHANING_WORKER, str(pidfile)],
                                      start_new_session=True)
            child_pid = None
            try:
                child_pid = wait_pidfile(pidfile)
                for _ in range(400):             # le leader sort de lui-meme, non recolte
                    if process_state(parent.pid) == "Z":
                        break
                    time.sleep(0.02)
                self.assertEqual(process_state(parent.pid), "Z", "le leader doit etre sorti, non recolte")
                self.assertFalse(wait_dead(child_pid, timeout=0.1), "le descendant est toujours vivant")

                outcome = session.terminate_worker_group(parent, grace_s=0.3)

                self.assertNotEqual(outcome, "ALREADY_EXITED",
                                    "un leader mort n'est pas une preuve que le groupe a disparu")
                self.assertTrue(wait_dead(child_pid), "le descendant doit etre tue")
            finally:
                cleanup_group(parent, child_pid)

    def test_34_the_group_probes_tell_the_truth(self):
        with tempfile.TemporaryDirectory() as raw:
            parent, child_pid = self._start_resistant(raw)
            pgid = parent.pid
            try:
                self.assertTrue(session.process_group_survives(pgid))
                self.assertGreaterEqual(session.process_group_live_members(pgid), 2)
                self.assertTrue(session.process_group_is_own_session(pgid))
                self.assertFalse(session.process_group_survives(2 ** 22 + 7),
                                 "un pgid inutilise ne porte aucun processus")
                self.assertEqual(session.process_group_live_members(2 ** 22 + 7), 0)
            finally:
                cleanup_group(parent, child_pid)
            self.assertFalse(session.process_group_survives(pgid),
                             "apres la terminaison, le groupe ne survit pas")

    def test_35_a_reaped_leader_cannot_be_signalled_blindly(self):
        # Une fois le leader recolte, son pid — donc l'identifiant du groupe —
        # n'est plus connaissable : le helper refuse de signaler au lieu de
        # deviner.  C'est ce refus qui ferme la fenetre de reutilisation PID/PGID.
        proc = subprocess.Popen([sys.executable, "-c", "pass"], start_new_session=True)
        proc.wait(timeout=10)                        # recolte
        with self.assertRaises(ProcessLookupError):
            os.getpgid(proc.pid)
        self.assertEqual(session.terminate_worker_group(proc), "ALREADY_EXITED")


class GroupOwnership(unittest.TestCase):
    """EXECUTED (v4, findings A / C / D / E) : ce qui est signalé, et quand.

    Chaque test suit un vrai processus, du vrai /proc, et de vrais signaux : ce
    qui est instrumenté (killpg, getpgid) continue d'atteindre le noyau, seul
    l'enregistrement des appels est ajouté.
    """

    def test_36_an_unreaped_zombie_worker_is_reported_without_any_signal(self):
        # Finding E/1: a worker that exited and was never collected.  Its group
        # holds nothing but the zombie, so there is nothing to stop — and above
        # all nothing to resolve a number from: no signal may be aimed at that
        # group, and none may be diverted to a pid.
        proc = subprocess.Popen([sys.executable, "-c", SLEEPING_WORKER], start_new_session=True)
        try:
            os.kill(proc.pid, signal.SIGKILL)          # it dies; nothing reaps it
            for _ in range(400):
                if process_state(proc.pid) == "Z":
                    break
                time.sleep(0.02)
            self.assertEqual(process_state(proc.pid), "Z", "le worker doit etre un zombie NON recolte")
            self.assertIsNone(proc.returncode, "et Popen ne l'a pas encore recolte")

            spy = SignalSpy()
            with mock.patch.object(os, "killpg", spy):
                outcome = session.terminate_worker_group(proc)

            self.assertEqual(outcome, "ALREADY_EXITED",
                             "un groupe reduit a un zombie est mort, pas « encore present »")
            self.assertEqual(spy.signals, [],
                             "aucun signal ne doit viser un groupe dont plus rien n'est vivant")
        finally:
            cleanup_group(proc)

    def test_37_a_reaped_leader_is_never_used_to_resolve_a_pgid(self):
        # Finding A: Popen a deja recolte le leader, et un descendant vit encore.
        # Interroger le noyau sur le groupe d'un pid recycle est le seul chemin
        # par lequel un killpg peut viser un etranger : il ne doit pas exister.
        with tempfile.TemporaryDirectory() as raw:
            pidfile = pathlib.Path(raw) / "child.pid"
            parent = subprocess.Popen([sys.executable, "-c", ORPHANING_WORKER, str(pidfile)],
                                      start_new_session=True)
            child_pid = None
            try:
                child_pid = wait_pidfile(pidfile)
                parent.wait(timeout=15)                # l'appelant recolte le leader lui-meme
                self.assertIsNotNone(parent.returncode)
                self.assertFalse(wait_dead(child_pid, timeout=0.1), "le descendant vit encore")

                pgids, signals = PgidSpy(), SignalSpy()
                with mock.patch.object(os, "getpgid", pgids), mock.patch.object(os, "killpg", signals):
                    outcome = session.terminate_worker_group(parent)

                self.assertEqual(outcome, "ALREADY_EXITED")
                self.assertNotIn(parent.pid, pgids.pids,
                                 "un pid deja recolte ne doit JAMAIS servir a resoudre un pgid")
                self.assertEqual(signals.signals, [],
                                 "aucun signal ne doit partir d'un numero que le noyau a pu rendre")
            finally:
                cleanup_group(parent, child_pid)

    def test_38_a_group_that_dies_at_the_end_of_its_grace_is_gone_not_foreign(self):
        # Finding C: la grace s'acheve groupe vivant, puis le dernier descendant
        # meurt avant la verification suivante.  Un groupe disparu est GONE — v3
        # le declarait etranger (GROUP_NOT_OURS) faute d'un vivant a juger.
        with tempfile.TemporaryDirectory() as raw:
            pidfile = pathlib.Path(raw) / "child.pid"
            sentinel = pathlib.Path(raw) / "child.gone"
            parent = subprocess.Popen([sys.executable, "-c", DYING_GROUP_WORKER, str(pidfile), str(sentinel)],
                                      start_new_session=True)
            child_pid = None
            try:
                child_pid = wait_pidfile(pidfile)
                for _ in range(400):                   # le leader sort de lui-meme, non recolte
                    if process_state(parent.pid) == "Z":
                        break
                    time.sleep(0.02)
                self.assertEqual(process_state(parent.pid), "Z", "le leader doit etre sorti, non recolte")
                self.assertEqual(os.getpgid(child_pid), parent.pid, "le descendant partage le groupe")
                self.assertFalse(wait_dead(child_pid, timeout=0.1), "le descendant vit encore")

                deadline = time.monotonic() + 0.3
                view = ProcRootAfterDeadline(pathlib.Path("/proc"), sentinel, deadline, gone_pid=child_pid)
                outcome = session.terminate_worker_group(parent, grace_s=0.3, pause_s=0.05, proc_root=view)

                self.assertNotEqual(outcome, "GROUP_NOT_OURS",
                                    "un groupe qui disparait n'est pas un groupe etranger")
                self.assertIn(outcome, {"TERMINATED", "ALREADY_EXITED"},
                              "le groupe est parti: la sortie doit le dire, pas inventer un etranger")
                self.assertTrue(wait_dead(child_pid), "le descendant est mort: le groupe est vide")
            finally:
                cleanup_group(parent, child_pid)

    def test_42_a_refused_or_failed_group_signal_is_reported_not_redirected(self):
        # Finding D: apres un echec de killpg, vouloir rattraper le coup par
        # proc.send_signal() fait poll() — donc recolte le leader, libere son pid
        # — et transforme un groupe non prouve en signal a un pid.  Le refus doit
        # remonter tel quel, et le worker doit survivre a l'appel.
        cases = (
            (ProcessLookupError(), "ALREADY_EXITED", "ESRCH : le groupe n'existe plus"),
            (PermissionError(), "GROUP_NOT_OURS", "EPERM : le groupe n'est pas le notre"),
            (OSError(5, "input/output error"), "SIGNAL_ERROR", "une autre erreur n'est pas masquee"),
        )
        for error, expected, label in cases:
            with self.subTest(case=label):
                proc = subprocess.Popen([sys.executable, "-c", SLEEPING_WORKER], start_new_session=True)
                try:
                    raiser = KillpgRaiser(error)
                    with mock.patch.object(os, "killpg", raiser):
                        outcome = session.terminate_worker_group(proc, grace_s=0.2, kill_grace_s=0.2)
                    self.assertEqual(outcome, expected)
                    self.assertTrue(raiser.calls, "le groupe a bien ete interroge")
                    self.assertIsNone(proc.poll(),
                                      "le refus du GROUPE ne doit pas devenir un signal au pid")
                    self.assertIsNone(proc.returncode, "et surtout: pas de reap implicite")
                finally:
                    cleanup_group(proc)

    def test_43_an_unreadable_proc_is_unknown_and_never_asserted(self):
        # Finding E (v4), tightened by findings B/C (v6): sans /proc, un groupe
        # qui repond au signal 0 peut n'etre qu'un zombie non recolte.  La sonde
        # doit dire UNKNOWN — et la terminaison ne doit ni affirmer un succes ni
        # affirmer un survivant, NI recolter le leader pour fabriquer la preuve
        # qui lui manque : le pid epingle est ce qui garde le groupe adressable.
        with tempfile.TemporaryDirectory() as raw:
            blind = pathlib.Path(raw) / "not-a-directory"     # iterdir() ne peut pas y repondre
            blind.write_text("pas de /proc ici")

            # 1. an unreaped zombie, and a /proc that cannot say it holds only a
            #    zombie: the kernel still answers signal 0 for it.  No claim may
            #    be made about it — neither "still present" nor "terminated" —
            #    and the leader must stay UNREAPED.
            zombie = subprocess.Popen([sys.executable, "-c", "pass"], start_new_session=True)
            try:
                for _ in range(400):
                    if process_state(zombie.pid) == "Z":
                        break
                    time.sleep(0.02)
                self.assertEqual(process_state(zombie.pid), "Z", "un zombie NON recolte, encore dans le groupe")

                outcome = session.terminate_worker_group(zombie, grace_s=0.2, kill_grace_s=0.2, proc_root=blind)

                self.assertNotEqual(outcome, "GROUP_STILL_PRESENT",
                                    "sans /proc, « le groupe est encore la » n'est pas etabli")
                self.assertNotEqual(outcome, "TERMINATED",
                                    "ni un arret cooperatif: rien ne l'a observe")
                self.assertEqual(outcome, "GROUP_UNKNOWN",
                                 "borne: la disparition du groupe n'est PAS prouvee, et le dire est le seul resultat honnete")
                self.assertIsNone(zombie.returncode,
                                  "recolter le leader libererait le pid — donc le groupe — sans preuve (finding B)")
                self.assertEqual(process_state(zombie.pid), "Z", "le leader est toujours la, non recolte")
            finally:
                cleanup_group(zombie)

            # 2. and the probe itself must be ABLE to say it does not know: a
            #    live group behind an unreadable /proc is not "surviving" either.
            proc = subprocess.Popen([sys.executable, "-c", SLEEPING_WORKER], start_new_session=True)
            try:
                self.assertFalse(session.process_group_survives(proc.pid, blind),
                                 "rien n'est prouve: la sonde ne doit pas affirmer que le groupe survit")
                self.assertEqual(session.process_group_liveness(proc.pid, blind), "UNKNOWN",
                                 "sans /proc l'etat du groupe n'est pas connaissable")
            finally:
                cleanup_group(proc)


class SupervisorGroupLifecycle(unittest.TestCase):
    """EXECUTED (v4, finding B) : le groupe d'un worker qui n'est plus vivant.

    Un leader qui sort seul laisse son groupe derriere lui: c'est ce groupe qui
    doit etre libere AVANT un retry, avant une supersession et avant une
    nouvelle generation — sinon le descendant continue d'ecrire pour une
    generation qui n'est plus la sienne.
    """

    def test_39_a_failed_worker_that_left_a_child_has_it_cleaned_before_the_retry(self):
        with tempfile.TemporaryDirectory() as raw:
            home = pathlib.Path(raw)
            pidfile = home / "child.pid"
            record = []

            def spawn(generation):
                record.append(generation)
                if len(record) == 1:
                    return subprocess.Popen([sys.executable, "-c", FAILING_ORPHANING_WORKER, str(pidfile)],
                                            start_new_session=True)
                return subprocess.Popen([sys.executable, "-c", SLEEPING_WORKER], start_new_session=True)

            supervisor = session.RegenerationSupervisor(
                spawn=spawn, current_optical=lambda: state(93), home=home, install=PAYLOAD)
            supervisor.request(93)
            child_pid = None
            try:
                child_pid = wait_pidfile(pidfile)
                for _ in range(900):
                    supervisor.tick()
                    if supervisor.executions == 2:
                        break
                    time.sleep(0.01)

                self.assertTrue(wait_dead(child_pid, timeout=5.0),
                                "le descendant du worker echoue doit etre nettoye AVANT le retry")
                self.assertEqual(record, [93, 93], "un seul retry, et pas avant le nettoyage")
                self.assertEqual(supervisor.executions, 2)
                self.assertEqual([(r[0], r[1]) for r in getattr(supervisor, "releases", [])],
                                 [(93, "KILLED")],
                                 "la liberation est enregistree comme telle, hors du compte des tentatives")
            finally:
                cleanup_group(supervisor.proc, child_pid)

    def test_40_a_superseded_success_still_has_its_group_cleaned(self):
        with tempfile.TemporaryDirectory() as raw:
            home = pathlib.Path(raw)
            pidfile = home / "child.pid"

            def spawn(generation):
                return subprocess.Popen([sys.executable, "-c", ORPHANING_WORKER, str(pidfile)],
                                        start_new_session=True)

            supervisor = session.RegenerationSupervisor(
                spawn=spawn, current_optical=lambda: state(94), home=home, install=PAYLOAD)
            supervisor.request(93)                     # la generation courante est deja 94
            child_pid = None
            try:
                child_pid = wait_pidfile(pidfile)
                events = drive(supervisor)

                self.assertEqual(events, ["SUPERSEDED"], "un rendu perime n'est pas publie")
                self.assertTrue(wait_dead(child_pid, timeout=5.0),
                                "une sortie reussie mais perimee laisse un groupe: il doit partir aussi")
                self.assertIsNone(supervisor.proc)
                self.assertFalse((home / ".local/state/openhtpc/disc-sheet-state.json").exists(),
                                 "une supersession n'est pas un echec: aucun repli ne doit etre publie")
            finally:
                cleanup_group(supervisor.proc, child_pid)

    def test_41_a_new_generation_releases_the_group_of_an_exited_worker_first(self):
        with tempfile.TemporaryDirectory() as raw:
            home = pathlib.Path(raw)
            pidfile = home / "child.pid"
            record = []

            def spawn(generation):
                record.append(generation)
                if len(record) == 1:
                    return subprocess.Popen([sys.executable, "-c", ORPHANING_WORKER, str(pidfile)],
                                            start_new_session=True)
                return subprocess.Popen([sys.executable, "-c", SLEEPING_WORKER], start_new_session=True)

            supervisor = session.RegenerationSupervisor(
                spawn=spawn, current_optical=lambda: state(93), home=home, install=PAYLOAD)
            supervisor.request(93)
            child_pid = None
            try:
                child_pid = wait_pidfile(pidfile)
                old_pid = supervisor.proc.pid
                for _ in range(400):                   # le worker sort seul; rien ne l'a encore vu
                    if process_state(old_pid) == "Z":
                        break
                    time.sleep(0.02)
                self.assertEqual(process_state(old_pid), "Z", "le leader est sorti, non recolte")
                self.assertFalse(wait_dead(child_pid, timeout=0.1), "le descendant vit encore")

                supervisor.request(94)

                self.assertTrue(wait_dead(child_pid, timeout=5.0),
                                "le groupe du worker sorti est libere AVANT que la nouvelle generation ne parte")
                self.assertEqual(record, [93, 94])
                self.assertNotEqual(supervisor.proc.pid, old_pid, "le nouveau worker n'herite de rien")
                self.assertEqual([(r[0], r[2]) for r in getattr(supervisor, "releases", [])],
                                 [(93, "SUPERSEDED")],
                                 "une liberation, pas une terminaison: le leader etait deja sorti")
            finally:
                cleanup_group(supervisor.proc, child_pid)

    def test_44_a_retry_is_not_started_on_an_unproven_group_release(self):
        # Fail-closed, tightened by finding AGY-2 (v7).  Si la liberation ne peut
        # pas prouver que le groupe precedent est parti, aucun worker n'est
        # relance pour la meme generation, ET AUCUNE ECRITURE n'a lieu — meme
        # lorsque /proc ne voit plus qu'un zombie et qu'un helper « estime » le
        # groupe disparu.  L'attente historiquement erronee de v6 (un repli
        # publie pendant UNPROVEN) est remplacee : le dernier rendu valide est
        # CONSERVE, octet pour octet, plutot qu'ecrase par une provenance que la
        # liberation n'a jamais prouvee.
        with tempfile.TemporaryDirectory() as raw:
            home = pathlib.Path(raw)
            record = []
            worker = None
            optical = state(93)
            png, provenance_path = seed_current_render(home, optical)
            before = (hashlib.sha256(png.read_bytes()).hexdigest(),
                      hashlib.sha256(provenance_path.read_bytes()).hexdigest())

            def spawn(generation):
                record.append(generation)
                return subprocess.Popen([sys.executable, "-c", FAILING_WORKER], start_new_session=True)

            def unproven(target):
                return "GROUP_UNKNOWN"

            supervisor = session.RegenerationSupervisor(
                spawn=spawn, current_optical=lambda: optical, home=home, install=PAYLOAD,
                terminate=unproven)
            try:
                supervisor.request(93)
                worker = supervisor.group.proc
                first = drive(supervisor)
                self.assertEqual(first, ["FAILED_CLEANUP_UNPROVEN"],
                                 "aucun repli tant que la sortie du groupe n'est pas prouvee")
                self.assertEqual(record, [93], "et aucun retry ne demarre")
                self.assertEqual(supervisor.pending, {"generation": 93, "intent": "FAILED"},
                                 "la generation ET son intention sont retenues: rien n'est perdu")
                self.assertEqual(
                    (hashlib.sha256(png.read_bytes()).hexdigest(),
                     hashlib.sha256(provenance_path.read_bytes()).hexdigest()),
                    before, "aucune ecriture tant que la sortie du groupe n'est pas prouvee")

                events = drive_to_decision(supervisor)
                self.assertIn("CLEANUP_FAIL_CLOSED", events, "la reprise est bornee et observable")
                self.assertIn("CLEANUP_FAIL_CLOSED_NO_WRITE", events)
                self.assertNotIn("FAIL_CLOSED_FALLBACK", events)
                self.assertEqual(record, [93], "et toujours aucun retry")
                self.assertTrue(supervisor.fail_closed)
                # v7 (finding AGY-2): le groupe n'est TOUJOURS pas prouve libere,
                # donc AUCUNE ecriture.  Le rendu courant valide reste intact.
                self.assertEqual(
                    (hashlib.sha256(png.read_bytes()).hexdigest(),
                     hashlib.sha256(provenance_path.read_bytes()).hexdigest()),
                    before, "un rendu courant valide ne doit jamais etre ecrase sous UNPROVEN")
            finally:
                cleanup_group(worker)


class KillSpy:
    """Records every ``os.kill`` the cleanup helper makes, and performs it."""

    def __init__(self):
        self._real = os.kill
        self.calls = []

    def __call__(self, pid, sig):
        self.calls.append((int(pid), int(sig)))
        return self._real(pid, sig)


class ExactListingProcRoot:
    """A /proc view that lists EXACTLY the entries given, real reads per pid."""

    def __init__(self, entries):
        self._entries = [pathlib.Path(entry) for entry in entries]

    def iterdir(self):
        return list(self._entries)

    def __truediv__(self, name):
        return pathlib.Path("/proc") / name


def _unproven_terminate(value):
    def terminate(target):
        return value
    return terminate


class SupervisedGroupMustBeProven(unittest.TestCase):
    """EXECUTED (v5 finding A, hardened by v6) : un worker supervise DOIT etre chef
    de groupe.

    Une capture non prouvee ou un pgid different ne peut pas degrader en
    « un seul processus, nettoye » : c'est une propriete NON prouvee.  Les deux
    tests ci-dessous executent le VRAI terminateur (``terminate_worker_group``)
    sur de VRAIS chefs de session — v5 les remplacait par un lambda qui rendait
    « TERMINATED »/« KILLED », ce qui masquait le chemin fautif au lieu de le
    mesurer (finding F3 de la revue v6).
    """

    def test_45_a_worker_whose_group_was_not_captured_is_not_reported_cleaned(self):
        # PRODUCTION PATH (finding A, v6): the REAL supervisor, the REAL
        # ``terminate_worker_group``, a REAL session leader whose descendant
        # ignores SIGTERM — and a capture forced to fail.  v5 still ran the
        # single-process path here (it called the terminator first and rewrote its
        # answer afterwards), which polls, reaps and can signal the pid alone.  The
        # group is the only handle that reaches a descendant: without it, nothing
        # was cleaned, and the supervisor must say exactly that.
        with tempfile.TemporaryDirectory() as raw:
            pidfile = pathlib.Path(raw) / "child.pid"
            record = []
            clock = {"now": 0.0}
            worker = None
            child_pid = None

            def spawn(generation):
                record.append(generation)
                return subprocess.Popen([sys.executable, "-c", RESISTANT_DESCENDANT_WORKER, str(pidfile)],
                                        start_new_session=True)

            def bad_capture(proc, proc_root=None):
                return session.WorkerGroup(proc, proc.pid, None, None, None)   # pgid mismatch

            supervisor = session.RegenerationSupervisor(
                spawn=spawn, current_optical=lambda: state(93),
                capture=bad_capture, clock=lambda: clock["now"],
                # terminate is NOT injected: the production helper is what must
                # never be reached here.
            )
            try:
                supervisor.request(93)
                worker = supervisor.group.proc
                child_pid = wait_pidfile(pidfile)
                time.sleep(0.3)                        # le descendant installe SIG_IGN
                self.assertFalse(wait_dead(child_pid, timeout=0.1), "le descendant vit encore")

                self.assertIsNotNone(supervisor.group, "l'identite non prouvee est conservee")
                self.assertFalse(supervisor.group.owns_group)

                clock["now"] = session.REGENERATION_WORKER_BUDGET_S + 1     # the watchdog fires
                groups, pids = SignalSpy(), KillSpy()
                with mock.patch.object(os, "killpg", groups), mock.patch.object(os, "kill", pids):
                    events = supervisor.tick()

                self.assertEqual(events, ["STALLED_CLEANUP_UNPROVEN"])
                self.assertEqual(groups.calls, [], "aucun groupe n'a ete interroge: il n'y en a pas de prouve")
                self.assertEqual(pids.calls, [], "et surtout: pas de signal au pid seul (le repli 'un seul processus')")
                outcomes = [r[1] for r in supervisor.terminations]
                self.assertEqual(outcomes, [session.NO_GROUP_UNPROVEN],
                                 "un groupe non capture n'est pas rapporte nettoye")
                self.assertIsNone(worker.returncode, "le leader n'est NI poll, NI wait, NI recolte")
                self.assertEqual(record, [93], "aucun retry tant que la propriete n'est pas prouvee")
                self.assertEqual(supervisor.cleanup_state, session.CLEANUP_UNPROVEN)
            finally:
                cleanup_group(worker, child_pid)

    def test_46_a_capture_that_returned_nothing_still_fails_closed(self):
        # PRODUCTION PATH (finding A, v6): the same rule when the capture returns
        # NOTHING at all — the pid (pinned, unreaped) is still retained as the
        # identity, the real terminator is still never reached, and the bounded
        # recovery settles into the observable fail-closed state instead of
        # progressing silently.
        record = []
        worker = None

        def spawn(generation):
            record.append(generation)
            return subprocess.Popen([sys.executable, "-c", FAILING_WORKER], start_new_session=True)

        supervisor = session.RegenerationSupervisor(
            spawn=spawn, current_optical=lambda: state(93),
            capture=lambda proc, proc_root=None: None,
            # no ``terminate`` stub: the production helper, and it must not run.
        )
        try:
            supervisor.request(93)
            worker = supervisor.group.proc
            self.assertIsNotNone(supervisor.group, "le pid (epingle) reste l'identite retenue")
            self.assertFalse(supervisor.group.owns_group)

            events = drive_to_decision(supervisor)
            self.assertEqual(events[0], "FAILED_CLEANUP_UNPROVEN")
            self.assertFalse("FALLBACK" in events or "RETRY" in events,
                             "ni reprise ni repli tant que la propriete n'est pas etablie")
            self.assertEqual(record, [93])
            self.assertEqual(supervisor.cleanup_state, session.CLEANUP_UNPROVEN)
            for _ in range(10):
                supervisor.tick()
            self.assertTrue(supervisor.fail_closed, "reprise bornee: etat fail-closed observable")
            self.assertEqual(record, [93], "aucune progression silencieuse")
            self.assertIsNone(worker.returncode,
                              "rien n'a touche le leader: ni poll, ni wait, ni reap")
        finally:
            cleanup_group(worker)


class UnprovenReleaseRetainsOwnership(unittest.TestCase):
    """EXECUTED (v5, finding B) : la propriete est retenue jusqu'a preuve."""

    def test_47_an_unproven_release_keeps_the_group_and_blocks_the_retry(self):
        record = []
        worker = None

        def spawn(generation):
            record.append(generation)
            return subprocess.Popen([sys.executable, "-c", FAILING_WORKER], start_new_session=True)

        supervisor = session.RegenerationSupervisor(
            spawn=spawn, current_optical=lambda: state(93),
            terminate=_unproven_terminate("GROUP_UNKNOWN"),
        )
        try:
            supervisor.request(93)
            worker = supervisor.group.proc
            events = drive(supervisor)

            self.assertEqual(record, [93], "aucun retry sur une sortie non prouvee")
            self.assertNotIn("RETRY", events)
            self.assertIsNotNone(supervisor.group, "self.group est retenu")
            self.assertEqual(supervisor.cleanup_state, session.CLEANUP_UNPROVEN)
        finally:
            cleanup_group(worker)

    def test_48_a_success_with_an_unproven_release_is_never_published(self):
        worker = None
        with tempfile.TemporaryDirectory() as raw:
            home = pathlib.Path(raw)
            supervisor = session.RegenerationSupervisor(
                spawn=lambda generation: subprocess.Popen([sys.executable, "-c", "import sys; sys.exit(0)"],
                                                          start_new_session=True),
                current_optical=lambda: state(93), home=home, install=PAYLOAD,
                terminate=_unproven_terminate("GROUP_STILL_PRESENT"),
            )
            try:
                supervisor.request(93)
                worker = supervisor.group.proc
                events = drive(supervisor)

                self.assertEqual(events, ["SUCCESS_BLOCKED_CLEANUP_UNPROVEN"])
                self.assertIsNone(supervisor.take_publishable(), "aucune publication de succes")
                self.assertFalse((home / ".local/state/openhtpc/disc-sheet-state.json").exists())
                self.assertIsNotNone(supervisor.group)
                self.assertEqual(supervisor.cleanup_state, session.CLEANUP_UNPROVEN)
                self.assertEqual(supervisor.pending, {"generation": 93, "intent": session.PENDING_SUCCESS},
                                 "le succes bloque est RETENU: il n'est pas perdu (finding D)")
            finally:
                cleanup_group(worker)

    def test_49_every_unproven_outcome_keeps_ownership(self):
        for outcome in ("GROUP_STILL_PRESENT", "GROUP_UNKNOWN", "SIGNAL_ERROR", "UNREAPED",
                        "NO_GROUP", "NO_GROUP_UNPROVEN", "GROUP_NOT_OURS"):
            with self.subTest(outcome=outcome):
                record = []
                worker = None

                def spawn(generation):
                    record.append(generation)
                    return subprocess.Popen([sys.executable, "-c", FAILING_WORKER], start_new_session=True)

                supervisor = session.RegenerationSupervisor(
                    spawn=spawn, current_optical=lambda: state(93),
                    terminate=_unproven_terminate(outcome),
                )
                try:
                    supervisor.request(93)
                    worker = supervisor.group.proc
                    drive(supervisor)
                    self.assertEqual(record, [93])
                    self.assertIsNotNone(supervisor.group)
                    self.assertEqual(supervisor.cleanup_state, session.CLEANUP_UNPROVEN)
                finally:
                    cleanup_group(worker)

    def test_50_a_superseded_render_with_an_unproven_release_is_not_published(self):
        worker = None
        with tempfile.TemporaryDirectory() as raw:
            home = pathlib.Path(raw)
            supervisor = session.RegenerationSupervisor(
                spawn=lambda generation: subprocess.Popen([sys.executable, "-c", "import sys; sys.exit(0)"],
                                                          start_new_session=True),
                current_optical=lambda: state(94),        # the render of 93 is already stale
                home=home, install=PAYLOAD,
                terminate=_unproven_terminate("GROUP_UNKNOWN"),
            )
            try:
                supervisor.request(93)
                worker = supervisor.group.proc
                events = drive(supervisor)

                self.assertNotIn("SUPERSEDED", events, "pas de progression trompeuse")
                self.assertNotIn("EXITED_OK", events)
                self.assertIsNone(supervisor.take_publishable())
                self.assertIsNotNone(supervisor.group)
            finally:
                cleanup_group(worker)


class BoundedCleanupRecovery(unittest.TestCase):
    """EXECUTED (v5 finding B, extended by v6) : reprise bornee et deterministe."""

    def test_51_a_request_during_an_unproven_release_is_retained_without_loss(self):
        record = []
        worker = None

        def spawn(generation):
            record.append(generation)
            return subprocess.Popen([sys.executable, "-c", FAILING_WORKER], start_new_session=True)

        supervisor = session.RegenerationSupervisor(
            spawn=spawn, current_optical=lambda: state(93),
            terminate=_unproven_terminate("GROUP_UNKNOWN"),
        )
        try:
            supervisor.request(93)
            worker = supervisor.group.proc
            drive(supervisor)
            self.assertEqual(supervisor.cleanup_state, session.CLEANUP_UNPROVEN)

            supervisor.request(94)
            supervisor.request(95)
            self.assertEqual(record, [93], "aucune nouvelle generation ne demarre tant que non prouve")
            self.assertEqual(supervisor.pending_request, 95, "la generation en attente est conservee")
            self.assertEqual(supervisor.pending, {"generation": 95, "intent": session.PENDING_REQUEST})
        finally:
            cleanup_group(worker)

    def test_52_an_unproven_release_that_is_later_proven_resumes_exactly_once(self):
        record = []
        calls = []
        workers = []

        def spawn(generation):
            record.append(generation)
            code = FAILING_WORKER if generation == 93 else SLEEPING_WORKER
            workers.append(subprocess.Popen([sys.executable, "-c", code], start_new_session=True))
            return workers[-1]

        def terminate(target):
            calls.append(1)
            return "GROUP_UNKNOWN" if len(calls) == 1 else "KILLED"

        supervisor = session.RegenerationSupervisor(
            spawn=spawn, current_optical=lambda: state(93), terminate=terminate)
        try:
            supervisor.request(93)
            drive(supervisor)
            self.assertEqual(supervisor.cleanup_state, session.CLEANUP_UNPROVEN)
            self.assertEqual(supervisor.take_publishable(), None)

            supervisor.request(94)
            self.assertEqual(record, [93], "la generation 94 attend une sortie prouvee")

            events = supervisor.tick()                      # relachement prouve -> reprise
            self.assertIn("CLEANUP_PROVEN", events)
            self.assertIn("PENDING_GENERATION_STARTED", events)
            self.assertEqual(record, [93, 94], "la progression a lieu exactement une fois")
            self.assertEqual(supervisor.cleanup_state, session.CLEANUP_PROVEN)
            supervisor.tick()
            supervisor.tick()
            self.assertEqual(record, [93, 94], "et une seule fois")
        finally:
            cleanup_group(supervisor.proc, *workers)


class PartialProcSemantics(unittest.TestCase):
    """EXECUTED (v5, finding C) : un scan incomplet n'est pas un groupe vide."""

    def test_53_a_partially_unreadable_scan_is_unknown_never_gone(self):
        with tempfile.TemporaryDirectory() as raw:
            bad = pathlib.Path(raw) / "424242"
            bad.mkdir()
            (bad / "stat").mkdir()                      # a directory: unreadable as a stat file
            parent = subprocess.Popen([sys.executable, "-c", SLEEPING_WORKER], start_new_session=True)
            try:
                view = ExactListingProcRoot([pathlib.Path(f"/proc/{parent.pid}"), bad])
                self.assertEqual(session.process_group_liveness(parent.pid, view), "UNKNOWN",
                                 "un scan incomplet ne peut pas affirmer GONE")
                self.assertFalse(session.process_group_survives(parent.pid, view),
                                 "rien n'est prouve: la sonde stricte dit False, l'etat est UNKNOWN")
            finally:
                cleanup_group(parent)

    def test_54_a_vanished_entry_is_a_race_and_does_not_force_unknown(self):
        with tempfile.TemporaryDirectory() as raw:
            vanished = pathlib.Path(raw) / "424243"      # jamais cree: liste puis disparu
            parent = subprocess.Popen([sys.executable, "-c", SLEEPING_WORKER], start_new_session=True)
            try:
                view = ExactListingProcRoot([pathlib.Path(f"/proc/{parent.pid}"), vanished])
                # l'entree disparue est ignoree (course normale): le membre vivant est trouve
                self.assertEqual(session.process_group_liveness(parent.pid, view), "LIVE")
                # et un groupe que le noyau dit parti reste GONE — aucun faux blocker
                self.assertEqual(session.process_group_liveness(2 ** 22 + 7, view), "GONE")
            finally:
                cleanup_group(parent)


class NonReapingLeaderObservation(unittest.TestCase):
    """EXECUTED (v5, finding D) : aucune observation ne reape avant release."""

    def test_55_an_unreadable_proc_never_reaps_an_exited_leader_before_release(self):
        worker = None
        with tempfile.TemporaryDirectory() as raw:
            blind = pathlib.Path(raw) / "not-a-directory"     # iterdir()/stat ne repondent pas
            blind.write_text("pas de /proc ici")
            try:
                worker = subprocess.Popen([sys.executable, "-c", SLEEPING_WORKER], start_new_session=True)
                supervisor = session.RegenerationSupervisor(
                    spawn=lambda generation: worker, current_optical=lambda: state(93), proc_root=blind)
                supervisor.request(93)

                # the leader EXITS on its own and is left UNREAPED (a zombie): this
                # is the instant at which a ``proc.poll()`` fallback would REAP it
                # and destroy the ownership before the release.
                os.kill(worker.pid, signal.SIGKILL)
                for _ in range(400):
                    if process_state(worker.pid) == "Z":
                        break
                    time.sleep(0.02)
                self.assertEqual(process_state(worker.pid), "Z", "le leader est un zombie NON recolte")

                waitids = []
                real_waitid = os.waitid

                def spy_waitid(idtype, ident, options):
                    waitids.append(options)
                    return real_waitid(idtype, ident, options)

                with mock.patch.object(os, "waitid", spy_waitid):
                    running = supervisor._leader_running(worker)

                self.assertFalse(running, "le leader est sorti")
                self.assertIsNone(worker.returncode,
                                  "l'observation non-reaping ne doit PAS recolter le leader (findings B/D)")
                self.assertTrue(waitids, "l'observation non-reaping a bien servi")
                self.assertTrue(all(flags & os.WNOWAIT for flags in waitids),
                                "l'observation doit utiliser WNOWAIT (non-reaping)")
            finally:
                cleanup_group(worker)


class ControllerAuthority(unittest.TestCase):
    """EXECUTED/STRUCTURAL (v5, finding E) : HOME n'est plus une autorite."""

    def test_56_the_controller_never_polls_the_supervisors_worker(self):
        source = CONTROLLER.read_text(encoding="utf-8")
        self.assertNotIn("supervisor.proc.poll", source)
        self.assertNotIn("supervisor.proc.returncode", source)
        self.assertNotIn("supervisor.proc.wait", source)
        self.assertIn("supervisor.take_publishable()", source)

    def test_57_an_exit_between_tick_and_the_loop_is_caught_by_the_next_tick(self):
        with tempfile.TemporaryDirectory() as raw:
            pidfile = pathlib.Path(raw) / "child.pid"
            parent = subprocess.Popen([sys.executable, "-c", ORPHANING_WORKER, str(pidfile)],
                                      start_new_session=True)
            child_pid = None
            supervisor = session.RegenerationSupervisor(
                spawn=lambda generation: parent, current_optical=lambda: state(93))
            try:
                supervisor.request(93)
                child_pid = wait_pidfile(pidfile)
                self.assertEqual(supervisor.tick(), [], "le leader est encore vivant: rien a decider")
                for _ in range(600):                       # le leader sort SEUL (HOME ne l'a pas poll)
                    if process_state(parent.pid) == "Z":
                        break
                    time.sleep(0.02)
                self.assertEqual(process_state(parent.pid), "Z")
                self.assertFalse(wait_dead(child_pid, timeout=0.1), "le descendant vit encore")

                events = supervisor.tick()                 # le tick SUIVANT garde l'ownership

                self.assertEqual(events, ["EXITED_OK"])
                self.assertTrue(wait_dead(child_pid, timeout=5.0),
                                "le descendant du worker sorti doit etre nettoye par le tick suivant")
                self.assertIsNone(supervisor.proc)
                self.assertEqual(supervisor.take_publishable(), (93, True))
            finally:
                cleanup_group(parent, child_pid)


class ReapedIdentitySafety(unittest.TestCase):
    """EXECUTED (v5, findings B/F) : un pid recycle n'est jamais signale."""

    def test_58_a_precaptured_group_whose_leader_was_reaped_is_never_signalled_blindly(self):
        with tempfile.TemporaryDirectory() as raw:
            pidfile = pathlib.Path(raw) / "child.pid"
            parent = subprocess.Popen([sys.executable, "-c", ORPHANING_WORKER, str(pidfile)],
                                      start_new_session=True)
            child_pid = None
            try:
                child_pid = wait_pidfile(pidfile)
                group = session.capture_worker_group(parent)     # capture BEFORE the reap
                self.assertTrue(group.owns_group)
                parent.wait(timeout=15)                          # the caller reaps the leader
                self.assertIsNotNone(parent.returncode)

                signals, pgids = SignalSpy(), PgidSpy()
                with mock.patch.object(os, "killpg", signals), mock.patch.object(os, "getpgid", pgids):
                    outcome = session.terminate_worker_group(group)

                self.assertNotEqual(outcome, "TERMINATED")
                self.assertEqual(signals.signals, [],
                                 "aucun signal ne doit partir d'un numero que le noyau a pu rendre")
                self.assertNotIn(parent.pid, pgids.pids,
                                 "un pgid ne doit jamais etre resolu depuis le pid recolte")
            finally:
                cleanup_group(parent, child_pid)

    def test_59_a_recycled_pid_is_never_signalled_by_the_cleanup_helper(self):
        live = subprocess.Popen([sys.executable, "-c", SLEEPING_WORKER], start_new_session=True)
        try:
            # pretend the recorded incarnation was a DIFFERENT one: the pid was reused
            IDENTITY[live.pid] = session.worker_starttime(live.pid) - 1
            spy = KillSpy()
            with mock.patch.object(os, "kill", spy):
                killed = kill_identity_safe(live.pid)
            self.assertFalse(killed)
            self.assertEqual(spy.calls, [], "un pid recycle ne doit JAMAIS etre signale")
            self.assertIsNone(live.poll(), "le processus courant survit")
        finally:
            IDENTITY.pop(live.pid, None)
            cleanup_group(live)



class OwnershipIsStrict(unittest.TestCase):
    """EXECUTED (v6, finding A) : ``owns_group`` n'est vrai que pour un groupe PROUVE."""

    def test_60_owns_group_is_only_true_for_a_proven_group(self):
        pid = 4242
        controller_session = 4241
        cases = (
            ("pgid absent", session.WorkerGroup(None, pid, None, None, controller_session), False),
            ("pgid nul", session.WorkerGroup(None, pid, 0, None, controller_session), False),
            ("pgid negatif", session.WorkerGroup(None, pid, -pid, None, controller_session), False),
            ("pgid != pid: pas chef de son groupe",
             session.WorkerGroup(None, pid, pid + 1, None, controller_session), False),
            ("pgid == session du controleur: le groupe est le notre",
             session.WorkerGroup(None, pid, controller_session, None, controller_session), False),
            ("pgid == pid, hors session du controleur",
             session.WorkerGroup(None, pid, pid, 12345, controller_session), True),
        )
        for label, group, expected in cases:
            with self.subTest(case=label):
                self.assertEqual(group.owns_group, expected)


class EmptyScanIsNotGone(unittest.TestCase):
    """EXECUTED (v6, finding C) : un scan VIDE n'est pas un groupe disparu."""

    def test_61_an_empty_scan_alongside_a_live_group_is_unknown_never_gone(self):
        # /proc is asked about a group the KERNEL knows is alive, and it lists
        # nothing: this is exactly what a partial view returns (hidepid, another
        # mount namespace, a scan that raced).  v5 answered GONE — it declared the
        # group dead on the strength of its own blind spot.
        parent = subprocess.Popen([sys.executable, "-c", SLEEPING_WORKER], start_new_session=True)
        try:
            view = ExactListingProcRoot([])
            self.assertEqual(session.process_group_liveness(parent.pid, view), "UNKNOWN",
                             "killpg(0) repond et /proc ne liste rien: l'etat n'est pas connaissable")
            self.assertFalse(session.process_group_survives(parent.pid, view),
                             "et rien n'est prouve dans l'autre sens non plus")
        finally:
            cleanup_group(parent)

        # ... and the same helper, on the REAL /proc, still says GONE for a pgid
        # the kernel refuses with ESRCH: the second probe decides, not the scan.
        self.assertEqual(session.process_group_liveness(2 ** 22 + 9), "GONE")


class UnprovenGroupKeepsItsIdentity(unittest.TestCase):
    """EXECUTED (v6, finding B) : un groupe non prouve garde son identite et est
    nettoye plus tard, sans jamais recolter le leader pour « fabriquer » la preuve."""

    def test_62_an_unreadable_proc_leaves_the_leader_unreaped_and_the_same_group_is_cleaned_later(self):
        with tempfile.TemporaryDirectory() as raw:
            blind = pathlib.Path(raw) / "not-a-directory"
            blind.write_text("pas de /proc ici")
            view = {"root": blind}                 # /proc answers, then answers again
            clock = {"now": 0.0}
            created = []

            def spawn(generation):
                created.append(subprocess.Popen([sys.executable, "-c", SLEEPING_WORKER],
                                                start_new_session=True))
                return created[-1]

            def terminate(target):
                return session.terminate_worker_group(target, grace_s=0.2, kill_grace_s=0.2,
                                                      proc_root=view["root"])

            supervisor = session.RegenerationSupervisor(
                spawn=spawn, current_optical=lambda: state(93),
                terminate=terminate, clock=lambda: clock["now"])
            try:
                supervisor.request(93)
                self.assertTrue(supervisor.group.owns_group, "premisse: le groupe est bien capture")
                leader = supervisor.group.proc

                clock["now"] = session.REGENERATION_WORKER_BUDGET_S + 1
                self.assertEqual(supervisor.tick(), ["STALLED_CLEANUP_UNPROVEN"],
                                 "sans /proc, la disparition du groupe n'est pas prouvee")
                self.assertEqual(supervisor.cleanup_state, session.CLEANUP_UNPROVEN)
                self.assertIsNone(leader.returncode,
                                  "le leader reste NON recolte: son pid est ce qui epingle le groupe")
                self.assertEqual(len(created), 1, "aucun nouveau worker tant que rien n'est prouve")

                # /proc answers again: the SAME retained group can now be judged,
                # and the identity that was kept is what makes that possible.
                view["root"] = pathlib.Path("/proc")
                events = supervisor.tick()

                self.assertIn("CLEANUP_PROVEN", events)
                self.assertIn("RETRY", events, "le stall retenu reprend, EXACTEMENT une fois")
                self.assertEqual(supervisor.cleanup_state, session.CLEANUP_PROVEN)
                self.assertNotEqual(supervisor.group.pgid, leader.pid,
                                    "l'ancien groupe est libere; le nouveau worker a le sien")
                self.assertEqual(supervisor.group.pgid, created[1].pid)
                self.assertIsNotNone(leader.returncode,
                                     "le leader est recolte APRES la preuve — et pas avant")
                self.assertEqual(len(created), 2, "aucune double execution")
                self.assertEqual(supervisor.executions, 2)
            finally:
                cleanup_group(supervisor.proc, *created)


class BlockedSuccessIsNeverLost(unittest.TestCase):
    """EXECUTED (v6, finding D) : un succes bloque par une sortie non prouvee est
    RETENU, puis repris exactement une fois — v5 le perdait (pending_request absent)."""

    def test_63_a_success_blocked_by_an_unproven_release_is_resumed_exactly_once(self):
        record = []
        outcomes = ["GROUP_UNKNOWN", "ALREADY_EXITED"]
        created = []

        def spawn(generation):
            record.append(generation)
            created.append(subprocess.Popen([sys.executable, "-c", "import sys; sys.exit(0)"],
                                            start_new_session=True))
            return created[-1]

        def terminate(target):
            return outcomes.pop(0) if outcomes else "ALREADY_EXITED"

        supervisor = session.RegenerationSupervisor(
            spawn=spawn, current_optical=lambda: state(93), terminate=terminate)
        try:
            supervisor.request(93)
            first = None
            for _ in range(600):
                got = supervisor.tick()
                if got:
                    first = got
                    break
                time.sleep(0.01)
            self.assertEqual(first, ["SUCCESS_BLOCKED_CLEANUP_UNPROVEN"])
            self.assertIsNone(supervisor.take_publishable(), "aucun succes publie sur une sortie non prouvee")
            self.assertEqual(supervisor.pending, {"generation": 93, "intent": session.PENDING_SUCCESS},
                             "le rendu reussi est RETENU: c'est ce que v5 perdait")

            events = supervisor.tick()
            self.assertEqual(events, ["CLEANUP_PROVEN", "PENDING_SUCCESS_RESUMED"])
            self.assertEqual(supervisor.take_publishable(), (93, True),
                             "le rendu est rendu au controleur, EXACTEMENT une fois")
            self.assertIsNone(supervisor.take_publishable(), "et une seule fois")
            self.assertIsNone(supervisor.pending)
            for _ in range(5):
                supervisor.tick()
            self.assertIsNone(supervisor.take_publishable(), "aucune seconde reprise")
            self.assertEqual(record, [93], "aucun nouveau worker: c'est la MEME generation")
        finally:
            cleanup_group(supervisor.proc, *created)


class FailClosedNeverWritesOverAWriter(unittest.TestCase):
    """EXECUTED (v6, finding D) : a l'epuisement borne, aucune ecriture tant qu'un
    ecrivain potentiel n'est pas exclu."""

    def test_64_an_exhausted_recovery_writes_nothing_while_a_writer_is_not_excluded(self):
        with tempfile.TemporaryDirectory() as raw:
            home = pathlib.Path(raw)
            pidfile = home / "child.pid"
            record = []
            clock = {"now": 0.0}
            worker = None
            child_pid = None

            def spawn(generation):
                record.append(generation)
                return subprocess.Popen([sys.executable, "-c", RESISTANT_DESCENDANT_WORKER, str(pidfile)],
                                        start_new_session=True)

            supervisor = session.RegenerationSupervisor(
                spawn=spawn, current_optical=lambda: state(93), home=home, install=PAYLOAD,
                terminate=lambda target: "GROUP_STILL_PRESENT",   # un ecrivain est PROUVE encore la
                clock=lambda: clock["now"])
            try:
                supervisor.request(93)
                worker = supervisor.group.proc
                child_pid = wait_pidfile(pidfile)
                time.sleep(0.3)                        # le descendant installe SIG_IGN
                self.assertFalse(wait_dead(child_pid, timeout=0.1), "un descendant vit encore")

                clock["now"] = session.REGENERATION_WORKER_BUDGET_S + 1
                events = drive_to_decision(supervisor)

                self.assertEqual(events[0], "STALLED_CLEANUP_UNPROVEN")
                self.assertIn("CLEANUP_FAIL_CLOSED", events, "la decision est bornee et observable")
                self.assertIn("CLEANUP_FAIL_CLOSED_NO_WRITE", events)
                self.assertNotIn("FAIL_CLOSED_FALLBACK", events)
                self.assertEqual(record, [93], "le groupe etant encore vivant, aucun retry ne part")
                self.assertTrue(supervisor.fail_closed)
                self.assertFalse((home / ".local/state/openhtpc/disc-sheet-state.json").exists(),
                                 "aucune ecriture tant qu'un descendant peut ecrire les memes fichiers")
                self.assertFalse(wait_dead(child_pid, timeout=0.1),
                                 "et ce descendant est bien vivant: l'ecriture aurait ete une course")
            finally:
                cleanup_group(worker, child_pid)


class StalePublicationNeverCrosses(unittest.TestCase):
    """EXECUTED (v6, finding D4) : une publication perimee ne traverse pas une
    nouvelle generation."""

    def test_65_a_stale_publication_never_crosses_into_a_new_generation(self):
        record = []
        created = []

        def spawn(generation):
            record.append(generation)
            created.append(subprocess.Popen([sys.executable, "-c", "import sys; sys.exit(0)"],
                                            start_new_session=True))
            return created[-1]

        supervisor = session.RegenerationSupervisor(spawn=spawn, current_optical=lambda: state(93))
        try:
            supervisor.request(93)
            events = drive(supervisor)
            self.assertEqual(events, ["EXITED_OK"])
            self.assertEqual(supervisor.publish_pending, (93, True), "le rendu attend le controleur")

            supervisor.request(94)                 # une nouvelle generation, AVANT la prise

            self.assertIsNone(supervisor.publish_pending,
                              "une publication perimee ne doit pas traverser une nouvelle generation")
            self.assertIsNone(supervisor.take_publishable())
            self.assertEqual(record, [93, 94], "et la nouvelle generation demarre normalement")
        finally:
            cleanup_group(supervisor.proc, *created)


class HomeShutdownDrain(unittest.TestCase):
    """EXECUTED (v6, finding E) : la sortie du controleur n'abandonne rien.

    Le controleur HOME ne peut pas etre importe hermétiquement (l'import rend le
    menu et lance Flex), donc la DECISION qu'il prend a la sortie est ici executee
    sur le vrai superviseur, et son cablage (quelle sortie passe par quelle
    decision) est verifie sur sa source, comme les autres contrats STRUCTURAL.
    """

    def test_66_shutdown_releases_a_live_group_whose_descendant_ignores_sigterm(self):
        with tempfile.TemporaryDirectory() as raw:
            pidfile = pathlib.Path(raw) / "child.pid"
            worker = None
            child_pid = None
            supervisor = None
            try:
                worker = subprocess.Popen([sys.executable, "-c", RESISTANT_DESCENDANT_WORKER, str(pidfile)],
                                          start_new_session=True)
                supervisor = session.RegenerationSupervisor(
                    spawn=lambda generation: worker, current_optical=lambda: state(93))
                supervisor.request(93)
                child_pid = wait_pidfile(pidfile)
                time.sleep(0.3)                        # SIG_IGN installe

                may_exit, outcome, events = supervisor.shutdown()

                self.assertTrue(may_exit, "le groupe est prouve libere: la sortie est sure")
                self.assertEqual(events, ["SHUTDOWN_RELEASED"])
                self.assertIn(outcome, {"TERMINATED", "KILLED"})
                self.assertIsNone(supervisor.group)
                self.assertEqual(supervisor.cleanup_state, session.CLEANUP_PROVEN)
                self.assertTrue(wait_dead(worker.pid), "le worker ne survit pas a la sortie")
                self.assertTrue(wait_dead(child_pid), "ni son descendant SIGTERM-ignorant")
                self.assertIsNotNone(worker.returncode, "le leader est recolte APRES la preuve")
            finally:
                cleanup_group(worker, child_pid)

    def test_67_a_shutdown_that_cannot_prove_the_release_fails_closed(self):
        with tempfile.TemporaryDirectory() as raw:
            blind = pathlib.Path(raw) / "not-a-directory"
            blind.write_text("pas de /proc ici")
            worker = None
            supervisor = None
            try:
                worker = subprocess.Popen([sys.executable, "-c", SLEEPING_WORKER], start_new_session=True)
                supervisor = session.RegenerationSupervisor(
                    spawn=lambda generation: worker, current_optical=lambda: state(93),
                    terminate=lambda target: session.terminate_worker_group(
                        target, grace_s=0.2, kill_grace_s=0.2, proc_root=blind))
                supervisor.request(93)
                worker = supervisor.group.proc

                groups, pids = SignalSpy(), KillSpy()
                with mock.patch.object(os, "killpg", groups), mock.patch.object(os, "kill", pids):
                    may_exit, outcome, events = supervisor.shutdown(attempts=1)

                self.assertFalse(may_exit,
                                 "sans preuve, le controleur ne doit NI remplacer NI terminer 'normalement'")
                self.assertEqual(events, ["SHUTDOWN_CLEANUP_UNPROVEN"])
                self.assertEqual(outcome, "GROUP_UNKNOWN")
                self.assertTrue(supervisor.fail_closed, "l'etat fail-closed est observable")
                self.assertIsNotNone(supervisor.group, "l'identite retenue reste journalisable")
                self.assertIsNone(worker.returncode,
                                  "le leader reste NON recolte: aucune preuve n'a ete fabriquee")
                self.assertEqual(pids.calls, [], "aucun signal au pid seul")
                self.assertTrue(groups.signals, "le GROUPE, lui, a bien ete adresse")
                self.assertTrue(all(pgid == worker.pid for pgid, _sig in groups.signals),
                                "et toujours par son identite capturee, jamais par un pid resolu")
            finally:
                cleanup_group(worker)

    def test_68_the_whole_post_supervisor_life_sits_inside_one_boundary(self):
        """STRUCTURAL, by SCOPE (v8, finding Codex v7-3).

        v7's version searched strings, so it accepted a boundary drawn around the
        LOOP alone — the scope Codex rejected: every statement AFTER the loop
        (the crash-loop lookup, the recovery/exit decision, the ``execv``, the
        ``SystemExit``) sat outside it and escaped with no drain at all.  This one
        parses the controller and proves the SCOPE: ``controller_loop``'s body
        ends with exactly ONE ``try``, that ``try`` holds the loop, the post-loop
        decision, the departure AND every exit primitive, and its handlers are
        the planned departure (which does NOT re-enter the gate) and the total
        ``BaseException`` boundary (which does).  A wrong scope now fails here.

        The behavioural half is executed for real by tests 77-80, on the payload
        controller started by the payload launcher.
        """
        source = CONTROLLER.read_text(encoding="utf-8")
        self.assertTrue(hasattr(session, "guarded_release"))
        self.assertIn("def drain_supervisor_for_exit", source)
        self.assertIn("supervisor.shutdown()", source)
        self.assertIn("def controller_loop(", source)

        tree = ast.parse(source)
        loops = [node for node in tree.body
                 if isinstance(node, ast.FunctionDef) and node.name == "controller_loop"]
        self.assertEqual(len(loops), 1, "un seul controleur, une seule frontiere")
        function = loops[0]
        boundary = function.body[-1]
        # (1) the LAST statement of the controller is the boundary itself: no
        #     statement — and therefore no exit — can follow it.
        self.assertIsInstance(boundary, ast.Try,
                              "la vie post-superviseur doit se terminer par UN try")
        self.assertEqual([ast.unparse(handler.type) for handler in boundary.handlers],
                         ["PlannedDeparture", "BaseException"],
                         "la sortie planifiee puis la frontiere totale")
        # (2) the loop AND the post-loop decision are both in the try body
        kinds = [type(node).__name__ for node in boundary.body]
        self.assertIn("While", kinds, "la boucle principale est dans la frontiere")
        self.assertEqual(kinds[-1], "Raise")
        self.assertEqual(ast.unparse(boundary.body[-1]), "raise PlannedDeparture()",
                         "la sortie PLANIFIEE est le dernier mot de la frontiere")
        # ... and it is raised only AFTER a call to the gate: the gate statement
        # is the one right above it, in the same block.  Nothing can reach the
        # departure without having gone through the gate first.
        self.assertIn("engine.guarded_release", ast.unparse(boundary.body[-2]))
        # (3) every exit primitive of the controller is lexically INSIDE it —
        #     the only one allowed outside the try body is the SystemExit the
        #     PLANNED-departure handler itself raises.
        inside = {id(node) for statement in boundary.body for node in ast.walk(statement)}
        planned_handler = {id(node) for node in ast.walk(boundary.handlers[0])}
        exits = []
        for node in ast.walk(function):
            if isinstance(node, ast.Call) and ast.unparse(node.func) == "os.execv":
                exits.append(node)
            elif isinstance(node, ast.Raise) and node.exc is not None \
                    and "SystemExit" in ast.unparse(node.exc):
                exits.append(node)
        self.assertTrue(exits, "l'execv FLEX_RECOVERY et le SystemExit existent toujours")
        for node in exits:
            self.assertIn(id(node), inside | planned_handler,
                          f"sortie hors frontiere ligne {node.lineno}: {ast.unparse(node)[:70]}")
        self.assertEqual(len([node for node in exits if id(node) in inside]), 1,
                         "seul l'execv est une sortie en dur dans la frontiere")
        self.assertEqual(len([node for node in exits if id(node) in planned_handler]), 1,
                         "et le SystemExit de la sortie planifiee est le seul hors du corps")
        # (4) the crash-loop lookup and the recovery decision are in there too
        decision = ast.unparse(boundary.body[-3])
        self.assertIn("crash_loop_state", decision)
        self.assertIn("reason='FLEX_RECOVERY'", decision)
        ordinary = ast.unparse(boundary.body[-2])
        self.assertIn('reason='"'"'STOP_SIGNAL'"'"' if stop_requested else '"'"'FLEX_EXIT'"'"'', ordinary)
        # (5) the exception gate is the SAME engine gate, and the recovery gate
        #     comes FIRST (before any replacement).
        gates = [ast.unparse(node) for node in ast.walk(boundary)
                 if isinstance(node, ast.Call) and ast.unparse(node.func) == "engine.guarded_release"]
        self.assertEqual(sum("reason='EXCEPTION'" in gate for gate in gates), 1,
                         "le handler total passe par la MEME porte")
        self.assertLess(decision.index("reason='FLEX_RECOVERY'"),
                        decision.index("os.execv(sys.executable"),
                        "aucun execv sans preuve de liberation")
        # (6) the planned-departure handler does NOT re-enter the gate: a clean
        #     exit stays a clean exit.
        planned = ast.unparse(boundary.handlers[0])
        self.assertIn("raise SystemExit(0 if stop_requested else proc.returncode or 0)", planned)
        self.assertNotIn("guarded_release", planned)
        # (7) production never caps the recovery: it does NOT abandon a retained group
        self.assertIn("recovery_pause_s=engine.GUARDED_RECOVERY_PAUSE_S", source)
        self.assertNotIn("max_recovery_rounds=", source,
                         "en production l'autorite ne renonce jamais")
        self.assertEqual(session.EXIT_CLEANUP_UNPROVEN, 75)
        self.assertNotEqual(session.EXIT_CLEANUP_UNPROVEN, 0)
        # (8) the dev11 order (render -> publish -> navigation) is untouched
        success = source.index("if successful and completed_generation")
        publish = source.index("pending_auto_open_generation, pending_eject_home_generation", success)
        detect = source.index("optical_navigation_event", publish)
        self.assertLess(success, publish)
        self.assertLess(publish, detect)


def blind_then_real_supervisor(pidfile, blind_calls=None):
    """A supervisor whose first release attempts answer ``GROUP_UNKNOWN``.

    Reproduces a /proc the controller cannot read yet (the case the guarded
    release exists for): the first ``blind_calls`` release attempts fail closed,
    then the REAL terminator runs against the SAME captured group — so a test can
    prove the retained identity still reaches the descendant.  ``spawned`` counts
    the workers started, so "no new worker during the quarantine" is measurable.
    """
    blind = session.SHUTDOWN_RELEASE_ATTEMPTS if blind_calls is None else int(blind_calls)
    calls = {"n": 0}
    spawned = []
    real = session.terminate_worker_group

    def terminate(target):
        calls["n"] += 1
        if calls["n"] <= blind:
            return "GROUP_UNKNOWN"
        return real(target, grace_s=0.3, kill_grace_s=0.3)

    def spawn(generation):
        worker = subprocess.Popen([sys.executable, "-c", RESISTANT_DESCENDANT_WORKER, str(pidfile)],
                                  start_new_session=True)
        spawned.append(worker)
        return worker

    supervisor = session.RegenerationSupervisor(
        spawn=spawn, current_optical=lambda: state(93), terminate=terminate)
    return supervisor, calls, spawned


class SameGenerationRequestAfterBlockedSuccess(unittest.TestCase):
    """EXECUTED (v7, blocker AGY-1) : une REQUEST de MEME generation arrivee
    APRES un SUCCES bloque (le rerender post-enrichissement TMDb) n'est jamais
    perdue.  v6 l'absorbait et publiait le rendu PRE-enrichissement."""

    def _supervisor(self, terminate):
        record, created = [], []

        def spawn(generation):
            record.append(generation)
            created.append(subprocess.Popen([sys.executable, "-c", "import sys; sys.exit(0)"],
                                            start_new_session=True))
            return created[-1]
        supervisor = session.RegenerationSupervisor(
            spawn=spawn, current_optical=lambda: state(93), terminate=terminate)
        return supervisor, record, created

    @staticmethod
    def _first_event(supervisor):
        for _ in range(600):
            got = supervisor.tick()
            if got:
                return got
            time.sleep(0.01)
        raise AssertionError("aucun evenement du superviseur")

    def test_69_a_same_generation_request_supersedes_a_blocked_success(self):
        outcomes = ["GROUP_UNKNOWN", "ALREADY_EXITED", "ALREADY_EXITED"]
        events_log = []
        supervisor, record, created = self._supervisor(
            lambda target: outcomes.pop(0) if outcomes else "ALREADY_EXITED")
        supervisor._log = lambda event, **fields: events_log.append((event, fields))
        try:
            supervisor.request(93)                      # rendu G pre-enrichissement
            self.assertEqual(self._first_event(supervisor), ["SUCCESS_BLOCKED_CLEANUP_UNPROVEN"])
            self.assertEqual(supervisor.pending, {"generation": 93, "intent": session.PENDING_SUCCESS})
            self.assertIsNone(supervisor.take_publishable(),
                              "le succes n'est pas publie sur une sortie non prouvee")

            # le rerender post-enrichissement du MEME G arrive AVANT la recovery
            supervisor.request(93)
            self.assertEqual(supervisor.pending, {"generation": 93, "intent": session.PENDING_REQUEST},
                             "une REQUEST de meme generation SUPERSEDE le succes bloque, jamais absorbee")
            self.assertIsNone(supervisor.publish_pending,
                              "aucune publication du rendu pre-enrichissement")
            self.assertIn("REGENERATION_PENDING_SUCCESS_SUPERSEDED_BY_REQUEST",
                          [event for event, _ in events_log],
                          "la supersession est journalisee: rien n'est perdu en silence")

            events = supervisor.tick()
            self.assertEqual(events, ["CLEANUP_PROVEN", "PENDING_GENERATION_STARTED"],
                             "la recovery PROVEN lance un rerender de G")
            self.assertEqual(record, [93, 93], "exactement un rerender post-enrichissement de G")
            self.assertIsNone(supervisor.pending, "rien ne reste en attente")

            self.assertEqual(drive(supervisor), ["EXITED_OK"])
            self.assertEqual(supervisor.take_publishable(), (93, True),
                             "le rerender enrichi est publie, EXACTEMENT une fois")
            self.assertIsNone(supervisor.take_publishable(), "et une seule fois")
        finally:
            cleanup_group(supervisor.proc, *created)

    def test_70_a_newer_generation_request_wins_over_a_blocked_success(self):
        outcomes = ["GROUP_UNKNOWN", "ALREADY_EXITED", "ALREADY_EXITED"]
        current = {"generation": 93}
        record, created = [], []

        def spawn(generation):
            record.append(generation)
            created.append(subprocess.Popen([sys.executable, "-c", "import sys; sys.exit(0)"],
                                            start_new_session=True))
            return created[-1]

        supervisor = session.RegenerationSupervisor(
            spawn=spawn, current_optical=lambda: state(current["generation"]),
            terminate=lambda target: outcomes.pop(0) if outcomes else "ALREADY_EXITED")
        try:
            supervisor.request(93)
            self.assertEqual(self._first_event(supervisor), ["SUCCESS_BLOCKED_CLEANUP_UNPROVEN"])
            self.assertEqual(supervisor.pending, {"generation": 93, "intent": session.PENDING_SUCCESS})

            current["generation"] = 94
            supervisor.request(94)                      # une generation PLUS RECENTE arrive
            self.assertEqual(supervisor.pending, {"generation": 94, "intent": session.PENDING_REQUEST},
                             "la generation plus recente reste prioritaire")
            self.assertIsNone(supervisor.publish_pending)

            events = supervisor.tick()
            self.assertEqual(events, ["CLEANUP_PROVEN", "PENDING_GENERATION_STARTED"])
            self.assertEqual(record, [93, 94])
            self.assertIsNone(supervisor.take_publishable(),
                              "le succes stale de 93 n'est jamais publie")
        finally:
            cleanup_group(supervisor.proc, *created)


class FailClosedUnprovenNeverWrites(unittest.TestCase):
    """EXECUTED (v7, blocker AGY-2) : tant que la liberation n'est pas PROUVEE,
    le chemin fail-closed n'ecrit AUCUN artefact de presentation — meme quand un
    helper estime le groupe disparu.  Un rendu courant valide reste intact."""

    def _exhaust(self, home, optical, terminate):
        record, worker = [], None

        def spawn(generation):
            record.append(generation)
            return subprocess.Popen([sys.executable, "-c", FAILING_WORKER], start_new_session=True)

        supervisor = session.RegenerationSupervisor(
            spawn=spawn, current_optical=lambda: optical, home=home, install=PAYLOAD,
            terminate=terminate)
        try:
            supervisor.request(93)
            worker = supervisor.group.proc
            events = drive_to_decision(supervisor)
        finally:
            cleanup_group(worker)
        return supervisor, record, events

    def test_71_an_exhausted_unproven_recovery_never_writes_even_when_the_group_looks_gone(self):
        with tempfile.TemporaryDirectory() as raw:
            home = pathlib.Path(raw)
            optical = state(93)
            png, provenance_path = seed_current_render(home, optical)
            before = (hashlib.sha256(png.read_bytes()).hexdigest(),
                      hashlib.sha256(provenance_path.read_bytes()).hexdigest())

            supervisor, record, events = self._exhaust(home, optical, lambda target: "GROUP_UNKNOWN")

            self.assertIn("FAILED_CLEANUP_UNPROVEN", events)
            self.assertIn("CLEANUP_FAIL_CLOSED", events)
            self.assertIn("CLEANUP_FAIL_CLOSED_NO_WRITE", events)
            self.assertNotIn("FAIL_CLOSED_FALLBACK", events)
            self.assertTrue(supervisor.fail_closed)
            self.assertEqual(record, [93], "aucun retry pendant UNPROVEN")
            self.assertEqual(
                (hashlib.sha256(png.read_bytes()).hexdigest(),
                 hashlib.sha256(provenance_path.read_bytes()).hexdigest()),
                before, "le rendu courant valide est conserve, octet pour octet")

    def test_72_group_not_ours_eperm_and_transient_unknown_write_nothing(self):
        for outcome in ("GROUP_NOT_OURS", "SIGNAL_ERROR", "GROUP_STILL_PRESENT",
                        "NO_GROUP_UNPROVEN", "GROUP_UNKNOWN", "UNREAPED"):
            with self.subTest(outcome=outcome), tempfile.TemporaryDirectory() as raw:
                home = pathlib.Path(raw)
                optical = state(93)
                png, provenance_path = seed_current_render(home, optical)
                before = (hashlib.sha256(png.read_bytes()).hexdigest(),
                          hashlib.sha256(provenance_path.read_bytes()).hexdigest())

                supervisor, record, events = self._exhaust(
                    home, optical, lambda target, outcome=outcome: outcome)

                self.assertIn("CLEANUP_FAIL_CLOSED_NO_WRITE", events, outcome)
                self.assertNotIn("FAIL_CLOSED_FALLBACK", events, outcome)
                self.assertEqual(
                    (hashlib.sha256(png.read_bytes()).hexdigest(),
                     hashlib.sha256(provenance_path.read_bytes()).hexdigest()),
                    before, outcome)


class HermeticHomeCase(unittest.TestCase):
    """A test that drives the PAYLOAD HOME through the PAYLOAD launcher.

    The fixture builds a real ``openhtpc-home.py`` controller, started by the
    real ``openhtpc-session-start`` (its ``exec 8>`` / ``flock -n 8`` protocol
    and its ``exec "$HOME_CONTROLLER"``), with a REAL regeneration worker whose
    process group is retained: a live worker, a live SIGTERM-ignoring descendant
    and a release the engine cannot PROVE.  Importing the controller is
    impossible (its import renders the menu and launches Flex), so the tests
    that need the real controller run it as the payload runs it.
    """

    #: the bounded drain is retried at the PRODUCTION cadence (5 s); six blind
    #: release attempts mean two full quarantine rounds before the proof, which
    #: is the window in which every "nothing leaves" assertion below is taken.
    BLIND_RELEASES = 6

    def _armed_home(self, home, faults=()):
        """Start the payload controller for real, with a retained real worker."""
        home.build(blind_releases=self.BLIND_RELEASES, resistant_worker=True)
        session = home.start()
        self.assertTrue(home.wait_event("FLEX_STARTED", timeout=60),
                        "le vrai lanceur n'a pas démarré le contrôleur HOME")
        flex_pid = home.wait_started_flex()
        # the worker stays LIVE inside its own group: the test holds the engine's
        # own publication lock, exactly like a concurrent publisher would.
        home.hold_publication_lock()
        home.set_optical(94)
        descendant = home.wait_descendant()
        for name in faults:
            home.fault(name)
        return session, flex_pid, descendant

    def _quarantine(self, home, message):
        """Wait for the gate to hold HOME alive, then report when it started."""
        self.assertTrue(home.wait_event("HOME_GUARDED_RECOVERY", timeout=45), message)
        return time.monotonic()


class HomeGuardedRelease(HermeticHomeCase):
    """EXECUTED (v7, blocker Codex-3) : la sortie du controleur HOME est GATED par
    ``engine.guarded_release``, qui NE QUITTE PAS tant que le groupe du worker
    n'est pas PROUVE libere.  Le processus reste vivant (identite memoire +
    ui-session.lock detenu), ne fait NI execv NI sortie, ne lance aucun worker et
    ne publie rien, et ne rejoue le drain borne qu'a un rythme espace.

    The caller's shape below is EXACTLY the controller's (openhtpc-home.py): the
    action on the "leave" path runs only if the gate returns True.  Test 68 pins
    the real controller to that same shape by parsing its scope, and test 77 runs
    the real thing — payload launcher, payload controller, real worker group."""

    def _armed(self, raw):
        pidfile = pathlib.Path(raw) / "child.pid"
        supervisor, calls, spawned = blind_then_real_supervisor(pidfile)
        return supervisor, calls, spawned, pidfile

    def _start(self, supervisor, pidfile):
        supervisor.request(93)
        worker = supervisor.group.proc
        child_pid = wait_pidfile(pidfile)
        time.sleep(0.3)                        # le descendant installe SIG_IGN
        return worker, child_pid

    def test_73_the_gate_keeps_the_controller_alive_until_the_group_is_proven_gone(self):
        with tempfile.TemporaryDirectory() as raw:
            supervisor, calls, spawned, pidfile = self._armed(raw)
            worker = child_pid = None
            events, sleeps, actions = [], [], []
            try:
                worker, child_pid = self._start(supervisor, pidfile)

                released = session.guarded_release(
                    supervisor, lambda reason: drain_via_shutdown(supervisor),
                    lambda event, **fields: events.append(event),
                    reason="FLEX_EXIT",
                    sleep=lambda seconds: sleeps.append(seconds), recovery_pause_s=0.01)
                if released:                       # the controller's "leave" path
                    events.append("CALLER_EXIT")
                    actions.append(1)

                self.assertTrue(released)
                self.assertEqual(actions, [1], "une seule sortie, et seulement apres la preuve")
                self.assertLess(events.index("HOME_AUTHORITY_RELEASE_PROVEN"),
                                events.index("CALLER_EXIT"), "aucune sortie avant la preuve")
                self.assertGreaterEqual(len(sleeps), 1, "quarantaine PACEE: jamais un spin CPU")
                self.assertEqual(calls["n"], session.SHUTDOWN_RELEASE_ATTEMPTS + 1,
                                 "un drain aveugle borne, puis la preuve")
                self.assertEqual(len(spawned), 1, "aucun nouveau worker pendant la quarantaine")
                self.assertIn("HOME_GUARDED_RECOVERY", events)
                self.assertLess(events.index("HOME_GUARDED_RECOVERY"),
                                events.index("HOME_AUTHORITY_RELEASE_PROVEN"))
                self.assertEqual(supervisor.cleanup_state, session.CLEANUP_PROVEN)
                self.assertTrue(wait_dead(worker.pid),
                                "le worker est nettoye depuis son identite retenue")
                self.assertTrue(wait_dead(child_pid),
                                "et son descendant SIGTERM-ignorant aussi")
            finally:
                cleanup_group(worker, child_pid, *spawned)

    def test_74_flex_recovery_execs_exactly_once_and_only_after_the_proof(self):
        with tempfile.TemporaryDirectory() as raw:
            supervisor, calls, spawned, pidfile = self._armed(raw)
            worker = child_pid = None
            events, sleeps, execvs = [], [], []
            try:
                worker, child_pid = self._start(supervisor, pidfile)

                released = session.guarded_release(
                    supervisor, lambda reason: drain_via_shutdown(supervisor),
                    lambda event, **fields: events.append(event),
                    reason="FLEX_RECOVERY",
                    sleep=lambda seconds: sleeps.append(seconds), recovery_pause_s=0.01)
                if released:
                    events.append("CALLER_EXECV")
                    execvs.append(1)

                self.assertTrue(released)
                self.assertEqual(execvs, [1], "exactement un execv — et APRES la preuve")
                self.assertLess(events.index("HOME_AUTHORITY_RELEASE_PROVEN"),
                                events.index("CALLER_EXECV"))
                self.assertNotIn("CALLER_EXECV",
                                 events[:events.index("HOME_AUTHORITY_RELEASE_PROVEN")],
                                 "aucun execv avant la preuve")
                self.assertEqual(supervisor.cleanup_state, session.CLEANUP_PROVEN)
                self.assertTrue(wait_dead(child_pid))
            finally:
                cleanup_group(worker, child_pid, *spawned)

    def test_75_an_exception_is_not_masked_and_never_abandons_the_group(self):
        with tempfile.TemporaryDirectory() as raw:
            supervisor, calls, spawned, pidfile = self._armed(raw)
            worker = child_pid = None
            events, sleeps, exits = [], [], []
            failure = RuntimeError("panne injectee dans la boucle")
            try:
                worker, child_pid = self._start(supervisor, pidfile)

                with self.assertRaises(RuntimeError) as caught:
                    released = session.guarded_release(
                        supervisor, lambda reason: drain_via_shutdown(supervisor),
                        lambda event, **fields: events.append(event),
                        reason="EXCEPTION", sleep=lambda seconds: sleeps.append(seconds),
                        recovery_pause_s=0.01, exception=failure)
                    if released:                   # unreachable: the boundary re-raises
                        exits.append(1)

                self.assertIs(caught.exception, failure, "l'exception n'est pas masquee")
                self.assertEqual(exits, [], "aucune sortie pendant la quarantaine")
                self.assertIn("HOME_GUARDED_RECOVERY", events)
                self.assertIn("HOME_AUTHORITY_RELEASE_PROVEN", events)
                self.assertIn("HOME_SESSION_EXCEPTION_RERAISED", events)
                self.assertLess(events.index("HOME_GUARDED_RECOVERY"),
                                events.index("HOME_SESSION_EXCEPTION_RERAISED"))
                self.assertLess(events.index("HOME_AUTHORITY_RELEASE_PROVEN"),
                                events.index("HOME_SESSION_EXCEPTION_RERAISED"),
                                "l'exception n'est relevee qu'apres la preuve")
                self.assertEqual(supervisor.cleanup_state, session.CLEANUP_PROVEN)
                self.assertTrue(wait_dead(worker.pid))
                self.assertTrue(wait_dead(child_pid))
            finally:
                cleanup_group(worker, child_pid, *spawned)

    def test_76_a_stop_signal_exits_only_after_the_proof(self):
        with tempfile.TemporaryDirectory() as raw:
            supervisor, calls, spawned, pidfile = self._armed(raw)
            worker = child_pid = None
            events, sleeps, exits, reasons = [], [], [], []
            try:
                worker, child_pid = self._start(supervisor, pidfile)

                def drain(reason):
                    reasons.append(reason)
                    return drain_via_shutdown(supervisor)

                released = session.guarded_release(
                    supervisor, drain, lambda event, **fields: events.append(event),
                    reason="STOP_SIGNAL", sleep=lambda seconds: sleeps.append(seconds),
                    recovery_pause_s=0.01)
                if released:
                    events.append("CALLER_EXIT")
                    exits.append(1)

                self.assertTrue(released)
                self.assertEqual(exits, [1])
                self.assertEqual(set(reasons), {"STOP_SIGNAL"},
                                 "la raison STOP_SIGNAL est portee jusqu'au drain")
                self.assertLess(events.index("HOME_AUTHORITY_RELEASE_PROVEN"),
                                events.index("CALLER_EXIT"))
                self.assertEqual(supervisor.cleanup_state, session.CLEANUP_PROVEN)
                self.assertTrue(wait_dead(child_pid))
            finally:
                cleanup_group(worker, child_pid, *spawned)

    def test_77_the_real_session_lock_stays_held_through_quarantine(self):
        """EXECUTED (v8, finding Codex v7-4): the REAL session-start protocol.

        Codex rejected v7's ``HOME_LOCK_DRIVER``: a synthetic process flocking a
        file proves nothing about the payload's session protocol, and a synthetic
        supervisor proves nothing about a retained worker.  Here the PAYLOAD
        launcher runs its real protocol — ``exec 8>`` + ``flock -n 8`` + its
        exports + ``exec "$HOME_CONTROLLER"`` — around the PAYLOAD controller,
        while the gate quarantines HOME with a REAL worker group retained: a live
        worker, a live SIGTERM-ignoring descendant, and a release the engine
        cannot prove.  A SECOND real ``openhtpc-session-start`` must be refused
        for as long as the first HOME lives; once that HOME has proven the
        release and left, a THIRD one acquires and runs.
        """
        with tempfile.TemporaryDirectory() as raw:
            home = HermeticHome(raw)
            try:
                session, flex_pid, descendant = self._armed_home(home)
                # two failures recorded, then Flex dies ABNORMALLY: the third
                # failure turns the crash loop red, so the controller takes its
                # ORDINARY exit path — never a replacement.
                home.seed_crashes(2)
                home.release_flex(flex_pid, code=3)
                self._quarantine(home, "HOME n'a pas garde la session: aucune quarantaine")
                lock_free = home.session_lock_is_free()
                alive = process_state(session.pid) is not None
                workers = home.live_workers()
                refused = home.launch()                    # ← the REAL second launcher
                session.wait(timeout=150)
                events = home.events()

                self.assertFalse(lock_free, "ui-session.lock reste tenu pendant la quarantaine")
                self.assertTrue(alive, "HOME reste VIVANT: la quarantaine n'abandonne rien")
                self.assertEqual(len(workers), 1, "un seul worker, retenu, pendant la quarantaine")
                self.assertEqual(refused.returncode, 0, refused.stderr)
                self.assertIn("déjà active", refused.stdout,
                              "le VRAI openhtpc-session-start refuse un second HOME")
                self.assertIn("START_ALREADY_ACTIVE", home.events("session"),
                              "le refus est journalise par le protocole reel")
                self.assertNotIn("FLEX_RECOVERY_REQUESTED", events,
                                 "aucun execv: la sortie est celle DECIDEE")
                self.assertIn("HOME_AUTHORITY_RELEASE_PROVEN", events)
                self.assertNotIn("HOME_SESSION_LOOP_FAILED", events,
                                 "une sortie planifiee n'est pas un echec")
                self.assertEqual(session.returncode, 3,
                                 "le statut de Flex est porte par la sortie planifiee")
                self.assertTrue(wait_dead(descendant),
                                "le descendant resistant est nettoye par la preuve")
                self.assertTrue(home.session_lock_is_free(),
                                "une fois HOME sorti, la session est rendue")

                # ... and a THIRD real session-start ACQUIRES and progresses.
                (home.state / "flex-crashes.json").unlink(missing_ok=True)   # crash loop cleared
                home.release_publication_lock()        # the retained worker is gone
                home.start()
                deadline = time.monotonic() + 60
                started = 0
                while time.monotonic() < deadline:
                    started = home.events().count("FLEX_STARTED")
                    if started >= 2:
                        break
                    time.sleep(0.1)
                self.assertGreaterEqual(started, 2,
                                        "le second HOME acquiert la session et demarre Flex")
                self.assertTrue(home.live_controllers(),
                                "un controleur HOME vit a nouveau, sous la meme session")
                self.assertFalse(home.session_lock_is_free(),
                                 "le nouveau HOME detient lui aussi ui-session.lock")
            finally:
                home.close()


# ══════════════════════════════════════════════════════════════════════════════
# v8 — the REAL controller, started by the REAL openhtpc-session-start
#
# Codex's finding 4 rejected v7's ``HOME_LOCK_DRIVER``: a synthetic process that
# flocks a file proves nothing about the payload's session protocol, and a
# synthetic supervisor proves nothing about the controller's own boundary.  The
# fixture below runs the ACTUAL payload: the bash launcher with its ``exec 8>`` /
# ``flock -n 8`` protocol and its ``exec "$HOME_CONTROLLER"``, the actual
# ``openhtpc-home.py``, the actual engine, the actual runtime — inside a tree
# small enough to be hermetic.
#
# Two modules of the hermetic install are the payload BYTES plus a DECLARED tail
# (the harness re-checks the prefix relationship on every installation, and test
# 81 pins it): a fault injector for the runtime (the post-loop crash-loop lookup
# raises; the logger of the exception path raises) and a stand-in for the
# engine's terminator (a release that cannot be proven, i.e. the /proc race of
# the measured incident, plus the resistant descendant the worker leaves behind).
# Nothing else is altered: the controller under test is the byte-identical
# payload file, executed by the payload launcher.
# ══════════════════════════════════════════════════════════════════════════════

# A real install also carries these long-lived helpers; they are LEFT OUT on
# purpose: the optical monitor inherits the session lock (fd 8) and would hold it
# after HOME is gone, and the system view writes state behind the test's back.
HERMETIC_INSTALL_EXCLUDES = (
    "flex", "__pycache__", "VERSION",
    "openhtpc-optical-monitor", "openhtpc-system-page", "openhtpc-system-view",
    "openhtpc-refresh-match.py",
)

FLEX_STUB = '''#!/bin/sh
# Hermetic authoritative-UI stand-in: a REAL long-lived child, exactly where the
# controller's Popen() puts the real flex-launcher.  It announces itself, waits
# for the driver to release THIS instance (by pid), then exits with the status
# the driver asked for — so "Flex vanished on its own" is deterministic.
marker="$OPENHTPC_TEST_FLEX_DIR/started.$$"
: > "$marker"
while [ ! -f "$OPENHTPC_TEST_FLEX_DIR/release.$$" ]; do sleep 0.05; done
code=0
[ -f "$OPENHTPC_TEST_FLEX_DIR/exit-code.$$" ] && code="$(cat "$OPENHTPC_TEST_FLEX_DIR/exit-code.$$")"
exit "$code"
'''

HOME_ENGINE_INJECTION = '''
# ── hermetic test double (appended by the test suite; the payload engine is the
#    bytes above, byte for byte) ─────────────────────────────────────────────
import os as _os, signal as _signal, subprocess as _subprocess, sys as _sys

_TEST_BLIND = {"budget": int(_os.environ.get("OPENHTPC_TEST_BLIND_RELEASES", "0") or 0), "calls": 0}
_real_terminate_worker_group = terminate_worker_group


def terminate_worker_group(target, *args, **kwargs):
    """A release that cannot be PROVEN: the /proc the controller cannot read."""
    _TEST_BLIND["calls"] += 1
    if _TEST_BLIND["calls"] <= _TEST_BLIND["budget"]:
        return "GROUP_UNKNOWN"
    return _real_terminate_worker_group(target, *args, **kwargs)


# ``RegenerationSupervisor.__init__`` captured the terminator as a DEFAULT
# ARGUMENT, i.e. at class-definition time: rebinding the module name below is
# not enough.  Every default that still points at the original function is
# rebound to the stand-in, so the supervisor the CONTROLLER builds uses it.
RegenerationSupervisor.__init__.__defaults__ = tuple(
    terminate_worker_group if value is _real_terminate_worker_group else value
    for value in RegenerationSupervisor.__init__.__defaults__)


_real_write_flex_config = write_flex_config


def _arm_resistant_worker():
    """The regeneration worker leaves a SIGTERM-ignoring descendant behind."""
    pidfile = _os.environ.get("OPENHTPC_TEST_WORKER_DESCENDANT")
    if not pidfile or "--regenerate-only" not in _sys.argv:
        return
    if _os.environ.get("OPENHTPC_TEST_WORKER_ARMED"):
        return
    _os.environ["OPENHTPC_TEST_WORKER_ARMED"] = "1"
    _signal.signal(_signal.SIGTERM, _signal.SIG_IGN)
    child = _subprocess.Popen(
        [_sys.executable, "-c",
         "import signal, time; signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(120)"],
        stdin=_subprocess.DEVNULL, stdout=_subprocess.DEVNULL, stderr=_subprocess.DEVNULL)
    with open(pidfile, "w") as stream:
        stream.write(str(child.pid))


def write_flex_config(path, home, sources, install=None, expected_optical_generation=None,
                      media_generation=None):
    _arm_resistant_worker()
    return _real_write_flex_config(path, home, sources, install, expected_optical_generation,
                                   media_generation)


class PacingUnavailable(BaseException):
    """The recovery sleeper failed (finding Codex v8-1)."""


def _test_fault(name):
    root = _os.environ.get("OPENHTPC_TEST_FAULTS")
    return bool(root) and _os.path.exists(_os.path.join(root, name))


_real_pace_sleep = time.sleep
_real_guarded_release = guarded_release
_TEST_PACE = {"calls": 0}


def _faulting_pace_sleep(seconds):
    """The FIRST recovery pacing fails (finding Codex v8-1): HOME must go on."""
    if _test_fault("pacing-raise"):
        _TEST_PACE["calls"] += 1
        if _TEST_PACE["calls"] == 1:
            raise PacingUnavailable("the recovery sleeper failed (injected)")
    return _real_pace_sleep(seconds)


def _outage_pace_sleep(seconds):
    """A recovery sleeper that fails on EVERY call (blocker Codex v10-1)."""
    raise PacingUnavailable("the recovery sleeper is broken (injected)")


_TEST_OUTAGE = {"armed": False}


def _arm_pacing_outage():
    """Arm the WHOLE combination Codex v10-1 named — inside the running payload.

    A sleeper that always fails, a clock that no longer answers, and a clock-wait
    that returns INSTANTLY WITHOUT RAISING: three faults that together used to
    end the pacing before ``_PACE_SELECT`` was ever reached.  Every ``select``
    the gate really makes is appended to a file the test reads back, so the
    pacing path is OBSERVED — never inferred from a duration alone.
    """
    global _PACE_CLOCK, _PACE_CLOCK_WAIT, _PACE_SELECT
    if _TEST_OUTAGE["armed"]:
        return
    _TEST_OUTAGE["armed"] = True
    _real_pace_select = _PACE_SELECT
    _select_log = _os.path.join(_os.environ.get("OPENHTPC_TEST_FAULTS", "."),
                                "pacing-select.log")

    def counting_select(*args, **kwargs):
        with open(_select_log, "a") as stream:
            stream.write("select")
            stream.write(chr(10))
        return _real_pace_select(*args, **kwargs)

    def outage_clock():
        raise PacingUnavailable("the pacing clock is broken (injected)")

    def outage_wait(timeout=None):
        return None                      # ← returns at once, and does NOT raise

    _PACE_CLOCK = outage_clock
    _PACE_CLOCK_WAIT = outage_wait
    _PACE_SELECT = counting_select


def guarded_release(*args, **kwargs):
    """Fault injector for the ONE seam the controller hands the gate.

    The controller calls the REAL gate and passes its own sleeper; the injector
    only REPLACES that sleeper while the fault is armed, so the production gate
    (its guard, its quarantine, its proof) is the code under test — never a
    stand-in for it.  Without the fault file it is a transparent pass-through.

    v11 adds the OUTAGE arming: the faults are applied inside the running
    process, at the gate's own call, because ``_PACE_CLOCK`` may only be faulted
    after the payload is fully imported.
    """
    if _test_fault("pacing-raise"):
        kwargs["sleep"] = _faulting_pace_sleep
    if _test_fault("pacing-clock-outage"):
        _arm_pacing_outage()
        kwargs["sleep"] = _outage_pace_sleep
    return _real_guarded_release(*args, **kwargs)
'''

HOME_RUNTIME_INJECTION = '''
# ── hermetic test double (appended by the test suite; the payload runtime is the
#    bytes above, byte for byte) ─────────────────────────────────────────────
import os as _os

_real_log = log
_real_crash_loop_state = crash_loop_state


class HomeDiagnosticUnavailable(RuntimeError):
    """The POST-LOOP crash-loop diagnostic could not be read (injected fault)."""


class HomeDiagnosticUnprintable(BaseException):
    """An exception that REFUSES to be described (finding Codex v8-2).

    ``str(exc)`` used to be evaluated BEFORE the non-escaping logging seam, so an
    exception of this shape escaped the controller's boundary, masked itself and
    skipped ``guarded_release`` entirely.
    """

    def __str__(self):
        raise RuntimeError("__str__ is broken (injected)")

    def __repr__(self):
        raise RuntimeError("__repr__ is broken (injected)")


class _HostileNameMeta(type):
    """A metaclass whose ``__name__`` RAISES (blocker Codex v9-2)."""

    @property
    def __name__(cls):
        raise RuntimeError("__name__ is broken (injected)")


class HomeDiagnosticHostile(BaseException, metaclass=_HostileNameMeta):
    """An exception that refuses ``str()``, ``repr()`` AND its own type NAME.

    Naming it (``type(exc).__name__``) used to sit outside every guard in HOME's
    boundary and in ``guarded_release``'s post-proof diagnostics, so the very act
    of describing the failure could replace it.
    """

    def __str__(self):
        raise RuntimeError("__str__ is broken (injected)")

    def __repr__(self):
        raise RuntimeError("__repr__ is broken (injected)")


def _test_fault(name):
    root = _os.environ.get("OPENHTPC_TEST_FAULTS")
    return bool(root) and _os.path.exists(_os.path.join(root, name))


def crash_loop_state(home, now=None):
    """The lookup that runs AFTER the loop fails (finding Codex v7-1).

    Only the calls WITHOUT an explicit ``now`` are faulted: those are the two
    startup lookups (before the fault file exists) and the post-loop one, which
    is the call that used to sit outside the boundary.
    """
    if now is None and _test_fault("crash-loop-raise"):
        raise HomeDiagnosticUnavailable("the crash-loop journal cannot be read (injected)")
    if now is None and _test_fault("crash-loop-raise-unprintable"):
        raise HomeDiagnosticUnprintable("indescribable (injected)")
    if now is None and _test_fault("crash-loop-raise-hostile"):
        raise HomeDiagnosticHostile("hostile (injected)")
    return _real_crash_loop_state(home, now)


def log(home, component, event, **fields):
    """The logger OF THE EXCEPTION PATH fails (finding Codex v7-2)."""
    if event == "HOME_SESSION_LOOP_FAILED" and _test_fault("logger-raise"):
        raise RuntimeError("the journal writer is unavailable (injected)")
    return _real_log(home, component, event, **fields)
'''

HERMETIC_PROFILE = {
    "generator": {"name": "OPENHTPC Builder", "version": "1.3.1"},
    "detected": {"cpu": "hermetic"},
    "gpu_topology": {"processing_gpu": {"vendor": "amd"}},
    "video_backend": {"status": "observed", "decode_api": "vaapi", "render_api": "opengl",
                      "render_node": "/dev/dri/renderD128"},
    "runtime": {"status": "ready", "playback_validated": False},
}
HERMETIC_USER_CONFIG = {"configuration_completed": True, "local_media_sources": [],
                        "tmdb": {"configured": False}}


def live_processes(needle):
    """Every live process of this uid whose /proc cmdline contains ``needle``."""
    found = []
    for entry in pathlib.Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        try:
            if entry.stat().st_uid != os.getuid():
                continue
            command = (entry / "cmdline").read_bytes().split(b"\0")
        except OSError:
            continue
        text = b" ".join(item for item in command if item).decode("utf-8", "replace")
        if needle in text:
            found.append((int(entry.name), text))
    return sorted(found)


class HermeticHome:
    """The payload controller, the payload launcher, a real worker group.

    ``build()`` wires the tree; ``start()`` runs the REAL
    ``openhtpc-session-start``, which acquires ``ui-session.lock`` on fd 8,
    passes the gate, and ``exec``s the payload controller — so the process the
    test holds IS the controller, holding the lock the launcher took.
    """

    def __init__(self, root):
        self.root = pathlib.Path(root)
        self.home = self.root / "home"
        self.install = self.root / "install"
        self.faults_dir = self.root / "faults"
        self.flex_dir = self.root / "flex-stand-in"
        self.descendant_pidfile = self.root / "descendant.pid"
        self.launcher = PAYLOAD / "openhtpc-session-start"
        self.config = self.home / ".config/openhtpc/flex-v1.ini"
        self.state = self.home / ".local/state/openhtpc"
        self.blind_releases = 0
        self.resistant_worker = False
        self.sessions = []
        self._lock_fd = None
        self._lock_file = None

    # ── installation ────────────────────────────────────────────────────────
    def build(self, blind_releases=0, resistant_worker=False):
        self.blind_releases = int(blind_releases)
        self.resistant_worker = bool(resistant_worker)
        (self.home / ".config/openhtpc/runtime/mpv").mkdir(parents=True, exist_ok=True)
        self.state.mkdir(parents=True, exist_ok=True)
        self.faults_dir.mkdir(parents=True, exist_ok=True)
        self.flex_dir.mkdir(parents=True, exist_ok=True)
        self.install.mkdir(parents=True, exist_ok=True)

        payload_engine = (PAYLOAD / "openhtpc-session-engine.py").read_bytes()
        payload_runtime = (PAYLOAD / "openhtpc-runtime.py").read_bytes()
        for entry in sorted(PAYLOAD.iterdir()):
            if entry.name in HERMETIC_INSTALL_EXCLUDES:
                continue
            (self.install / entry.name).symlink_to(entry)
        # the two injected modules: the payload bytes PLUS a declared tail
        injected_engine = payload_engine + HOME_ENGINE_INJECTION.encode()
        injected_runtime = payload_runtime + HOME_RUNTIME_INJECTION.encode()
        self.assert_prefix(payload_engine, injected_engine, "engine")
        self.assert_prefix(payload_runtime, injected_runtime, "runtime")
        (self.install / "openhtpc-session-engine.py").unlink()
        (self.install / "openhtpc-runtime.py").unlink()
        (self.install / "openhtpc-session-engine.py").write_bytes(injected_engine)
        (self.install / "openhtpc-runtime.py").write_bytes(injected_runtime)
        (self.install / "openhtpc-runtime.py").chmod(0o755)
        (self.install / "flex/bin").mkdir(parents=True, exist_ok=True)
        stub = self.install / "flex/bin/flex-launcher"
        stub.write_text(FLEX_STUB, encoding="utf-8")
        stub.chmod(0o755)

        profile = json.loads(json.dumps(HERMETIC_PROFILE))
        profile["runtime_profiles"] = {"profiles": {"PURE": {
            "generation_status": "generated",
            "config_path": str(self.home / ".config/openhtpc/runtime/mpv/pure.conf")}}}
        (self.home / ".config/openhtpc/profile.json").write_text(json.dumps(profile))
        (self.home / ".config/openhtpc/runtime/mpv/pure.conf").write_text("profile=fast\n")
        (self.home / ".config/openhtpc/user-config.json").write_text(json.dumps(HERMETIC_USER_CONFIG))
        self.set_optical(93)

    @staticmethod
    def assert_prefix(payload_bytes, injected_bytes, label):
        if not injected_bytes.startswith(payload_bytes):
            raise AssertionError(f"the hermetic {label} is not the payload bytes plus a tail")
        if injected_bytes[len(payload_bytes):].decode("utf-8") not in (
                HOME_ENGINE_INJECTION, HOME_RUNTIME_INJECTION):
            raise AssertionError(f"the hermetic {label} tail is not the declared injection")

    # ── environment / launcher ──────────────────────────────────────────────
    def env(self):
        environment = dict(os.environ)
        for name in ("OPENHTPC_SESSION_ACTIVE", "OPENHTPC_SESSION_LOCK_FD", "OPENHTPC_MONITOR_STARTED",
                     "OPENHTPC_SESSION_ID", "OPENHTPC_INHIBITED"):
            environment.pop(name, None)
        environment.update({
            "OPENHTPC_HOME": str(self.home),
            "OPENHTPC_INSTALL_DIR": str(self.install),
            "DISPLAY": ":0",
            "OPENHTPC_INHIBITED": "1",
            "OPENHTPC_DISPLAY_SIZE": "1920x1080",
            "OPENHTPC_TEST_FAULTS": str(self.faults_dir),
            "OPENHTPC_TEST_BLIND_RELEASES": str(self.blind_releases),
            "OPENHTPC_TEST_FLEX_DIR": str(self.flex_dir),
            "PATH": str(pathlib.Path(sys.executable).parent) + ":" + environment.get("PATH", ""),
        })
        if self.resistant_worker:
            environment["OPENHTPC_TEST_WORKER_DESCENDANT"] = str(self.descendant_pidfile)
        else:
            environment.pop("OPENHTPC_TEST_WORKER_DESCENDANT", None)
        return environment

    def start(self):
        """Run the REAL launcher: it locks, gates, then execs the payload controller."""
        session = subprocess.Popen([str(self.launcher)], env=self.env(),
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.sessions.append(session)
        return session

    def launch(self, timeout=120):
        """One synchronous launcher run — a SECOND ``openhtpc-session-start``."""
        return subprocess.run([str(self.launcher)], env=self.env(), capture_output=True,
                              text=True, timeout=timeout)

    def fault(self, name):
        (self.faults_dir / name).write_text("injected\n")

    # ── observation ─────────────────────────────────────────────────────────
    def records(self):
        target = self.state / "runtime.log"
        try:
            text = target.read_text(encoding="utf-8")
        except OSError:
            return []
        out = []
        for line in text.splitlines():
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return out

    def events(self, component=None):
        return [record.get("event") for record in self.records()
                if component is None or record.get("component") == component]

    def wait_event(self, event, timeout=30.0):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if event in self.events():
                return True
            time.sleep(0.05)
        return False

    def wait_started_flex(self, timeout=30.0):
        """The pid of the Flex stand-in the controller started (its own child)."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            markers = sorted(self.flex_dir.glob("started.*"))
            if markers:
                return int(markers[0].name.split(".")[1])
            time.sleep(0.05)
        raise AssertionError("the controller never started the Flex stand-in")

    def release_flex(self, flex_pid, code=0):
        (self.flex_dir / f"exit-code.{flex_pid}").write_text(str(code))
        (self.flex_dir / f"release.{flex_pid}").write_text("go\n")

    def wait_descendant(self, timeout=20.0):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                text = self.descendant_pidfile.read_text().strip()
            except OSError:
                text = ""
            if text.isdigit():
                return remember(int(text))
            time.sleep(0.05)
        raise AssertionError("the retained worker never armed its resistant descendant")

    def seed_crashes(self, count=2):
        """Record ``count`` recent Flex failures — AFTER the controller started.

        The startup lookup refuses to launch Flex over a recorded crash loop, so a
        journal seeded before the launcher would never let HOME start.  Seeded
        here, the NEXT abnormal exit (``record_flex_exit``) turns the loop red and
        the controller takes its ORDINARY ``FLEX_EXIT`` path instead of replacing
        itself.
        """
        now = time.time()
        (self.state / "flex-crashes.json").write_text(json.dumps(
            {"schema": 1, "events": [now - 5.0 * (index + 1) for index in range(int(count))],
             "last_returncode": 3, "last_runtime_seconds": 1.0, "updated": now}))

    def set_optical(self, generation):
        (self.state / "optical-current.json").write_text(json.dumps({
            "generation": int(generation), "canonical_state": "DVD_VIDEO", "state": "DVD",
            "device": "/dev/sr0", "ui_state_hash": f"hash-{generation}"}))

    def flex_config_hash(self):
        try:
            return hashlib.sha256(self.config.read_bytes()).hexdigest()
        except OSError:
            return "absent"

    def live_workers(self):
        return [(pid, text) for pid, text in live_processes("--regenerate-only")]

    def live_controllers(self):
        needle = str(self.install / "openhtpc-home.py")
        return [(pid, text) for pid, text in live_processes(needle) if "--regenerate-only" not in text]

    # ── the session lock, as the launcher takes it ──────────────────────────
    def hold_publication_lock(self):
        """Hold the engine's OWN publication lock, so the worker stays LIVE."""
        self._lock_file = self.home / ".local/state/openhtpc/flex-publication.lock"
        self._lock_file.parent.mkdir(parents=True, exist_ok=True)
        self._lock_fd = os.open(str(self._lock_file), os.O_RDWR | os.O_CREAT, 0o600)
        fcntl.flock(self._lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)

    def release_publication_lock(self):
        """Stop holding the engine's publication lock (the worker is gone by then)."""
        if self._lock_fd is not None:
            fcntl.flock(self._lock_fd, fcntl.LOCK_UN)
            os.close(self._lock_fd)
            self._lock_fd = None

    def session_lock_is_free(self):
        """A SECOND session-start (or HOME) must not be able to take the lock."""
        fd = os.open(str(self.state / "ui-session.lock"), os.O_RDWR | os.O_CREAT, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except OSError:
            return False
        finally:
            os.close(fd)

    # ── teardown ────────────────────────────────────────────────────────────
    def close(self):
        """Leave nothing behind: workers first, then Flex, then the controllers."""
        for pid, _text in self.live_workers():
            try:
                os.killpg(pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError, OSError):
                pass
        for pid, text in live_processes(str(self.install / "flex/bin/flex-launcher")):
            try:
                os.kill(pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError, OSError):
                pass
        for session in self.sessions:
            if session.poll() is None:
                session.kill()
            try:
                session.wait(timeout=10)
            except Exception:                                        # noqa: BLE001
                pass
            try:
                session.communicate(timeout=5)
            except Exception:                                        # noqa: BLE001
                pass
            for stream in (session.stdout, session.stderr):
                if stream is not None:
                    try:
                        stream.close()
                    except Exception:                                # noqa: BLE001
                        pass
        for pid, text in self.live_controllers():
            try:
                os.kill(pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError, OSError):
                pass
        if self._lock_fd is not None:
            os.close(self._lock_fd)
            self._lock_fd = None


class HomeTotalBoundary(HermeticHomeCase):
    """EXECUTED (v8, finding Codex v7-1/v7-2): the payload controller keeps its
    authority through the WHOLE post-supervisor life — the crash-loop lookup,
    the recovery/exit decision and their own failures included.

    Every test here runs the REAL ``openhtpc-home.py`` (bytes of the payload, via
    the payload launcher), with a REAL regeneration worker whose process group is
    retained — a live worker, a live SIGTERM-ignoring descendant, and a release
    the engine cannot PROVE — while the gate quarantines HOME.
    """

    def test_78_an_exception_from_the_post_loop_crash_loop_lookup_stays_inside_the_guard(self):
        with tempfile.TemporaryDirectory() as raw:
            home = HermeticHome(raw)
            try:
                session, flex_pid, descendant = self._armed_home(
                    home, faults=("crash-loop-raise",))
                # the fault exists now: the NEXT crash-loop lookup without an
                # explicit `now` is the POST-LOOP one (line 468 of the payload).
                home.release_flex(flex_pid, code=0)
                self._quarantine(home, "HOME n'a pas quarantaine: l'exception post-loop a echappe")
                lock_free = home.session_lock_is_free()
                during_hash = home.flex_config_hash()
                during_workers = len(home.live_workers())
                alive = process_state(session.pid) is not None
                during_events = home.events()

                self.assertFalse(lock_free,
                                 "HOME doit garder ui-session.lock pendant la quarantaine")
                self.assertTrue(alive, "HOME doit rester VIVANT pendant la quarantaine")
                self.assertEqual(during_workers, 1, "aucun nouveau worker pendant la quarantaine")
                self.assertEqual(home.flex_config_hash(), during_hash,
                                 "aucune publication pendant la quarantaine")
                self.assertNotIn("FLEX_RECOVERY_REQUESTED", during_events,
                                 "aucun execv pendant la quarantaine")
                self.assertIn("HOME_DRAIN_CLEANUP_UNPROVEN", during_events)

                session.wait(timeout=150)
                events = home.events()
                errors = session.stderr.read().decode("utf-8", "replace")

                self.assertIn("HOME_AUTHORITY_RELEASE_PROVEN", events,
                              "la liberation doit etre PROUVEE avant toute sortie")
                self.assertIn("HOME_SESSION_EXCEPTION_RERAISED", events)
                self.assertLess(events.index("HOME_AUTHORITY_RELEASE_PROVEN"),
                                events.index("HOME_SESSION_EXCEPTION_RERAISED"),
                                "l'exception d'origine n'est relevee QU'APRES la preuve")
                self.assertEqual(session.returncode, 1,
                                 "l'exception non planifiee termine HOME")
                self.assertIn("HomeDiagnosticUnavailable", errors,
                              "l'exception d'origine est celle qui sort, jamais masquee")
                self.assertIn("crash_loop_state", errors)
                self.assertTrue(wait_dead(descendant),
                                "le descendant resistant est nettoye par la preuve")
                self.assertTrue(home.session_lock_is_free(),
                                "une fois HOME sorti, la session est rendue")
            finally:
                home.close()

    def test_79_a_logger_failing_on_the_exception_path_cannot_mask_it_or_skip_the_gate(self):
        with tempfile.TemporaryDirectory() as raw:
            home = HermeticHome(raw)
            try:
                session, flex_pid, descendant = self._armed_home(
                    home, faults=("crash-loop-raise", "logger-raise"))
                home.release_flex(flex_pid, code=0)
                self._quarantine(home, "le logger de l'exception a contourne la porte")
                lock_free = home.session_lock_is_free()
                session.wait(timeout=150)
                events = home.events()
                errors = session.stderr.read().decode("utf-8", "replace")

                self.assertFalse(lock_free,
                                 "HOME garde la session malgre l'echec du logger")
                # the failing write is absorbed: it never became an event, and the
                # gate's own events went through the same seam untouched.
                self.assertNotIn("HOME_SESSION_LOOP_FAILED", events,
                                 "l'ecriture qui a echoue est absorbee, jamais fatale")
                self.assertIn("HOME_AUTHORITY_RELEASE_PROVEN", events)
                self.assertIn("HOME_SESSION_EXCEPTION_RERAISED", events)
                # the ORIGINAL exception is the one that leaves: the logger's own
                # failure never replaces the story it was reporting.
                self.assertIn("HomeDiagnosticUnavailable", errors)
                self.assertNotIn("the journal writer is unavailable", errors,
                                 "le logger ne masque rien: son echec est absorbe")
                self.assertTrue(wait_dead(descendant))
            finally:
                home.close()

    def test_85_a_failing_sleeper_and_an_indescribable_exception_stay_inside_the_guard(self):
        """EXECUTED (v9, findings Codex v8-1 AND v8-2) — on the REAL controller.

        The payload launcher starts the byte-identical payload controller, with a
        REAL retained worker group, while BOTH v8 blockers are injected at once:
        the recovery sleeper fails on its first pacing, and the post-loop
        crash-loop lookup raises an exception whose ``__str__`` and ``__repr__``
        both raise.  HOME must keep its authority for the whole quarantine —
        alive, holding ``ui-session.lock``, no ``execv``, no new worker, no
        publication, and a second REAL ``openhtpc-session-start`` refused — then
        prove the release, and only THEN re-raise the ORIGINAL exception.  The
        journal carries the fail-closed placeholder, so nothing about the
        exception ever decided anything.
        """
        with tempfile.TemporaryDirectory() as raw:
            home = HermeticHome(raw)
            try:
                session, flex_pid, descendant = self._armed_home(
                    home, faults=("crash-loop-raise-unprintable", "pacing-raise"))
                home.release_flex(flex_pid, code=0)
                self._quarantine(
                    home, "HOME n'a pas quarantaine: le reveil defaillant l'a fait sortir")
                lock_free = home.session_lock_is_free()
                during_hash = home.flex_config_hash()
                during_events = home.events()
                alive = process_state(session.pid) is not None
                refused = home.launch()                # ← the REAL second launcher

                self.assertFalse(lock_free,
                                 "ui-session.lock reste tenu malgre le reveil defaillant")
                self.assertTrue(alive, "HOME reste VIVANT pendant la quarantaine")
                self.assertEqual(len(home.live_workers()), 1,
                                 "aucun nouveau worker pendant la quarantaine")
                self.assertEqual(home.flex_config_hash(), during_hash,
                                 "aucune publication pendant la quarantaine")
                self.assertNotIn("FLEX_RECOVERY_REQUESTED", during_events,
                                 "aucun execv pendant la quarantaine")
                self.assertIn("HOME_DRAIN_CLEANUP_UNPROVEN", during_events)
                self.assertEqual(refused.returncode, 0, refused.stderr)
                self.assertIn("déjà active", refused.stdout,
                              "le VRAI openhtpc-session-start refuse un second HOME")

                session.wait(timeout=150)
                events = home.events()
                errors = session.stderr.read().decode("utf-8", "replace")
                failed = [record for record in home.records()
                          if record.get("event") == "HOME_SESSION_LOOP_FAILED"]

                self.assertIn("HOME_PACING_UNAVAILABLE", events,
                              "la defaillance du reveil est ABSORBEE, jamais fatale")
                self.assertEqual(events.count("HOME_PACING_UNAVAILABLE"), 1,
                                 "une seule fois: HOME n'a pas boucle sur sa panne de pacing")
                self.assertIn("HOME_AUTHORITY_RELEASE_PROVEN", events,
                              "la liberation est PROUVEE malgre le reveil defaillant")
                self.assertIn("HOME_SESSION_EXCEPTION_RERAISED", events)
                self.assertLess(events.index("HOME_AUTHORITY_RELEASE_PROVEN"),
                                events.index("HOME_SESSION_EXCEPTION_RERAISED"),
                                "l'exception d'origine n'est relevee QU'APRES la preuve")
                self.assertEqual(session.returncode, 1,
                                 "l'exception non planifiee termine HOME")
                self.assertEqual(len(failed), 1,
                                 "l'echec post-boucle est journalise EXACTEMENT une fois")
                self.assertEqual(failed[0].get("exception_type"), "HomeDiagnosticUnprintable")
                self.assertEqual(failed[0].get("exception"),
                                 "<HomeDiagnosticUnprintable: unprintable>",
                                 "le diagnostic SAFE remplace str(exc): rien ne decide avant la porte")
                self.assertIn("HomeDiagnosticUnprintable", errors,
                              "l'exception d'origine est celle qui sort, jamais masquee")
                self.assertTrue(wait_dead(descendant),
                                "le descendant resistant est nettoye par la preuve")
                self.assertTrue(home.session_lock_is_free(),
                                "une fois HOME sorti, la session est rendue")
            finally:
                home.close()

    def test_86_a_failing_sleeper_alone_cannot_kill_home_during_the_quarantine(self):
        """EXECUTED (v9, finding Codex v8-1) — on the REAL controller, ISOLATED.

        Only the PACING is faulted (the post-loop exception is the ordinary,
        printable ``HomeDiagnosticUnavailable``): the gate is entered, the drain
        comes back UNPROVEN, and the very first recovery pacing fails.  On v8
        that ``sleep`` sat OUTSIDE the guard, so HOME died mid-quarantine with a
        retained group and released ``ui-session.lock`` — the isolated RED of this
        finding.  Here HOME must survive its own pacing failure and finish the
        quarantine with the release PROVEN.
        """
        with tempfile.TemporaryDirectory() as raw:
            home = HermeticHome(raw)
            try:
                session, flex_pid, descendant = self._armed_home(
                    home, faults=("crash-loop-raise", "pacing-raise"))
                home.release_flex(flex_pid, code=0)
                self._quarantine(
                    home, "HOME n'a pas quarantaine: le reveil defaillant l'a fait sortir")
                during_events = home.events()
                alive = process_state(session.pid) is not None

                self.assertTrue(alive, "HOME survit a la panne de son propre pacing")
                self.assertFalse(home.session_lock_is_free(),
                                 "et garde ui-session.lock pendant toute la quarantaine")
                self.assertNotIn("FLEX_RECOVERY_REQUESTED", during_events,
                                 "aucun execv pendant la quarantaine")
                self.assertIn("HOME_DRAIN_CLEANUP_UNPROVEN", during_events)

                session.wait(timeout=150)
                events = home.events()
                errors = session.stderr.read().decode("utf-8", "replace")

                self.assertIn("HOME_PACING_UNAVAILABLE", events)
                self.assertEqual(events.count("HOME_PACING_UNAVAILABLE"), 1,
                                 "une seule panne de pacing: HOME ne boucle pas dessus")
                self.assertIn("HOME_AUTHORITY_RELEASE_PROVEN", events,
                              "la quarantaine aboutit a la PREUVE malgre le pacing defaillant")
                self.assertIn("HOME_SESSION_EXCEPTION_RERAISED", events)
                self.assertLess(events.index("HOME_PACING_UNAVAILABLE"),
                                events.index("HOME_AUTHORITY_RELEASE_PROVEN"))
                self.assertLess(events.index("HOME_AUTHORITY_RELEASE_PROVEN"),
                                events.index("HOME_SESSION_EXCEPTION_RERAISED"))
                self.assertEqual(session.returncode, 1)
                self.assertIn("HomeDiagnosticUnavailable", errors,
                              "l'exception d'origine sort: la panne de pacing ne la masque pas")
                self.assertNotIn("PacingUnavailable", errors,
                                 "la panne de pacing n'est JAMAIS l'exception rapportee")
                self.assertTrue(wait_dead(descendant))
                self.assertTrue(home.session_lock_is_free())
            finally:
                home.close()


class HostileExceptionIdentityIsQuarantined(HermeticHomeCase):
    """EXECUTED (v10, blocker Codex v9-2) — on the REAL controller.

    The post-loop exception refuses ``str()``, ``repr()`` AND its own type name
    (a hostile metaclass), so describing it used to raise *before* the gate:
    HOME died, released ``ui-session.lock`` and abandoned the retained group.  It
    must instead quarantine, keep its authority (a second launcher is refused),
    journal SAFE diagnostics only, and re-raise the very same instance after the
    release is PROVEN.
    """

    def test_92_the_real_home_quarantines_an_exception_that_refuses_its_own_name(self):
        with tempfile.TemporaryDirectory() as raw:
            home = HermeticHome(raw)
            try:
                proc, flex_pid, descendant = self._armed_home(
                    home, faults=("crash-loop-raise-hostile",))
                home.release_flex(flex_pid, code=0)
                self._quarantine(
                    home, "HOME n'a pas quarantaine: nommer l'exception l'a fait sortir")
                lock_free = home.session_lock_is_free()
                during_hash = home.flex_config_hash()
                during_events = home.events()
                alive = process_state(proc.pid) is not None
                refused = home.launch()                # ← the REAL second launcher

                self.assertFalse(lock_free,
                                 "ui-session.lock reste tenu malgre la metaclasse hostile")
                self.assertTrue(alive, "HOME reste VIVANT pendant la quarantaine")
                self.assertEqual(len(home.live_workers()), 1,
                                 "aucun nouveau worker pendant la quarantaine")
                self.assertEqual(home.flex_config_hash(), during_hash,
                                 "aucune publication pendant la quarantaine")
                self.assertNotIn("FLEX_RECOVERY_REQUESTED", during_events,
                                 "aucun execv pendant la quarantaine")
                self.assertIn("HOME_DRAIN_CLEANUP_UNPROVEN", during_events)
                self.assertEqual(refused.returncode, 0, refused.stderr)
                self.assertIn("déjà active", refused.stdout,
                              "le VRAI openhtpc-session-start refuse un second HOME")

                proc.wait(timeout=150)
                events = home.events()
                errors = proc.stderr.read().decode("utf-8", "replace")
                failed = [record for record in home.records()
                          if record.get("event") == "HOME_SESSION_LOOP_FAILED"]
                reraised = [record for record in home.records()
                            if record.get("event") == "HOME_SESSION_EXCEPTION_RERAISED"]

                self.assertEqual(proc.returncode, 1,
                                 "l'exception non planifiee termine HOME")
                self.assertEqual(len(failed), 1,
                                 "l'echec post-boucle est journalise EXACTEMENT une fois")
                self.assertEqual(failed[0].get("exception_type"), "unknown-type",
                                 "le nom du type vient d'une garde BaseException")
                self.assertEqual(failed[0].get("exception"), "<unknown-type: unprintable>",
                                 "le diagnostic SAFE remplace str(exc)")
                self.assertEqual([record.get("exception_type") for record in reraised],
                                 ["unknown-type"],
                                 "le re-raise n'utilise que des diagnostics SAFE")
                self.assertIn("HOME_AUTHORITY_RELEASE_PROVEN", events)
                self.assertLess(events.index("HOME_AUTHORITY_RELEASE_PROVEN"),
                                events.index("HOME_SESSION_EXCEPTION_RERAISED"),
                                "l'exception d'origine n'est relevee QU'APRES la preuve")
                self.assertIn("HomeDiagnosticHostile", errors,
                              "l'exception d'origine est celle qui sort, jamais masquee")
                self.assertNotIn("__name__ is broken", errors,
                                 "aucun diagnostic n'a remplace l'exception d'origine")
                self.assertNotIn("__str__ is broken", errors,
                                 "aucun diagnostic n'a remplace l'exception d'origine")
                self.assertTrue(wait_dead(descendant),
                                "le descendant resistant est nettoye par la preuve")
                self.assertTrue(home.session_lock_is_free(),
                                "une fois HOME sorti, la session est rendue")
            finally:
                home.close()


class PacingOutageOnTheRealHome(HermeticHomeCase):
    """EXECUTED (v11, blocker Codex v10-1) — sur le VRAI controleur HOME.

    La combinaison exacte nommee par le blocker est ARMED DANS le processus qui
    tourne : un reveil qui echoue a CHAQUE appel, une horloge de pacing qui ne
    repond plus, et une clock-wait qui rend la main INSTANTANEMENT sans lever.
    v10 lisait ce waiter non mesurable comme un intervalle consomme, n'atteignait
    jamais ``_PACE_SELECT`` et laissait la boucle de recovery tourner sans
    cadence.  La porte doit au contraire porter le pacing sur sa primitive
    INDEPENDANTE, garder l'autorite (``ui-session.lock``, groupe retenu, aucune
    publication, aucun nouveau worker, aucun execv) pendant tout ce chemin, et
    n'atteindre la preuve qu'apres un intervalle REELLEMENT consomme.

    Chaque ``select`` reellement fait par la porte est consigne par l'injection
    dans ``<faults>/pacing-select.log`` : le chemin de pacing est OBSERVE, jamais
    deduit d'une duree.
    """

    @staticmethod
    def _selects(home):
        try:
            return len((home.faults_dir / "pacing-select.log").read_text().splitlines())
        except OSError:
            return 0

    def _wait_selects(self, home, count, timeout=20.0):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self._selects(home) >= count:
                return True
            time.sleep(0.1)
        return False

    def test_101_the_real_home_stays_paced_and_keeps_its_authority_under_the_outage(self):
        with tempfile.TemporaryDirectory() as raw:
            home = HermeticHome(raw)
            try:
                proc, flex_pid, descendant = self._armed_home(
                    home, faults=("crash-loop-raise-hostile", "pacing-clock-outage"))
                home.release_flex(flex_pid, code=0)
                self._quarantine(
                    home, "HOME n'a pas quarantaine sous la panne de pacing nommee")
                started = time.monotonic()
                lock_free = home.session_lock_is_free()
                during_hash = home.flex_config_hash()
                during_events = home.events()
                during_workers = len(home.live_workers())
                alive = process_state(proc.pid) is not None
                paced = self._wait_selects(home, 2)
                elapsed = time.monotonic() - started

                self.assertTrue(paced,
                                "la primitive INDEPENDANTE (select) porte le pacing: un waiter "
                                "non mesurable ne peut PAS rendre la boucle non pacee")
                self.assertGreaterEqual(
                    elapsed, session.GUARDED_RECOVERY_PAUSE_S * 0.4,
                    "les tours sont REELLEMENT espaces par leur intervalle (pas un spin)")
                self.assertFalse(lock_free,
                                 "ui-session.lock reste tenu pendant tout le chemin")
                self.assertTrue(alive, "HOME reste VIVANT pendant la quarantaine")
                self.assertEqual(during_workers, 1, "aucun nouveau worker pendant la quarantaine")
                self.assertEqual(home.flex_config_hash(), during_hash,
                                 "aucune publication pendant la quarantaine")
                self.assertNotIn("FLEX_RECOVERY_REQUESTED", during_events,
                                 "aucun execv pendant la quarantaine")
                self.assertIn("HOME_DRAIN_CLEANUP_UNPROVEN", during_events)

                proc.wait(timeout=150)
                events = home.events()
                errors = proc.stderr.read().decode("utf-8", "replace")
                records = home.records()
                unverified = [record for record in records
                              if record.get("event") == "HOME_PACING_UNVERIFIED"]

                self.assertEqual(proc.returncode, 1, "l'exception non planifiee termine HOME")
                self.assertEqual([record.get("pacing_tier") for record in unverified],
                                 ["CLOCK_WAIT"] * len(unverified),
                                 "le waiter rendu instantanement est journalise NON PROUVE")
                self.assertEqual({record.get("pacing_reason") for record in unverified},
                                 {"UNDERSPENT"})
                self.assertNotIn("HOME_PACING_HOLD", events,
                                 "une preuve a ete atteinte: le hold n'est pas le chemin")
                self.assertIn("HOME_AUTHORITY_RELEASE_PROVEN", events)
                self.assertLess(events.index("HOME_AUTHORITY_RELEASE_PROVEN"),
                                events.index("HOME_SESSION_EXCEPTION_RERAISED"),
                                "l'exception d'origine n'est relevee QU'APRES la preuve")
                self.assertIn("HomeDiagnosticHostile", errors,
                              "l'exception d'origine est celle qui sort, jamais masquee")
                self.assertNotIn("__name__ is broken", errors)
                self.assertTrue(wait_dead(descendant),
                                "le descendant resistant est nettoye par la preuve")
                self.assertTrue(home.session_lock_is_free(),
                                "une fois HOME sorti, la session est rendue")
            finally:
                home.close()


class PacingIsFailClosed(unittest.TestCase):
    """EXECUTED (v9, finding Codex v8-1): a recovery pacing that FAILS can never
    end a quarantine, never abandon the retained group and never mask the
    original exception — and it can never become a CPU spin.

    The gate, the supervisor and the retained worker group are the production
    ones (a real worker plus a real SIGTERM-ignoring descendant); only the
    SLEEPER is injected — which is exactly the seam the finding is about.
    """

    class PacingBoom(BaseException):
        """The sleeper failure that used to escape ``guarded_release``."""

    #: two complete quarantine rounds before the release is provable: the first
    #: pacing therefore happens INSIDE the quarantine, where v8's unprotected
    #: ``sleep`` used to kill HOME.
    BLIND_ROUNDS = 2

    def _armed(self, raw):
        pidfile = pathlib.Path(raw) / "child.pid"
        supervisor, calls, spawned = blind_then_real_supervisor(
            pidfile, blind_calls=self.BLIND_ROUNDS * session.SHUTDOWN_RELEASE_ATTEMPTS)
        supervisor.request(93)
        worker = supervisor.group.proc
        child_pid = wait_pidfile(pidfile)
        time.sleep(0.3)                            # le descendant installe SIG_IGN
        return supervisor, spawned, worker, child_pid

    def test_82_a_sleeper_failing_on_the_first_pacing_keeps_the_authority_and_the_original_exception(self):
        with tempfile.TemporaryDirectory() as raw:
            supervisor, spawned, worker, child_pid = self._armed(raw)
            events, records, paces, actions = [], [], [], []
            failure = RuntimeError("panne d'origine injectee")

            def sleeper(seconds):
                paces.append(seconds)
                if len(paces) == 1:                # ← "au PREMIER pacing"
                    raise PacingIsFailClosed.PacingBoom("le reveil est injoignable")

            def logger(event, **fields):
                events.append(event)
                records.append((event, fields))

            try:
                with self.assertRaises(RuntimeError) as caught:
                    released = session.guarded_release(
                        supervisor, lambda reason: drain_via_shutdown(supervisor), logger,
                        reason="EXCEPTION", sleep=sleeper, recovery_pause_s=0.01,
                        exception=failure)
                    if released:                   # the controller's own leave path
                        actions.append(1)

                self.assertIs(caught.exception, failure,
                              "l'exception d'origine est relevee TELLE QUELLE, jamais masquee")
                self.assertEqual(actions, [],
                                 "aucune sortie: la sortie reste gatée sur la preuve")
                self.assertEqual(len(spawned), 1, "aucun nouveau worker pendant la quarantaine")
                self.assertEqual([fields.get("pacing_tier") for event, fields in records
                                  if event == "HOME_PACING_UNAVAILABLE"], ["SEAM"],
                                 "la defaillance du reveil est absorvee ET journalisee")
                self.assertIn("HOME_GUARDED_RECOVERY", events)
                self.assertIn("HOME_AUTHORITY_RELEASE_PROVEN", events)
                self.assertIn("HOME_SESSION_EXCEPTION_RERAISED", events)
                self.assertLess(events.index("HOME_PACING_UNAVAILABLE"),
                                events.index("HOME_AUTHORITY_RELEASE_PROVEN"),
                                "la quarantine CONTINUE apres le reveil defaillant")
                self.assertLess(events.index("HOME_AUTHORITY_RELEASE_PROVEN"),
                                events.index("HOME_SESSION_EXCEPTION_RERAISED"),
                                "l'exception n'est relevee qu'APRES la preuve")
                self.assertGreaterEqual(len(paces), 2,
                                        "le pacing est REPRIS apres la panne, jamais abandonne")
                self.assertEqual(len(paces), events.count("HOME_GUARDED_RECOVERY"),
                                 "exactement un pacing par tour de quarantaine: aucun spin")
                self.assertEqual(supervisor.cleanup_state, session.CLEANUP_PROVEN)
                self.assertTrue(wait_dead(worker.pid))
                self.assertTrue(wait_dead(child_pid),
                                "le descendant resistant est nettoye par la preuve")
            finally:
                cleanup_group(worker, child_pid, *spawned)

    def test_83_a_sleeper_that_never_works_still_paces_and_still_proves_the_release(self):
        """The fallback is NOT a spin: the interval is really spent, on the
        gate's OWN blocking clock-wait, and the quarantine goes on to the proof."""
        interval = 0.05
        with tempfile.TemporaryDirectory() as raw:
            supervisor, spawned, worker, child_pid = self._armed(raw)
            events, records, paces, actions = [], [], [], []
            failure = RuntimeError("panne d'origine injectee")

            def sleeper(seconds):
                paces.append(seconds)
                raise PacingIsFailClosed.PacingBoom("le reveil est injoignable")

            def logger(event, **fields):
                events.append(event)
                records.append((event, fields))

            try:
                started = time.monotonic()
                with self.assertRaises(RuntimeError) as caught:
                    released = session.guarded_release(
                        supervisor, lambda reason: drain_via_shutdown(supervisor), logger,
                        reason="EXCEPTION", sleep=sleeper, recovery_pause_s=interval,
                        exception=failure)
                    if released:
                        actions.append(1)
                elapsed = time.monotonic() - started

                self.assertIs(caught.exception, failure)
                self.assertEqual(actions, [], "aucune sortie pendant la quarantaine")
                self.assertEqual([fields.get("pacing_tier") for event, fields in records
                                  if event == "HOME_PACING_UNAVAILABLE"],
                                 ["SEAM"] * len(paces),
                                 "CHAQUE pacing defaillant est absorbe et journalise")
                self.assertGreaterEqual(len(paces), 2)
                self.assertEqual(len(paces), events.count("HOME_GUARDED_RECOVERY"),
                                 "un pacing par tour: aucun tour surnumeraire, aucun spin")
                self.assertGreaterEqual(elapsed, interval * len(paces),
                                        "la temporisation est EFFECTIVE (le fallback BLOQUE)")
                self.assertIn("HOME_AUTHORITY_RELEASE_PROVEN", events)
                self.assertEqual(supervisor.cleanup_state, session.CLEANUP_PROVEN)
                self.assertTrue(wait_dead(worker.pid))
                self.assertTrue(wait_dead(child_pid))
            finally:
                cleanup_group(worker, child_pid, *spawned)

    def test_87_a_planned_departure_is_never_unguarded_by_a_failing_sleeper(self):
        """EXECUTED (v9, finding Codex v8-1, third clause): with NO original
        exception — a PLANNED departure — a failing sleeper must not produce a
        premature unguarded exit either: the ONLY way out stays the PROOF."""
        with tempfile.TemporaryDirectory() as raw:
            supervisor, spawned, worker, child_pid = self._armed(raw)
            events, paces, actions = [], [], []
            try:
                def sleeper(seconds):
                    paces.append(seconds)
                    raise PacingIsFailClosed.PacingBoom("le reveil est injoignable")

                released = session.guarded_release(
                    supervisor, lambda reason: drain_via_shutdown(supervisor),
                    lambda event, **fields: events.append(event),
                    reason="STOP_SIGNAL", sleep=sleeper, recovery_pause_s=0.01)

                if released:                           # the controller's own leave path
                    actions.append(1)
                    events.append("CALLER_EXIT")

                self.assertTrue(released, "la porte aboutit a la PREUVE, jamais a une sortie non gardee")
                self.assertEqual(actions, [1], "exactement une sortie, et seulement apres la preuve")
                self.assertLess(events.index("HOME_AUTHORITY_RELEASE_PROVEN"),
                                events.index("CALLER_EXIT"),
                                "la sortie planifiee vient APRES la preuve, jamais d'un pacing defaillant")
                self.assertGreaterEqual(len(paces), 2)
                self.assertEqual(len(paces), events.count("HOME_GUARDED_RECOVERY"),
                                 "un pacing par tour: aucun spin")
                self.assertEqual(supervisor.cleanup_state, session.CLEANUP_PROVEN)
                self.assertTrue(wait_dead(worker.pid))
                self.assertTrue(wait_dead(child_pid))
            finally:
                cleanup_group(worker, child_pid, *spawned)


    # ── v10 (blocker Codex v9-1) : le pacing est ABSOLUMENT non-escaping ET
    #    non-spinning.  Chaque sous-operation potentiellement faillible — nom de
    #    type, horloge monotone, primitives d'attente — est absorbe ; aucune ne
    #    peut rendre la main a la boucle de recovery avant l'intervalle.

    class ClockBoom(BaseException):
        """A clock failure of the class that used to escape ``_pace``."""

    def _failing_paces(self, paces):
        """A sleeper that fails on EVERY call — the seam is broken for good."""

        def sleeper(seconds):
            paces.append(seconds)
            raise PacingIsFailClosed.PacingBoom("le reveil est injoignable")
        return sleeper

    class RetainedDrain:
        """A retained group the drain cannot release for ``blind`` rounds.

        Deliberately INSTANT: the elapsed time of the test must be the PACING,
        never the drain — otherwise a fast drain could hide a spinning pacing.
        """

        group = "<retained worker group>"

        def __init__(self, blind):
            self.blind = blind
            self.calls = 0

        def drain(self, reason):
            self.calls += 1
            return self.calls > self.blind

    def test_88_a_clock_wait_failing_every_time_cannot_turn_the_quarantine_into_a_spin(self):
        """RED v9 — Codex v9-1.  v9's CLOCK_WAIT tier answered ``return`` as soon
        as its own wait failed, so every quarantine round came back instantly and
        the gate spun (Codex: 10 000 nominal 10 ms rounds in 8 ms).  Here BOTH the
        seam and the clock-wait are broken for the whole quarantine: every round
        must still spend its interval, and the proof must still be reached.
        """
        interval = 0.05
        blind = 3
        events, records, paces, actions = [], [], [], []
        failure = RuntimeError("panne d'origine injectee")
        supervisor = PacingIsFailClosed.RetainedDrain(blind)

        def broken_wait(timeout=None):
            raise PacingIsFailClosed.PacingBoom("l'horloge de la porte est injoignable")

        def logger(event, **fields):
            events.append(event)
            records.append((event, fields))

        with mock.patch.object(session, "_PACE_CLOCK_WAIT", broken_wait):
            started = time.monotonic()
            with self.assertRaises(RuntimeError) as caught:
                released = session.guarded_release(
                    supervisor, supervisor.drain, logger,
                    reason="EXCEPTION", sleep=self._failing_paces(paces),
                    recovery_pause_s=interval, exception=failure)
                if released:
                    actions.append(1)
            elapsed = time.monotonic() - started

        self.assertIs(caught.exception, failure,
                      "l'exception d'origine est relevee TELLE QUELLE")
        self.assertEqual(actions, [], "aucune sortie pendant la quarantaine")
        self.assertEqual(len(paces), blind, "un pacing par tour de quarantaine, pas plus")
        self.assertEqual(len(paces), events.count("HOME_GUARDED_RECOVERY"),
                         "un pacing par tour: aucun tour surnumeraire")
        self.assertEqual(
            [fields.get("pacing_tier") for event, fields in records
             if event == "HOME_PACING_UNAVAILABLE"],
            ["SEAM", "CLOCK_WAIT"] * len(paces),
            "chaque primitive defaillante est absorvee ET nommee")
        self.assertGreaterEqual(elapsed, interval * len(paces),
                                "l'intervalle est REELLEMENT depense a chaque tour: "
                                "aucun busy-loop, meme quand la clock-wait leve")
        self.assertGreaterEqual(elapsed / len(paces), interval,
                                "chaque tour coute AU MOINS son intervalle (pas 8 ms pour 100 s)")
        self.assertIn("HOME_AUTHORITY_RELEASE_PROVEN", events)
        self.assertLess(events.index("HOME_AUTHORITY_RELEASE_PROVEN"),
                        events.index("HOME_SESSION_EXCEPTION_RERAISED"))

    def test_894_a_sleeper_raising_an_unnamable_exception_cannot_escape_the_quarantine(self):
        """RED v9 — Codex v9-1 (first clause) + v9-2 in the PACING path.

        The sleeper's own failure has a hostile metaclass, so the SEAM branch's
        ``type(exc).__name__`` — evaluated as an argument of the gate's logger —
        used to raise out of ``_pace`` and out of ``guarded_release``, releasing
        the authority before any proof.  HOME/guard must stay alive, keep the
        lock, keep the group retained, and re-raise the ORIGINAL instance.
        """
        interval = 0.05
        blind = 2
        supervisor = PacingIsFailClosed.RetainedDrain(blind)
        events, records, paces, actions = [], [], [], []
        failure = RuntimeError("panne d'origine injectee")

        def sleeper(seconds):
            paces.append(seconds)
            raise IndescribableExceptionIsQuarantined.Hostile()

        def logger(event, **fields):
            events.append(event)
            records.append((event, fields))

        started = time.monotonic()
        with self.assertRaises(RuntimeError) as caught:
            released = session.guarded_release(
                supervisor, supervisor.drain, logger,
                reason="EXCEPTION", sleep=sleeper, recovery_pause_s=interval,
                exception=failure)
            if released:
                actions.append(1)
        elapsed = time.monotonic() - started

        self.assertIs(caught.exception, failure,
                      "l'instance d'origine est relevee TELLE QUELLE")
        self.assertEqual(actions, [], "aucune sortie avant la preuve")
        self.assertEqual(len(paces), blind, "la quarantaine continue malgre le reveil hostile")
        self.assertEqual(
            [fields.get("exception_type") for event, fields in records
             if event == "HOME_PACING_UNAVAILABLE"],
            ["unknown-type"] * len(paces),
            "le nom du reveil vient d'une garde BaseException")
        self.assertGreaterEqual(elapsed, interval * len(paces),
                                "le pacing BLOQUE malgre le reveil hostile")
        self.assertIn("HOME_AUTHORITY_RELEASE_PROVEN", events)
        self.assertLess(events.index("HOME_AUTHORITY_RELEASE_PROVEN"),
                        events.index("HOME_SESSION_EXCEPTION_RERAISED"))


    # ── v11 (blocker Codex v10-1) : le waiter NON MESURABLE n'est jamais un
    #    intervalle consomme.  Meme combinaison de pannes que le blocker, mais
    #    sur le VRAI groupe retenu (worker reel + descendant SIGTERM-ignorant)
    #    et le VRAI drain : le pacing doit etre porte par la primitive
    #    INDEPENDANTE, et l'autorite rester retenue jusque la preuve.

    def test_100_an_unmeasurable_waiter_never_ends_the_pacing_of_a_retained_group(self):
        """RED v10 — reveil defaillant + horloge cassee + clock-wait rendue
        INSTANTANEMENT sans lever : v10 lisait ce waiter non mesurable comme un
        intervalle consomme, n'atteignait jamais ``select`` et rendait la boucle
        de recovery non pacee.  Sur le VRAI groupe retenu, l'intervalle doit etre
        depense sur la primitive INDEPENDANTE, et l'autorite rester retenue.
        """
        interval = 0.05
        with tempfile.TemporaryDirectory() as raw:
            supervisor, spawned, worker, child_pid = self._armed(raw)
            events, records, actions = [], [], []
            selects = {"n": 0}
            failure = RuntimeError("panne d'origine injectee")
            real_select = session._PACE_SELECT

            def counting_select(*args, **kwargs):
                selects["n"] += 1
                return real_select(*args, **kwargs)

            def instant_wait(timeout=None):
                return None                    # ← retour INSTANTANE, sans lever

            def raising_clock():
                raise PacingIsFailClosed.ClockBoom("l'horloge du pacing est injoignable")

            def logger(event, **fields):
                events.append(event)
                records.append((event, fields))

            try:
                with mock.patch.object(session, "_PACE_CLOCK", raising_clock), \
                        mock.patch.object(session, "_PACE_CLOCK_WAIT", instant_wait), \
                        mock.patch.object(session, "_PACE_SELECT", counting_select):
                    started = time.monotonic()
                    with self.assertRaises(RuntimeError) as caught:
                        released = session.guarded_release(
                            supervisor, lambda reason: drain_via_shutdown(supervisor), logger,
                            reason="EXCEPTION", sleep=self._failing_paces([]),
                            recovery_pause_s=interval, exception=failure)
                        if released:
                            actions.append(1)
                    elapsed = time.monotonic() - started

                rounds = events.count("HOME_GUARDED_RECOVERY")
                self.assertIs(caught.exception, failure,
                              "l'exception d'origine est relevee TELLE QUELLE")
                self.assertEqual(actions, [], "aucune sortie avant la preuve")
                self.assertEqual(len(spawned), 1, "aucun nouveau worker pendant la quarantaine")
                self.assertGreaterEqual(rounds, self.BLIND_ROUNDS)
                self.assertGreaterEqual(selects["n"], rounds,
                                        "la primitive INDEPENDANTE porte le pacing a CHAQUE "
                                        "tour: le waiter non mesurable est REFUSE")
                self.assertGreaterEqual(elapsed, interval * rounds,
                                        "l'intervalle est REELLEMENT depense, jamais 1e-05 s "
                                        "pour 0.05 s exiges: le waiter non verifiable n'est "
                                        "pas compte comme consomme")
                self.assertEqual([fields.get("pacing_reason") for event, fields in records
                                  if event == "HOME_PACING_UNVERIFIED"],
                                 ["UNDERSPENT"] * rounds,
                                 "le waiter rendu instantanement est journalise NON PROUVE")
                self.assertNotIn("HOME_PACING_HOLD", events,
                                 "une preuve a ete atteinte: le hold n'est pas le chemin")
                self.assertIn("HOME_AUTHORITY_RELEASE_PROVEN", events)
                self.assertEqual(supervisor.cleanup_state, session.CLEANUP_PROVEN)
                self.assertTrue(wait_dead(worker.pid))
                self.assertTrue(wait_dead(child_pid),
                                "le descendant resistant est nettoye par la preuve")
            finally:
                cleanup_group(worker, child_pid, *spawned)


class PacingClockOutageIsContained(unittest.TestCase):
    """EXECUTED (v10, blocker Codex v9-1, clock + planned-departure clauses).

    ``time.monotonic`` is broken for the ENGINE module only, in a THROWAWAY child
    process.  That is exactly the failure Codex named: v9 evaluated
    ``time.monotonic()`` OUTSIDE any guard, so the clock raised out of ``_pace``
    and out of ``guarded_release`` — the caller received a clock error instead of
    its original outcome, before any proof.

    A child process isolates the fault honestly: the same patch inside the suite
    would also break the SUPERVISOR's internal clock (a different, unrelated
    contract), and a held quarantine cannot be observed in-process without
    leaking a thread or hanging the run.
    """

    SCRIPT = textwrap.dedent('''
        import importlib.util, pathlib, sys, time
        spec = importlib.util.spec_from_file_location("clock_outage_engine", pathlib.Path(sys.argv[1]))
        engine = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(engine)
        mode = sys.argv[2]

        class Broken(BaseException):
            """The monotonic clock is unreachable."""

        class ClockModule:
            """The engine's OWN ``time`` name, with a ``monotonic`` that RAISES."""

            def __getattr__(self, name):
                if name == "monotonic":
                    raise Broken("monotonic is broken")
                return getattr(time, name)

        engine.time = ClockModule()
        if mode == "complete":
            # ... and the gate's own bounded clock-wait is gone too: a COMPLETE
            # outage of every clock-driven primitive.
            def broken_wait(timeout=None):
                raise Broken("clock-wait is broken")
            engine._PACE_CLOCK_WAIT = broken_wait

        class Retained:
            """A group the drain cannot release for two rounds."""

            group = "<retained group>"

            def __init__(self):
                self.calls = 0

            def drain(self, reason):
                self.calls += 1
                return self.calls > 2

        def failing_sleeper(seconds):
            # The seam fails, so the pacing reaches its OWN clock — the exact
            # path where v9 evaluated ``time.monotonic()`` outside any guard.
            raise Broken("seam is broken")

        supervisor = Retained()
        events = []
        started = time.monotonic()
        released = engine.guarded_release(
            supervisor, supervisor.drain,
            lambda event, **fields: events.append(event),
            reason="STOP_SIGNAL", sleep=failing_sleeper, recovery_pause_s=0.05)
        elapsed = time.monotonic() - started
        print("RESULT", released, len(events), round(elapsed, 3),
              events.count("HOME_AUTHORITY_RELEASE_PROVEN"), flush=True)
    ''')

    def _outage(self, mode):
        script = pathlib.Path(tempfile.mkdtemp(dir=tempfile.gettempdir())) / "clock_probe.py"
        script.write_text(PacingClockOutageIsContained.SCRIPT, encoding="utf-8")
        child = subprocess.Popen(
            [sys.executable, str(script), str(PAYLOAD / "openhtpc-session-engine.py"), mode],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            out, err = child.communicate(timeout=120)
        finally:
            if child.poll() is None:
                child.kill()
                child.communicate(timeout=10)
            script.unlink(missing_ok=True)
            script.parent.rmdir()
        return child.returncode, out.decode("utf-8", "replace"), err.decode("utf-8", "replace")

    def _assert_contained(self, mode):
        returncode, out, err = self._outage(mode)
        self.assertEqual(returncode, 0,
                         f"la panne d'horloge ({mode}) s'est ECHAPPEE du pacing: {err[-800:]}")
        self.assertNotIn("Traceback", err, "aucune sortie non gardee hors de la porte")
        self.assertRegex(out.strip(), r"^RESULT True [0-9]+ [0-9.]+ 1$",
                         "la porte aboutit a la PREUVE, apres les tours de quarantaine")
        released, events, elapsed, proofs = out.split()[1:5]
        self.assertEqual(released, "True")
        self.assertEqual(int(proofs), 1, "exactement une preuve de liberation")
        self.assertGreaterEqual(float(elapsed), 0.09,
                                "les DEUX tours depensent leur intervalle: aucun busy-loop")

    def test_89_a_broken_monotonic_clock_cannot_escape_the_pacing(self):
        """RED v9 — the clock raises where v9 computed its deadline unguarded."""
        self._assert_contained("clock")

    def test_893_a_planned_departure_survives_a_complete_pacing_outage(self):
        """RED v9 — ``exception=None`` (planned departure) + EVERY clock primitive
        broken: the gate must still leave ONLY through the proof."""
        self._assert_contained("complete")


class PacingCannotReturnToTheLoop(unittest.TestCase):
    """EXECUTED (v10, blocker Codex v9-1, last resort): when EVERY bounded pacing
    primitive is broken, the gate HOLDs instead of returning to the recovery
    loop.  Proved on the real payload module in a THROWAWAY child process — a
    held quarantine never returns, so it cannot be observed in-process without
    leaking a thread or hanging the suite.
    """

    HOLD_SCRIPT = textwrap.dedent('''
        import importlib.util, pathlib, sys
        spec = importlib.util.spec_from_file_location("pace_hold_engine", pathlib.Path(sys.argv[1]))
        engine = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(engine)

        class Broken(BaseException):
            """Every bounded pacing primitive is unreachable."""

        def broken(*args, **kwargs):
            raise Broken("primitive injoignable")

        engine._PACE_CLOCK_WAIT = broken
        engine._PACE_SELECT = broken
        engine._PACE_CLOCK = broken
        engine._pace(lambda seconds: None, 0.05, log=lambda *a, **k: None, rounds=1)
        print("RETURNED-TO-THE-LOOP", flush=True)
    ''')

    def test_90_a_gate_whose_pacing_primitives_are_all_broken_holds_and_never_returns(self):
        script = pathlib.Path(tempfile.mkdtemp(dir=tempfile.gettempdir())) / "hold_probe.py"
        script.write_text(PacingCannotReturnToTheLoop.HOLD_SCRIPT, encoding="utf-8")
        child = subprocess.Popen([sys.executable, str(script), str(PAYLOAD / "openhtpc-session-engine.py")],
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            time.sleep(1.5)
            self.assertIsNone(child.poll(),
                              "le pacing est RETENU (hold conservateur): il ne rend pas la main "
                              "a la boucle de recovery quand toutes ses primitives sont cassees")
            child.kill()
            out, err = child.communicate(timeout=10)
            self.assertNotIn(b"RETURNED-TO-THE-LOOP", out,
                             "aucun retour instantane vers la boucle")
        finally:
            if child.poll() is None:
                child.kill()
                child.communicate(timeout=10)
            script.unlink(missing_ok=True)
            script.parent.rmdir()


class PacingRequiresAProof(unittest.TestCase):
    """EXECUTED (v11, blocker Codex v10-1): a recovery interval counts as spent
    only when a MEASUREMENT proves it — and the measurement may not be taken
    with the very name an actor can fault.

    RED v10, MEASURED on the v10 payload (see the V11 report):

    * clock broken + a clock-wait that returns INSTANTLY without raising:
      ``_pace`` came back after 1e-05 s for the 0.05 s it owed, and ``select``
      was NEVER called — the unverifiable waiter ended the pacing;
    * a waiter that consumed 90 % (0.045 s of 0.05) and one that consumed 99 %
      were both ACCEPTED as a spent interval, ``select`` never called;
    * with no clock answering at all, the gate returned at once.

    Every case below is red on v10 and green on v11.  The tolerance left in the
    accounting is the clock's own resolution (1e-6 s), so the assertions here can
    ask for the FULL interval: a deficit a real waiter can produce is orders of
    magnitude above it, and the remainder must go to the INDEPENDENT primitive.
    """

    class ClockBoom(BaseException):
        """A clock failure of the class that used to escape the pacing."""

    INTERVAL = 0.05

    def _counted_select(self, calls):
        """The gate's INDEPENDENT primitive, counted around the real syscall."""
        real_select = session._PACE_SELECT

        def counting_select(*args, **kwargs):
            calls["select"] += 1
            return real_select(*args, **kwargs)
        return counting_select

    @staticmethod
    def _raising_sleeper():
        """A recovery sleeper that fails on EVERY call."""
        def sleeper(seconds):
            raise PacingRequiresAProof.ClockBoom("le reveil est injoignable")
        return sleeper

    @staticmethod
    def _raising_clock():
        def clock():
            raise PacingRequiresAProof.ClockBoom("l'horloge du pacing est injoignable")
        return clock

    def test_95_an_unmeasurable_clock_wait_never_counts_as_a_spent_interval(self):
        """RED v10 (1e-05 s spent, ``select`` = 0).  A waiter that returns
        instantly WITHOUT raising, while the clock is unavailable, cannot be
        measured: it must never be read as a spent interval.  The gate falls
        through to its INDEPENDENT bounded primitive and spends the interval."""
        calls = {"select": 0}
        events, records = [], []

        def instant_wait(timeout=None):
            return None                        # ← returns at once, no exception

        with mock.patch.multiple(session, _PACE_CLOCK=self._raising_clock(),
                                 _PACE_CLOCK_WAIT=instant_wait,
                                 _PACE_SELECT=self._counted_select(calls)):
            started = time.monotonic()
            session._pace(self._raising_sleeper(), self.INTERVAL,
                          log=lambda event, **fields: (events.append(event),
                                                       records.append((event, fields))),
                          rounds=1)
            elapsed = time.monotonic() - started

        self.assertGreaterEqual(calls["select"], 1,
                                "la primitive INDEPENDANTE est atteinte: un waiter non "
                                "mesurable n'est JAMAIS compte comme intervalle consomme")
        self.assertGreaterEqual(elapsed, self.INTERVAL,
                                "l'intervalle COMPLET est depense avant de rendre la main "
                                "(v10: 1e-05 s pour les 0.05 s dus)")
        self.assertNotIn("HOME_PACING_HOLD", events,
                         "une PREUVE a ete atteinte: le hold n'est pas le chemin")
        self.assertEqual(
            [(fields.get("pacing_tier"), fields.get("pacing_reason"))
             for event, fields in records if event == "HOME_PACING_UNVERIFIED"],
            [("CLOCK_WAIT", "UNDERSPENT")],
            "le waiter rendu instantanement est journalise NON PROUVE, nomme, une fois")

    def _ratio(self, ratio):
        calls = {"select": 0}
        events, records = [], []

        def partial_wait(timeout=None):
            time.sleep(timeout * ratio)        # sous-consommation EXACTE

        with mock.patch.multiple(session, _PACE_CLOCK_WAIT=partial_wait,
                                 _PACE_SELECT=self._counted_select(calls)):
            started = time.monotonic()
            session._pace(self._raising_sleeper(), self.INTERVAL,
                          log=lambda event, **fields: (events.append(event),
                                                       records.append((event, fields))),
                          rounds=1)
            elapsed = time.monotonic() - started
        return calls["select"], elapsed, events, records

    def test_96_a_waiter_that_consumed_ninety_percent_is_not_a_proof(self):
        """RED v10 (0.045 s of 0.05 ACCEPTED, ``select`` = 0): the old 0.9 floor
        blessed a 10 % deficit.  The remainder must be spent on the gate's own
        INDEPENDENT primitive — never written off."""
        selects, elapsed, events, records = self._ratio(0.90)

        self.assertGreaterEqual(selects, 1,
                                "un waiter a 90 % n'est PAS une preuve: le reliquat part "
                                "sur la primitive INDEPENDANTE")
        self.assertGreaterEqual(elapsed, self.INTERVAL - 1e-4,
                                "l'intervalle est consomme EN ENTIER, pas a 90 %")
        unverified = [fields for event, fields in records
                      if event == "HOME_PACING_UNVERIFIED"]
        self.assertEqual([fields.get("pacing_tier") for fields in unverified], ["CLOCK_WAIT"])
        self.assertEqual([fields.get("pacing_reason") for fields in unverified], ["UNDERSPENT"])
        self.assertGreater(unverified[0].get("remaining_s"), 0.0,
                           "le deficit REFUSE est chiffre dans le journal")
        self.assertNotIn("HOME_PACING_HOLD", events)

    def test_97_a_waiter_that_consumed_ninety_nine_percent_is_not_a_proof_either(self):
        """RED v10 (0.0495 s of 0.05 ACCEPTED, ``select`` = 0).  Lowering the
        floor from 90 % to 99 % would only have blessed a smaller deficit: the
        accounting demands the WHOLE interval, whatever the remainder costs."""
        selects, elapsed, events, records = self._ratio(0.99)

        self.assertGreaterEqual(selects, 1,
                                "un waiter a 99 % n'est pas une preuve non plus")
        self.assertGreaterEqual(elapsed, self.INTERVAL - 1e-4,
                                "le reliquat est consomme, jamais tolere")
        self.assertEqual([fields.get("pacing_reason") for event, fields in records
                          if event == "HOME_PACING_UNVERIFIED"], ["UNDERSPENT"])
        self.assertNotIn("HOME_PACING_HOLD", events)

    def test_98_a_planned_departure_under_the_same_outage_leaves_only_after_the_pacing(self):
        """RED v10 — ``exception=None`` (planned departure) + the blocker's whole
        combination: v10 handed the recovery loop back unpaced, with ``select``
        never called.  Every round must still cost its interval, spent on the
        INDEPENDENT primitive, and the ONLY leave is the proof."""
        interval = self.INTERVAL
        blind = 2
        calls = {"select": 0}
        events = []

        def instant_wait(timeout=None):
            return None

        supervisor = PacingIsFailClosed.RetainedDrain(blind)

        with mock.patch.multiple(session, _PACE_CLOCK=self._raising_clock(),
                                 _PACE_CLOCK_WAIT=instant_wait,
                                 _PACE_SELECT=self._counted_select(calls)):
            started = time.monotonic()
            released = session.guarded_release(
                supervisor, supervisor.drain, lambda event, **fields: events.append(event),
                reason="STOP_SIGNAL", sleep=self._raising_sleeper(),
                recovery_pause_s=interval)
            elapsed = time.monotonic() - started

        rounds = events.count("HOME_GUARDED_RECOVERY")
        self.assertTrue(released, "la porte aboutit a la PREUVE, jamais a une sortie non gardee")
        self.assertEqual(rounds, blind, "un pacing par tour de quarantaine, pas plus")
        self.assertGreaterEqual(calls["select"], rounds,
                                "chaque tour est porte par la primitive INDEPENDANTE")
        self.assertGreaterEqual(elapsed, interval * rounds,
                                "chaque tour coute AU MOINS son intervalle: aucune sortie "
                                "avant un pacing reellement consomme")
        self.assertEqual(events[-1], "HOME_AUTHORITY_RELEASE_PROVEN")
        self.assertNotIn("HOME_PACING_HOLD", events)

    HOLD_SCRIPT = textwrap.dedent('''
        import importlib.util, pathlib, sys
        spec = importlib.util.spec_from_file_location("pace_unproven_engine", pathlib.Path(sys.argv[1]))
        engine = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(engine)

        class Broken(BaseException):
            """No clock answers at all, and every bounded waiter is unusable."""

        def broken_clock():
            raise Broken("aucune horloge")

        def instant_wait(timeout=None):
            return None                        # ← returns at once, without raising

        real_select = engine._PACE_SELECT

        def counting_select(*args, **kwargs):
            print("SELECT-INVOKED", flush=True)
            return real_select(*args, **kwargs)

        engine._PACE_CLOCK = broken_clock
        engine._PACE_CLOCK_ALT = broken_clock
        engine._PACE_CLOCK_WAIT = instant_wait
        engine._PACE_SELECT = counting_select
        engine._pace(lambda seconds: None, 0.05, log=lambda *a, **k: None, rounds=1)
        print("RETURNED-TO-THE-LOOP", flush=True)
    ''')

    def test_99_a_waiter_nobody_can_measure_ends_in_the_conservative_hold(self):
        """RED v10 — with NO clock answering, v10 returned at once and the loop
        ran unpaced.  An interval that cannot be PROVEN may not be returned to
        the recovery loop: the gate tries its independent primitive and then
        HOLDS.  Proved on the real payload module in a THROWAWAY child process —
        a held quarantine never returns, so it cannot be observed in-process
        without hanging the suite."""
        script = pathlib.Path(tempfile.mkdtemp(dir=tempfile.gettempdir())) / "unproven_probe.py"
        script.write_text(PacingRequiresAProof.HOLD_SCRIPT, encoding="utf-8")
        child = subprocess.Popen(
            [sys.executable, str(script), str(PAYLOAD / "openhtpc-session-engine.py")],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            time.sleep(1.5)
            out = b""
            self.assertIsNone(child.poll(),
                              "un intervalle NON PROUVABLE est TENU (hold conservateur): "
                              "le pacing ne rend pas la main a la boucle de recovery")
            child.kill()
            out, err = child.communicate(timeout=10)
            self.assertNotIn(b"RETURNED-TO-THE-LOOP", out,
                             "aucun retour instantane vers la boucle")
            self.assertIn(b"SELECT-INVOKED", out,
                          "la primitive INDEPENDANTE a ete tentee AVANT le hold")
            self.assertNotIn(b"Traceback", err)
        finally:
            if child.poll() is None:
                child.kill()
                child.communicate(timeout=10)
            script.unlink(missing_ok=True)
            script.parent.rmdir()


class IndescribableExceptionIsQuarantined(unittest.TestCase):
    """EXECUTED (v9, finding Codex v8-2): an exception whose ``__str__`` AND
    ``__repr__`` both raise is STILL quarantined, keeps the authority, and is
    re-raised as the very SAME instance."""

    class Unprintable(BaseException):
        def __str__(self):
            raise RuntimeError("__str__ is broken")

        def __repr__(self):
            raise RuntimeError("__repr__ is broken")

    class _HostileName(type):
        """A metaclass whose ``__name__`` RAISES (blocker Codex v9-2).

        ``type(exc).__name__`` was read UNGUARDED in ``safe_exception_text``, in
        HOME's boundary and in ``guarded_release`` AFTER the proof — so naming the
        exception could replace it.
        """

        @property
        def __name__(cls):
            raise RuntimeError("__name__ is broken")

    class Hostile(BaseException, metaclass=_HostileName):
        """``__str__``, ``__repr__`` AND ``__name__`` all refuse to answer."""

        def __str__(self):
            raise RuntimeError("__str__ is broken")

        def __repr__(self):
            raise RuntimeError("__repr__ is broken")

    @staticmethod
    def _type_name_reads(path):
        """Line numbers where ``type(x).__name__`` is READ in executable code.

        An AST pass, so a docstring that NAMES the pattern is not a finding and a
        real read inside a guarded expression still is.
        """
        tree = ast.parse(pathlib.Path(path).read_text(encoding="utf-8"))
        found = []
        for node in ast.walk(tree):
            if (isinstance(node, ast.Attribute) and node.attr == "__name__"
                    and isinstance(node.value, ast.Call)
                    and isinstance(node.value.func, ast.Name)
                    and node.value.func.id == "type"):
                found.append(node.lineno)
        return found

    def test_91_a_hostile_metaclass_can_neither_mask_the_instance_nor_skip_the_gate(self):
        """RED v9 — Codex v9-2.  ``safe_type_name`` is TOTAL: the class name is
        read inside a ``BaseException`` guard, so a metaclass whose ``__name__``
        raises answers a stable placeholder — and no payload ever reads
        ``type(x).__name__`` outside such a guard again.
        """
        failure = IndescribableExceptionIsQuarantined.Hostile()
        self.assertEqual(session.safe_type_name(failure), "unknown-type")
        self.assertEqual(session.safe_exception_text(failure), "<unknown-type: unprintable>",
                         "le diagnostic d'exception est TOTALEMENT non-levant")
        self.assertEqual(session.safe_repr(failure), "<unrepresentable unknown-type>")

        for path in (PAYLOAD / "openhtpc-session-engine.py", CONTROLLER):
            self.assertEqual(self._type_name_reads(path), [],
                             f"{path.name}: aucun type(...).__name__ non garde")

        with tempfile.TemporaryDirectory() as raw:
            pidfile = pathlib.Path(raw) / "child.pid"
            supervisor, calls, spawned = blind_then_real_supervisor(pidfile)
            worker = child_pid = None
            events, records, actions = [], [], []
            try:
                supervisor.request(93)
                worker = supervisor.group.proc
                child_pid = wait_pidfile(pidfile)
                time.sleep(0.3)

                def logger(event, **fields):
                    events.append(event)
                    records.append((event, fields))

                with self.assertRaises(IndescribableExceptionIsQuarantined.Hostile) as caught:
                    released = session.guarded_release(
                        supervisor, lambda reason: drain_via_shutdown(supervisor), logger,
                        reason="EXCEPTION", sleep=lambda seconds: None,
                        recovery_pause_s=0.01, exception=failure)
                    if released:
                        actions.append(1)

                self.assertIs(caught.exception, failure,
                              "l'instance d'origine est relevee TELLE QUELLE, jamais masquee")
                self.assertEqual(actions, [], "aucune sortie pendant la quarantaine")
                self.assertIn("HOME_AUTHORITY_RELEASE_PROVEN", events)
                self.assertLess(events.index("HOME_AUTHORITY_RELEASE_PROVEN"),
                                events.index("HOME_SESSION_EXCEPTION_RERAISED"))
                reraised = [fields for event, fields in records
                            if event == "HOME_SESSION_EXCEPTION_RERAISED"]
                self.assertEqual([fields.get("exception_type") for fields in reraised],
                                 ["unknown-type"],
                                 "l'evenement de re-raise n'utilise que des diagnostics SAFE")
                self.assertEqual(supervisor.cleanup_state, session.CLEANUP_PROVEN)
                self.assertTrue(wait_dead(worker.pid))
                self.assertTrue(wait_dead(child_pid))
            finally:
                cleanup_group(worker, child_pid, *spawned)

    def test_84_a_broken_str_cannot_skip_the_gate_and_the_same_instance_is_reraised(self):
        failure = IndescribableExceptionIsQuarantined.Unprintable()
        # the helpers are the ONLY way the gate and the controller describe an
        # exception: neither may raise, and both answer a STABLE placeholder.
        self.assertEqual(session.safe_exception_text(failure), "<Unprintable: unprintable>")
        self.assertEqual(session.safe_repr(failure), "<unrepresentable Unprintable>")
        # ... and the controller's exception path is WIRED to them: no raw str().
        controller = CONTROLLER.read_text(encoding="utf-8")
        self.assertIn("engine.safe_exception_text(exc)", controller)
        self.assertNotIn("exception=str(exc)", controller)

        with tempfile.TemporaryDirectory() as raw:
            pidfile = pathlib.Path(raw) / "child.pid"
            supervisor, calls, spawned = blind_then_real_supervisor(pidfile)
            worker = child_pid = None
            events, actions = [], []
            try:
                supervisor.request(93)
                worker = supervisor.group.proc
                child_pid = wait_pidfile(pidfile)
                time.sleep(0.3)

                with self.assertRaises(IndescribableExceptionIsQuarantined.Unprintable) as caught:
                    released = session.guarded_release(
                        supervisor, lambda reason: drain_via_shutdown(supervisor),
                        lambda event, **fields: events.append(event),
                        reason="EXCEPTION", sleep=lambda seconds: None,
                        recovery_pause_s=0.01, exception=failure)
                    if released:
                        actions.append(1)

                self.assertIs(caught.exception, failure,
                              "l'instance d'origine est relevee TELLE QUELLE")
                self.assertEqual(actions, [], "aucune sortie pendant la quarantaine")
                self.assertIn("HOME_GUARDED_RECOVERY", events)
                self.assertIn("HOME_AUTHORITY_RELEASE_PROVEN", events)
                self.assertIn("HOME_SESSION_EXCEPTION_RERAISED", events)
                self.assertLess(events.index("HOME_AUTHORITY_RELEASE_PROVEN"),
                                events.index("HOME_SESSION_EXCEPTION_RERAISED"),
                                "l'exception n'est relevee qu'APRES la preuve")
                self.assertEqual(supervisor.cleanup_state, session.CLEANUP_PROVEN)
                self.assertTrue(wait_dead(worker.pid))
                self.assertTrue(wait_dead(child_pid))
            finally:
                cleanup_group(worker, child_pid, *spawned)


class GateLoggerCannotEscape(unittest.TestCase):
    """EXECUTED (v8): ``guarded_release`` cannot be undone by its own logger.

    ``engine._safe_log`` is the gate's logging seam.  Catching only ``Exception``
    left a logger raising a ``BaseException`` free to escape the gate — returning
    to a caller that had NOT been told the release was proven, i.e. releasing the
    authority without proof.  A logger decides nothing, so it may not decide this
    either.
    """

    class Boom(BaseException):
        """A logger failure of the class that used to slip through."""

    def test_80_a_logger_raising_a_base_exception_neither_escapes_nor_releases_the_authority(self):
        with tempfile.TemporaryDirectory() as raw:
            pidfile = pathlib.Path(raw) / "child.pid"
            supervisor, calls, spawned = blind_then_real_supervisor(pidfile)
            worker = child_pid = None
            seen, actions = [], []
            try:
                supervisor.request(93)
                worker = supervisor.group.proc
                child_pid = wait_pidfile(pidfile)
                time.sleep(0.3)                        # le descendant installe SIG_IGN

                def logger(event, **fields):
                    seen.append(event)
                    raise GateLoggerCannotEscape.Boom("le journal est injoignable")

                released = session.guarded_release(
                    supervisor, lambda reason: drain_via_shutdown(supervisor), logger,
                    reason="FLEX_EXIT", sleep=lambda seconds: None, recovery_pause_s=0.01)
                if released:                           # the controller's own leave path
                    actions.append(1)

                self.assertTrue(released, "la porte doit aboutir: le logger ne decide rien")
                self.assertEqual(actions, [1], "exactement une sortie, apres la preuve")
                self.assertTrue(seen, "le logger a bien ete appele, et a bien leve")
                self.assertEqual(supervisor.cleanup_state, session.CLEANUP_PROVEN)
                self.assertTrue(wait_dead(worker.pid))
                self.assertTrue(wait_dead(child_pid), "le descendant resistant est nettoye")
            finally:
                cleanup_group(worker, child_pid, *spawned)


class HermeticInjectionProvenance(unittest.TestCase):
    """EXECUTED: the hermetic doubles are the payload bytes plus a declared tail."""

    def test_81_the_hermetic_doubles_are_the_payload_bytes_plus_their_declared_tail(self):
        for module, tail in (("openhtpc-session-engine.py", HOME_ENGINE_INJECTION),
                             ("openhtpc-runtime.py", HOME_RUNTIME_INJECTION)):
            payload_bytes = (PAYLOAD / module).read_bytes()
            self.assertTrue(tail.startswith("\n"))       # appended, never interleaved
            self.assertIn("OPENHTPC_TEST_", tail)
            HermeticHome.assert_prefix(payload_bytes, payload_bytes + tail.encode(), module)
            with self.assertRaises(AssertionError):
                HermeticHome.assert_prefix(payload_bytes + b"# payload changed\n",
                                           payload_bytes + tail.encode(), module)
        # the controller itself is used VERBATIM: no injection, no shim
        self.assertNotIn("OPENHTPC_TEST", CONTROLLER.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
