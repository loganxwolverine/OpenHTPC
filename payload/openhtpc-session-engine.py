#!/usr/bin/env python3
"""OPENHTPC Basic session gates and deterministic Flex home generation."""

from __future__ import annotations

import json
import os
import pathlib
import stat
import subprocess
import tempfile
import hashlib
import fcntl
import importlib.util
import importlib.machinery
import re
import select
import shlex
import signal
import sys
import time
import threading
from contextlib import contextmanager

_optical_spec = importlib.util.spec_from_file_location("openhtpc_optical_presentation", pathlib.Path(__file__).with_name("openhtpc-optical.py"))
_optical_model = importlib.util.module_from_spec(_optical_spec); _optical_spec.loader.exec_module(_optical_model)

# ── Regeneration worker budgets (single source of truth) ─────────────────────
# One regeneration worker performs, in one synchronous pass and before it
# publishes flex-v1.ini as its very last act: the System page renders, the
# disc-sheet render (bounded below) and the media-graph rebuild.  The home
# controller's watchdog MUST outlast every one of those steps, otherwise a
# healthy regeneration is killed before it can publish and the menu — including
# the DVD section derived from the canonical optical state — stays on the
# previous optical generation.  Never reintroduce an independent literal in the
# controller: derive its watchdog from these values.
DISC_VIEW_TIMEOUT_S = 12
REGENERATION_WORKER_RESERVE_S = 30
REGENERATION_WORKER_BUDGET_S = DISC_VIEW_TIMEOUT_S + REGENERATION_WORKER_RESERVE_S
REGENERATION_MAX_ATTEMPTS = 3
# REGENERATION_MAX_ATTEMPTS counts EXECUTIONS, not retries: one initial attempt
# plus REGENERATION_MAX_RETRIES retries.  3 therefore means three worker
# processes at most — a fourth execution is a defect, not a margin.
REGENERATION_MAX_RETRIES = REGENERATION_MAX_ATTEMPTS - 1


def regeneration_watchdog_expired(elapsed_s: float, budget_s: float = REGENERATION_WORKER_BUDGET_S) -> bool:
    """True when a live regeneration worker consumed its whole budget."""
    return elapsed_s > budget_s


def regeneration_recovery(outcome: str, executions: int, max_attempts: int = REGENERATION_MAX_ATTEMPTS) -> str:
    """Bounded recovery policy for one failed regeneration attempt.

    ``outcome`` is ``STALLED`` (the watchdog expired) or ``FAILED`` (the worker
    ended without publishing).  ``executions`` is the number of worker processes
    ALREADY started for the current generation, INCLUDING the one that just
    failed: the initial attempt is an execution, not a retry.  ``RETRY`` is
    returned while one more execution still fits in ``max_attempts`` (3 means at
    most 1 initial attempt + 2 retries = 3 workers), then ``FALLBACK`` so the UI
    is handed truthful, generation-matching provenance instead of a silently
    stale menu.  A pending navigation request is never dropped here: the
    successful attempt publishes it.
    """
    if outcome not in {"STALLED", "FAILED"}:
        raise ValueError(f"unknown regeneration outcome: {outcome!r}")
    if int(executions) < 0:
        raise ValueError(f"executions cannot be negative: {executions!r}")
    return "RETRY" if int(executions) < int(max_attempts) else "FALLBACK"


def regeneration_failure_is_stale(failed_generation: int, current_generation: int) -> bool:
    """True when a newer optical generation superseded the failed one.

    An error belonging to generation G must never publish a fallback for a newer
    generation: the newer generation owns the presentation and already has its
    own regeneration request.  A stale failure is dropped — logged, neither
    retried nor published.  Retrying it would ask the engine to publish a
    generation it would refuse anyway, and publishing it would stamp the
    fallback with a generation it does not describe.
    """
    return int(failed_generation or 0) != int(current_generation or 0)


def regeneration_trigger(optical_changed: bool, enrichment_changed: bool, enrichment_running: bool) -> str:
    """Decide what a state change means for the menu regeneration.

    ``OPTICAL``                a real optical transition: always regenerate.
    ``ENRICHMENT``             the metadata signature settled: regenerate once.
    ``SUPPRESSED_ENRICHMENT``  the metadata signature changed WHILE the enricher
                               is still running.  Those are intermediate writes
                               — the TMDb cache is rewritten as the lookup
                               progresses — not a new presentation.  Regenerating
                               now spawns a worker the next write kills a second
                               later; the enricher's completion is the one event
                               that triggers the authoritative regeneration.
    ``NONE``                   nothing that affects the menu changed.
    """
    if optical_changed:
        return "OPTICAL"
    if not enrichment_changed:
        return "NONE"
    return "SUPPRESSED_ENRICHMENT" if enrichment_running else "ENRICHMENT"


PROC_ROOT = pathlib.Path("/proc")

# ── Group liveness: three answers, never two ─────────────────────────────────
# A helper that can only answer "alive" or "gone" has to invent an answer when
# /proc cannot be read, and both inventions are lies: "gone" hides a surviving
# descendant, and "alive" reports a group that holds nothing but unreaped
# zombies as if it were running — which is exactly how v3 produced a false
# GROUP_STILL_PRESENT.  The probes answer in three states for that reason, and
# the termination helper decides, explicitly, what an unproven state means.
LIVENESS_GONE = "GONE"
LIVENESS_LIVE = "LIVE"
LIVENESS_UNKNOWN = "UNKNOWN"

# What the kernel said when it was asked to signal a group.
SIGNAL_OK = "OK"
SIGNAL_GONE = "GONE"            # ESRCH: no such group
SIGNAL_NOT_OURS = "NOT_OURS"    # EPERM: the group exists and is not ours to signal
SIGNAL_FAILED = "FAILED"        # anything else: reported, never masked.  (The
#                                 OUTCOME for that case is the separate
#                                 string "SIGNAL_ERROR" returned by the helper.)

# How long the supervisor waits for an exited worker to be collected once its
# group has been released.  A leader the probes saw as exited is collected at
# once; the bound is only there so a probe that was read at the wrong instant
# cannot stall the controller.
EXIT_REAP_TIMEOUT_S = 1.0

# Outcomes of a group release that leave the previous worker's group unproven.
# A retry renders the SAME generation, so it is not started on one of these: two
# writers for one presentation is the failure this whole tranche exists to stop.
#
# NO_GROUP, NO_GROUP_UNPROVEN and GROUP_NOT_OURS belong here (finding A of the v6
# review), not among the releases: none of them proves that every descendant of
# the worker has stopped writing.  A refusal and a missing group are the ABSENCE
# of a proof, and the absence of a proof may never be recorded as a release.
RELEASE_UNPROVEN = ("GROUP_STILL_PRESENT", "GROUP_UNKNOWN", "SIGNAL_ERROR", "UNREAPED",
                    "NO_GROUP", "NO_GROUP_UNPROVEN", "GROUP_NOT_OURS")

# The complement: outcomes that PROVE the worker's group (and with it every
# descendant) is gone.  Only these may free the ownership record, and only these
# let the leader be collected.
RELEASE_PROVEN = ("NO_WORKER", "ALREADY_EXITED", "TERMINATED", "KILLED")

# v6, finding A.  The outcome a SUPERVISED worker gets when the process group —
# the only handle that reaches its descendants — is not proven ours.  It is a
# refusal, never a cleaning: the single-process path is not run, the leader is
# not polled, not waited on and not reaped, and no signal is aimed at its pid
# alone.  Left unreaped, its pid (hence its pgid) cannot be recycled, so a later,
# better-informed attempt stays possible instead of becoming a guess.
NO_GROUP_UNPROVEN = "NO_GROUP_UNPROVEN"

# v6, finding D.  What a RETAINED generation is waiting for.  ONE slot, explicit
# and unique — never a queue, because a newer generation owns the presentation.
PENDING_SUCCESS = "SUCCESS"     # a render that SUCCEEDED while its group was unproven
PENDING_REQUEST = "REQUEST"     # a newer generation asked for while the slot was unproven
# A failure or a stall is held under the very outcome name the bounded retry
# policy already knows ("FAILED" / "STALLED"), so resuming it is one decision,
# not a second interpretation of the same event.

# v6, finding E.  How many bounded release rounds ``shutdown()`` may spend before
# it refuses to let the controller leave quietly.  Bounded on purpose: a group
# that never proves gone must fail closed, never hang a shutdown forever.
SHUTDOWN_RELEASE_ATTEMPTS = 3

# v7 (finding Codex on v6).  How long the controller WAITS between two bounded
# drain rounds while it holds a retained group.  A paced retry, never a CPU
# spin: the controller stays alive and keeps its authority (the retained group's
# identity and the ``ui-session.lock`` it inherited) instead of exiting and
# handing the machine to a controller that would race a group nobody remembers.
GUARDED_RECOVERY_PAUSE_S = 5.0

# v6, finding E.  The exit status HOME returns when it refuses to replace itself
# (or to exit "normally") while a worker group is retained.  Distinct, so both a
# service manager and a human read a fail-closed exit instead of a clean one.
# 75 is EX_TEMPFAIL (sysexits.h): a temporary failure, the operation may be
# retried — which is the exact shape here, since nothing was published and
# nothing is broken.
EXIT_CLEANUP_UNPROVEN = 75

# Ownership of a released worker is a two-state machine, never a boolean:
#   CLEANUP_PROVEN    the group is proven gone: the slot is free, a retry or a
#                     new generation may start.
#   CLEANUP_UNPROVEN  the group could not be proven gone: the identity is
#                     RETAINED (self.group is kept, the leader is left
#                     unreaped) and no new worker, retry, next generation or
#                     success publication may proceed while it holds.
CLEANUP_PROVEN = "CLEANUP_PROVEN"
CLEANUP_UNPROVEN = "CLEANUP_UNPROVEN"

# Bounded recovery: how many times an unproven release is re-attempted before
# the supervisor settles into an observable, truthful fail-closed state.
# Bounded and deterministic — an unproven group never becomes an infinite loop.
CLEANUP_MAX_RECOVERY_ATTEMPTS = 3


# How a single /proc/<pid>/stat read ended.  The distinction is the whole
# point of finding C: an entry that CANNOT be read is not an entry that holds
# nothing.  "the entry vanished" and "the entry is there but invisible" must not
# be collapsed, or an incomplete scan is mistaken for an empty group.
STAT_OK = "OK"
STAT_GONE = "GONE"              # FileNotFoundError: the process exited between
#                                 the listing and the read — a normal race
STAT_UNREADABLE = "UNREADABLE"  # any other OSError / a malformed stat: the entry
#                                 exists and cannot be inspected


def _read_proc_stat(pid_entry) -> tuple[str, tuple[str, int, int, int] | None]:
    """Read one /proc entry and say WHY it failed, not merely THAT it failed."""
    try:
        text = (pid_entry / "stat").read_text(encoding="utf-8", errors="replace")
    except FileNotFoundError:
        return STAT_GONE, None
    except OSError:
        return STAT_UNREADABLE, None
    try:
        # comm may contain spaces and parentheses: split on the LAST ')'
        fields = text.rsplit(")", 1)[1].split()
        return STAT_OK, (fields[0], int(fields[2]), int(fields[3]), int(fields[19]))
    except (IndexError, ValueError):
        return STAT_UNREADABLE, None


def _proc_stat(pid_entry: pathlib.Path) -> tuple[str, int, int, int] | None:
    """Return ``(state, pgrp, session, starttime)`` for one /proc entry, or None.

    ``starttime`` — field 22, in clock ticks since boot — identifies ONE
    incarnation of ONE pid: two processes that reused a pid number carry
    different start times.  It is what lets a captured group be re-identified
    later without ever asking the kernel to resolve a pgid from a pid again.

    Only this pid's state/start time is wanted here, so both failure modes
    collapse to ``None``; the group scan needs the finer distinction and calls
    ``_read_proc_stat`` directly.
    """
    status, parsed = _read_proc_stat(pid_entry)
    return parsed if status == STAT_OK else None


def worker_process_state(pid: int, proc_root: pathlib.Path = PROC_ROOT) -> str | None:
    """Process state of ``pid`` (``'Z'`` zombie), or ``None`` when not readable.

    Used to see that a worker has exited WITHOUT reaping it: ``proc.poll()``
    would collect the leader, free its pid, and with it the pinning that keeps
    the group's number ours.
    """
    parsed = _proc_stat(proc_root / str(int(pid)))
    return None if parsed is None else parsed[0]


def worker_starttime(pid: int, proc_root: pathlib.Path = PROC_ROOT) -> int | None:
    """Identity of the current incarnation of ``pid``, or None if unreadable."""
    parsed = _proc_stat(proc_root / str(int(pid)))
    return None if parsed is None else parsed[3]


_CLD_EXITED = getattr(os, "CLD_EXITED", 1)


def leader_exited_without_reaping(pid: int) -> bool | None:
    """True/False/None — has ``pid`` exited, WITHOUT reaping it?

    ``proc.poll()`` (v4's fallback when /proc was unreadable) calls ``waitpid``
    and COLLECTS the leader: its pid is then free, and the pgid that pinned the
    group is gone.  ``waitid`` with ``WNOWAIT`` peeks at the child's exit status
    and leaves it unreaped, so observation never destroys the ownership it is
    about to be used for.  ``None`` means the question cannot be answered (the
    pid is not our child, or waitid is unavailable): the caller stays
    fail-closed instead of guessing.
    """
    try:
        info = os.waitid(os.P_PID, int(pid), os.WEXITED | os.WNOHANG | os.WNOWAIT)
    except (ChildProcessError, OSError):
        return None
    return info is not None


def leader_exit_success_without_reaping(pid: int) -> bool | None:
    """True iff ``pid`` exited NORMALLY with status 0, without reaping it.

    Used only when the group could NOT be proven released: whether the render
    succeeded decides between "publish nothing" (a success) and "publish the
    truthful fallback" (a failure), and that decision must not require a reap.
    """
    try:
        info = os.waitid(os.P_PID, int(pid), os.WEXITED | os.WNOHANG | os.WNOWAIT)
    except (ChildProcessError, OSError):
        return None
    if info is None:
        return None
    return getattr(info, "si_code", None) == _CLD_EXITED and getattr(info, "si_status", None) == 0


def process_group_members(pgid: int, proc_root: pathlib.Path = PROC_ROOT) -> list[tuple[int, str, int, int]] | None:
    """Return ``[(pid, state, session, starttime)]`` for the members of ``pgid``.

    ``None`` means the scan cannot be trusted (unreadable /proc, hidepid): the
    caller must then say it does not know, never guess.
    """
    try:
        entries = list(proc_root.iterdir())
    except OSError:
        return None
    members = []
    for entry in entries:
        if not entry.name.isdigit():
            continue
        status, parsed = _read_proc_stat(entry)
        if status == STAT_UNREADABLE:
            # DECISION RULE.  A pid entry we can SEE but not READ may be a member
            # of ``pgid``; skipping it silently (v4) could turn an incomplete
            # scan into "the group is empty", i.e. a false GONE.  So
            # incompleteness PROVES nothing: the scan declares itself
            # untrustworthy and returns None, and every caller answers UNKNOWN
            # rather than GONE.  A VANISHED entry (STAT_GONE) is different: it
            # raced with the scan because its process exited, has no member left
            # to hide, and is skipped — so a normal exit does not pin every probe
            # to UNKNOWN.
            return None
        if parsed is None:                       # STAT_GONE: raced away
            continue
        state, group, session, starttime = parsed
        if group == int(pgid):
            members.append((int(entry.name), state, session, starttime))
    return members


def process_group_live_members(pgid: int, proc_root: pathlib.Path = PROC_ROOT) -> int | None:
    """Number of LIVE (non-zombie) members of ``pgid``; ``None`` when unreadable."""
    members = process_group_members(pgid, proc_root)
    if members is None:
        return None
    return sum(1 for _pid, state, _session, _start in members if state != "Z")


def process_group_liveness(pgid: int, proc_root: pathlib.Path = PROC_ROOT) -> str:
    """``LIVENESS_LIVE`` / ``LIVENESS_GONE`` / ``LIVENESS_UNKNOWN`` for ``pgid``.

    The kernel's signal-0 answer is only the first half of the question: a group
    holding nothing but unreaped zombies answers it exactly like a group holding
    a live process, so "it answered" is not "it is alive".  The second half is
    /proc; when /proc cannot be read the answer is ``UNKNOWN`` — deliberately
    not a boolean, so no caller can turn "cannot tell" into "still running".

    FINDING C (v6).  An EMPTY scan is not a gone group either.  ``killpg(pgid, 0)``
    succeeding while /proc lists no member is exactly what a partial view produces
    — hidepid, a mount namespace, an unfinished scan — and v5 answered ``GONE``
    there, i.e. it declared the group dead on the strength of a blind spot.  The
    kernel is asked a SECOND time instead: ``GONE`` is returned only when that
    second probe says ESRCH.  If the kernel still answers, the group exists and
    nothing proves it empty: the answer is ``UNKNOWN``.  (A scan that DO see
    members is judged as before: any live member means LIVE, and members that are
    all zombies — a real, observed group of the dead — mean GONE.)
    """
    if pgid is None or int(pgid) <= 0:
        return LIVENESS_GONE
    try:
        os.killpg(int(pgid), 0)
    except ProcessLookupError:
        return LIVENESS_GONE
    except PermissionError:
        return LIVENESS_UNKNOWN     # it exists, but it is not ours to look into
    except OSError:
        return LIVENESS_UNKNOWN
    members = process_group_members(pgid, proc_root)
    if members is None:
        return LIVENESS_UNKNOWN
    if any(state != "Z" for _pid, state, _session, _start in members):
        return LIVENESS_LIVE
    if members:
        return LIVENESS_GONE       # observed, and only zombies: genuinely gone
    # EMPTY SCAN.  The kernel has just said the group exists; /proc shows no
    # member.  Only the kernel can settle that contradiction, and it settles it
    # in exactly one direction: ESRCH, and only ESRCH, means gone.
    try:
        os.killpg(int(pgid), 0)
    except ProcessLookupError:
        return LIVENESS_GONE       # second probe: the group really is gone
    except (PermissionError, OSError):
        return LIVENESS_UNKNOWN
    return LIVENESS_UNKNOWN        # the kernel still names a group we cannot see


def process_group_survives(pgid: int, proc_root: pathlib.Path = PROC_ROOT) -> bool:
    """True only when the group is PROVEN to hold a live process.

    Strict on purpose, and NOT the negation of "gone": when /proc is unreadable
    the answer is False because nothing is proven, while the group's state is
    really ``UNKNOWN``.  Callers that must act on that ambiguity ask
    ``process_group_liveness`` — the termination helper does.
    """
    return process_group_liveness(pgid, proc_root) == LIVENESS_LIVE


def process_group_is_own_session(pgid: int, proc_root: pathlib.Path = PROC_ROOT) -> bool | None:
    """True when every live member of ``pgid`` sits in the session ``pgid`` opened.

    ``start_new_session=True`` makes the worker both session and group leader,
    so ``sid == pgid`` for every member that did not call ``setsid()`` itself.
    ``None`` means "cannot tell": unreadable /proc, or a group with no live
    member left to judge.  An empty group is not evidence of a stranger — v3
    read it as one, and a group that died at the end of its grace was then
    reported ``GROUP_NOT_OURS`` instead of "gone".
    """
    members = process_group_members(pgid, proc_root)
    if members is None:
        return None
    live = [session for _pid, state, session, _start in members if state != "Z"]
    if not live:
        return None
    return all(session == int(pgid) for session in live)


class WorkerGroup:
    """The process group a worker opened, OWNED from the instant it was spawned.

    Ownership is captured, never re-derived.  The pgid is read ONCE — while the
    worker is alive and unreaped — and the leader's start time is kept with it,
    so the identity can be checked later without calling ``os.getpgid`` again.
    Re-deriving a pgid from a pid after a reap is what opens the PID-reuse
    window: the pid may already name an unrelated process, and that process's
    group would then be the one signalled.  This object exists so the window is
    never opened.

    ``pgid`` is ``None`` when the worker owns no group we may signal: it is not
    its own group leader (``start_new_session`` was not used), it shares the
    controller's group, or the kernel would not name its group.  In those cases
    only its pid may be signalled, and only while it is unreaped.
    """

    __slots__ = ("proc", "pid", "pgid", "starttime", "controller_session")

    def __init__(self, proc, pid: int, pgid: int | None, starttime: int | None = None,
                 controller_session: int | None = None):
        self.proc = proc
        self.pid = int(pid)
        self.pgid = None if pgid is None else int(pgid)
        self.starttime = starttime
        self.controller_session = controller_session

    @property
    def owns_group(self) -> bool:
        """True only when the group this worker opened is PROVEN ours to signal.

        Strict on purpose (finding A, v6): a pgid that is ``None``, non-positive,
        different from the leader's own pid, or equal to the controller's session
        is not an ownership — it is the absence of one.  ``capture_worker_group``
        only ever records a pgid that satisfies every clause, so this property
        cannot turn a failed or mismatched capture into a licence to signal.
        """
        if self.pgid is None or self.pgid <= 0:
            return False
        if self.pgid != self.pid:
            return False                # not its own group leader
        if self.controller_session is not None and self.pgid == self.controller_session:
            return False                # the group is OURS: never signal it
        return True

    def __repr__(self) -> str:
        return f"WorkerGroup(pid={self.pid}, pgid={self.pgid}, starttime={self.starttime})"


def capture_worker_group(proc, proc_root: pathlib.Path = PROC_ROOT, pgid_of=None) -> WorkerGroup | None:
    """Take ownership of ``proc``'s group — only while its leader is UNREAPED.

    ``None`` means ownership is impossible and must not be faked: there is no
    process, or its leader was already reaped, in which case its pid is free
    again and asking the kernel which group it is in would be a guess about a
    stranger.  A caller that reaps its own worker before calling this has lost
    the group; the fix is to capture at spawn, which is what the supervisor
    does.  ``pgid_of`` is the ONLY place a pgid is ever resolved from a pid.
    """
    if proc is None:
        return None
    if proc.returncode is not None:
        return None
    try:
        controller_session = int(os.getpgid(0))
    except OSError:
        controller_session = None
    resolve = pgid_of or os.getpgid
    try:
        pgid = int(resolve(proc.pid))
    except (ProcessLookupError, OSError):
        # Unreaped, yet the kernel will not name its group: own no group, but
        # keep the worker — it is still our child and still ours to signal.
        return WorkerGroup(proc, proc.pid, None, None, controller_session)
    if pgid != int(proc.pid) or pgid == controller_session:
        return WorkerGroup(proc, proc.pid, None, None, controller_session)
    return WorkerGroup(proc, proc.pid, pgid, worker_starttime(proc.pid, proc_root), controller_session)


def group_identity_holds(group: WorkerGroup, proc_root: pathlib.Path = PROC_ROOT) -> bool | None:
    """True when ``group.pgid`` still names the leader we captured.

    A pgid is a pid, and a pid number is only released once nothing uses it —
    but that number IS what names the group, so while any member sits in the
    group the kernel cannot hand the number to anybody else.  This check is the
    belt to that brace, and it is only needed once the leader has been reaped:
    the leader's start time is unique to one incarnation of one pid, so a
    process carrying our number with a different start time is a recycled
    number — not ours.  ``None`` means the question cannot be answered: /proc
    unreadable, no start time recorded, or the leader's own entry already gone.
    """
    if group.pgid is None or group.starttime is None:
        return None
    members = process_group_members(group.pgid, proc_root)
    if members is None:
        return None
    for pid, _state, _session, starttime in members:
        if pid == group.pgid:
            return int(starttime) == int(group.starttime)
    return None


def _signal_worker_group(group: WorkerGroup, sig: int) -> str:
    """Signal the group and report EXACTLY what the kernel said.

    There is no fallback to the leader's pid here, for two reasons.  CPython's
    ``Popen.send_signal`` calls ``poll()`` first, and ``poll()`` REAPS a leader
    that has exited: the pid is then free, and the pinning that made this group
    safe to address is gone.  And a refused group (EPERM) is not a pid to poke
    instead — the same right is missing for the pid, so a group that cannot be
    shown to be ours must never be turned into "signal the pid anyway".  The
    caller gets a code, and decides.
    """
    try:
        os.killpg(int(group.pgid), int(sig))
        return SIGNAL_OK
    except ProcessLookupError:
        return SIGNAL_GONE
    except PermissionError:
        return SIGNAL_NOT_OURS
    except OSError:
        return SIGNAL_FAILED


def _wait_group_gone(pgid: int, proc_root: pathlib.Path, timeout_s: float, pause_s: float) -> str:
    """Wait, bounded, for the group to stop holding live processes.

    Returns the liveness observed at the end, so "gone", "still there" and
    "cannot tell" stay distinguishable to the caller instead of being collapsed
    into one boolean.
    """
    deadline = time.monotonic() + max(0.0, float(timeout_s))
    while True:
        state = process_group_liveness(pgid, proc_root)
        if state == LIVENESS_GONE:
            return LIVENESS_GONE
        if time.monotonic() >= deadline:
            return state
        time.sleep(max(0.01, float(pause_s)))


def _reap_worker(proc, timeout_s: float) -> None:
    """Collect the worker if it exited, so it cannot linger as a zombie.

    Only ever called once the group has been dealt with: while the leader is
    unreaped its pid is pinned, and that is what makes addressing its group
    safe.  Reaping first would free the pid — and the pgid with it.
    """
    if proc is None or proc.returncode is not None:
        return
    try:
        proc.wait(timeout=max(0.0, float(timeout_s)))
    except subprocess.TimeoutExpired:
        pass


def _terminate_single_process(proc, grace_s: float, kill_grace_s: float) -> str:
    """Stop one process without ever signalling a group (it shares ours).

    ``proc.poll()`` is safe HERE: there is no group to keep pinned, and that
    check is exactly what keeps a signal away from an already-reaped pid.
    """
    if proc.poll() is not None:
        return "ALREADY_EXITED"
    try:
        proc.send_signal(signal.SIGTERM)
    except (ProcessLookupError, OSError):
        return "ALREADY_EXITED"
    try:
        proc.wait(timeout=max(0.0, float(grace_s)))
        return "TERMINATED"
    except subprocess.TimeoutExpired:
        pass
    try:
        proc.send_signal(signal.SIGKILL)     # still unreaped: the pid is still pinned
    except (ProcessLookupError, OSError):
        return "KILLED"
    try:
        proc.wait(timeout=max(0.0, float(kill_grace_s)))
    except subprocess.TimeoutExpired:
        return "UNREAPED"
    return "KILLED"


def terminate_worker_group(target, grace_s: float = 1.0, kill_grace_s: float = 1.0,
                           pause_s: float = 0.05, proc_root: pathlib.Path = PROC_ROOT) -> str:
    """Stop a regeneration worker AND every descendant it left behind.

    The worker is spawned with ``start_new_session=True``: it is a session and
    process-group leader, and every step it runs (the disc-sheet render, the
    media-graph rebuild) is a child in that same group.  Signalling only the
    parent pid leaves those children alive, still writing into the state of a
    generation that has already been superseded.

    The GROUP is the unit of observation, never the parent, and it is addressed
    by its CAPTURED identity (a :class:`WorkerGroup`), never by a pgid resolved
    from a pid at termination time.  Two rules follow, and both are enforced
    here rather than asserted in a comment:

    * A pid that has already been reaped is never used to resolve a pgid.  Its
      number is free again and may name an unrelated process whose group would
      then be the one killed, so this function refuses to guess: a bare
      ``Popen`` whose leader was reaped comes back ``ALREADY_EXITED``, with no
      ``os.getpgid`` and no ``killpg`` at all.
    * A group that cannot be shown to be the worker's is not signalled
      (``GROUP_NOT_OURS``, ``GROUP_UNKNOWN``, ``SIGNAL_ERROR``), and the leader
      is then left UNREAPED on purpose: while it is unreaped its pid — hence its
      pgid — cannot be recycled, so a later, better-informed attempt stays safe.

    The group's death is established by /proc, not by the leader's exit status:
    a descendant that ignores SIGTERM outlives its leader, so once the bounded
    grace expires the SIGKILL goes to the group EVEN THOUGH the leader has
    already exited, and a group holding only zombies counts as gone.  When /proc
    cannot be read the outcome is never asserted: a group that still answers the
    kernel is reported ``GROUP_UNKNOWN`` rather than the false
    ``GROUP_STILL_PRESENT`` that v3 produced from the very same blind spot.

    Outcome: ``NO_WORKER`` / ``ALREADY_EXITED`` / ``NO_GROUP`` / ``TERMINATED`` /
    ``KILLED`` / ``GROUP_NOT_OURS`` / ``NO_GROUP_UNPROVEN`` / ``GROUP_STILL_PRESENT``
    / ``GROUP_UNKNOWN`` / ``SIGNAL_ERROR`` / ``UNREAPED``.
    """
    if target is None:
        return "NO_WORKER"
    if isinstance(target, WorkerGroup):
        group = target
    else:
        if target.returncode is not None:
            # The caller has already reaped the leader: its pid is not ours to
            # resolve any more, and ownership had to be captured at spawn.  The
            # only honest answer is a refusal — no getpgid, no signal.
            return "ALREADY_EXITED"
        group = capture_worker_group(target, proc_root)
        if group is None:
            return "ALREADY_EXITED"
    proc = group.proc
    if not group.owns_group:
        if proc is None:
            return "NO_GROUP"
        if group.pgid is not None:
            # A group NUMBER was recorded and this worker is not proven to lead
            # it: its descendants are reachable through that number and we cannot
            # prove the number is ours.  Refuse — no single-process fallback (it
            # would report "cleaned" for a worker whose group was never ours),
            # and the leader is left unreaped so a later attempt stays possible.
            return NO_GROUP_UNPROVEN
        return _terminate_single_process(proc, grace_s, kill_grace_s)
    pgid = group.pgid

    if process_group_liveness(pgid, proc_root) == LIVENESS_GONE:
        _reap_worker(proc, kill_grace_s)
        return "ALREADY_EXITED"

    if proc is not None and proc.returncode is not None:
        # The leader has been reaped, so the pid-pinning proof is gone: the
        # identity must be re-proved before a signal is aimed at that number.
        identity = group_identity_holds(group, proc_root)
        if identity is False:
            return "GROUP_NOT_OURS"
        if identity is None:
            return "GROUP_UNKNOWN"

    sent = _signal_worker_group(group, signal.SIGTERM)
    if sent == SIGNAL_GONE:
        _reap_worker(proc, kill_grace_s)
        return "TERMINATED"          # the group vanished: nothing was there to stop
    if sent == SIGNAL_NOT_OURS:
        return "GROUP_NOT_OURS"
    if sent == SIGNAL_FAILED:
        return "SIGNAL_ERROR"

    after = _wait_group_gone(pgid, proc_root, grace_s, pause_s)
    if after == LIVENESS_GONE:
        _reap_worker(proc, kill_grace_s)
        return "TERMINATED"

    if after == LIVENESS_LIVE:
        if process_group_is_own_session(pgid, proc_root) is False:
            return "GROUP_NOT_OURS"
        # The group can die between the end of the grace and this check.  A group
        # that is gone is GONE — not a stranger, which is what v3 concluded the
        # moment its probe found no live member left to judge.
        if process_group_liveness(pgid, proc_root) == LIVENESS_GONE:
            _reap_worker(proc, kill_grace_s)
            return "TERMINATED"

    killed = _signal_worker_group(group, signal.SIGKILL)
    if killed == SIGNAL_GONE:
        _reap_worker(proc, kill_grace_s)
        return "TERMINATED"          # vanished before the SIGKILL: not attributed to it
    if killed == SIGNAL_NOT_OURS:
        return "GROUP_NOT_OURS"
    if killed == SIGNAL_FAILED:
        return "SIGNAL_ERROR"

    final = _wait_group_gone(pgid, proc_root, kill_grace_s, pause_s)
    if final == LIVENESS_GONE:
        _reap_worker(proc, kill_grace_s)
        return "KILLED"
    if final == LIVENESS_UNKNOWN:
        # FINDING B (v6).  v5 collected the leader here, "as a bounded last
        # resort", and that reap is precisely what destroyed the ownership it was
        # about to report on: with the leader collected its pid is free again and
        # the pgid that pinned the group is gone with it, so a descendant that is
        # still alive becomes unreachable — permanently, because no later attempt
        # can identify the group any more.  The leader is left UNREAPED on
        # purpose, and the outcome says exactly what is known: the group's
        # disappearance was NOT proven.  The caller keeps the identity and the
        # bounded recovery re-attempts against the SAME group.
        return "GROUP_UNKNOWN"
    # Proven to still hold a live process after SIGKILL: reported as such, and
    # the leader is left unreaped so the pinned pid keeps a later attempt safe.
    return "GROUP_STILL_PRESENT"


def load_theme(install: pathlib.Path):
    import importlib.util
    path = install / "openhtpc-theme.py"
    if not path.is_file():
        path = pathlib.Path(__file__).with_name("openhtpc-theme.py")
    spec = importlib.util.spec_from_file_location("openhtpc_theme", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class GateError(RuntimeError):
    def __init__(self, gate: str, reason: str, message: str):
        super().__init__(message)
        self.gate = gate
        self.reason = reason


def load_object(path: pathlib.Path, gate: str, missing: str, invalid: str) -> dict:
    if not path.is_file():
        raise GateError(gate, missing, f"Fichier requis absent : {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise GateError(gate, invalid, f"Fichier JSON invalide : {path}") from exc
    if not isinstance(value, dict):
        raise GateError(gate, invalid, f"Objet JSON attendu : {path}")
    return value


def validate_profile(profile: dict) -> None:
    required = ("generator", "detected", "gpu_topology", "video_backend", "runtime", "runtime_profiles")
    if not all(isinstance(profile.get(key), dict) for key in required):
        raise GateError("hardware_profile", "PROFILE_INVALID", "Le profil matériel CURRENT est incomplet.")
    generator = profile["generator"]
    if generator.get("name") != "OPENHTPC Builder" or not generator.get("version"):
        raise GateError("hardware_profile", "PROFILE_INVALID", "Le profil ne provient pas du Builder OPENHTPC CURRENT.")


def validate_capability_provenance(profile: dict, snapshot: dict) -> None:
    if not snapshot:
        return
    source = profile.get("capability_source")
    if not isinstance(source, dict) or not all(source.get(key) for key in ("hardware_fingerprint", "runtime_fingerprint")):
        raise GateError("hardware_profile", "PASSPORT_REBUILD_REQUIRED", "Le Hardware Passport legacy doit être reconstruit.")
    if any(source.get(key) != snapshot.get(key) for key in ("hardware_fingerprint", "runtime_fingerprint")):
        raise GateError("hardware_profile", "PASSPORT_STALE", "Le Hardware Passport ne correspond pas aux capacités courantes.")
    runtime_source = profile.get("runtime", {}).get("generation_provenance", {}).get("capability_source")
    if runtime_source != source:
        raise GateError("runtime", "RUNTIME_STALE", "Le runtime ne correspond pas au Hardware Passport courant.")


def viability(profile: dict) -> dict:
    backend = profile["video_backend"]
    topology = profile["gpu_topology"]
    processing = topology.get("processing_gpu")
    failures = []
    if backend.get("status") != "observed":
        failures.append("backend vidéo non observé")
    if not backend.get("decode_api"):
        failures.append("API de décodage non observée")
    if not backend.get("render_api"):
        failures.append("API de rendu non observée")
    if not backend.get("render_node"):
        failures.append("render node absent")
    if not isinstance(processing, dict):
        failures.append("GPU de traitement non associé")
    if topology.get("offload_required") is True and topology.get("offload_validated") is not True:
        failures.append("chemin multi-GPU non validé")
    return {
        "status": "PASS" if not failures else "FAIL",
        "basis": "CURRENT observed backend and GPU topology",
        "failures": failures,
    }


def validate_runtime(profile: dict, home: pathlib.Path) -> None:
    runtime = profile["runtime"]
    profiles = profile["runtime_profiles"].get("profiles")
    pure = profiles.get("PURE") if isinstance(profiles, dict) else None
    if runtime.get("status") != "ready" or runtime.get("playback_validated") not in (False, True):
        raise GateError("runtime", "RUNTIME_NOT_READY", "Le runtime MPV CURRENT n'est pas prêt.")
    if not isinstance(pure, dict) or pure.get("generation_status") != "generated":
        raise GateError("runtime", "PURE_NOT_GENERATED", "Le profil PURE CURRENT n'est pas généré.")
    config = pure.get("config_path")
    if not isinstance(config, str) or not config:
        config = str(home / ".config/openhtpc/runtime/mpv/pure.conf")
    path = pathlib.Path(config)
    if not path.is_absolute():
        raise GateError("runtime", "RUNTIME_CONFIG_INVALID", "Le chemin du runtime PURE n'est pas absolu.")
    if not path.is_file():
        raise GateError("runtime", "RUNTIME_CONFIG_MISSING", f"Configuration PURE absente : {path}")


def validate_user_config(config: dict, credential: pathlib.Path) -> list[pathlib.Path]:
    if config.get("configuration_completed") is not True:
        raise GateError("initial_configuration", "CONFIGURATION_INCOMPLETE", "La configuration initiale n'est pas terminée.")
    sources = config.get("local_media_sources")
    tmdb = config.get("tmdb")
    if not isinstance(sources, list) or not isinstance(tmdb, dict) or not isinstance(tmdb.get("configured"), bool):
        raise GateError("initial_configuration", "CONFIGURATION_INVALID", "La configuration utilisateur est invalide.")
    paths = []
    for source in sources:
        if not isinstance(source, str) or not pathlib.Path(source).is_absolute():
            raise GateError("initial_configuration", "CONFIGURATION_INVALID", "Chaque source média doit être un chemin absolu.")
        paths.append(pathlib.Path(source))
    if tmdb["configured"]:
        try:
            mode = stat.S_IMODE(credential.stat().st_mode)
            present = credential.is_file() and credential.stat().st_size > 0
        except OSError:
            present, mode = False, 0
        if not present or mode & 0o077:
            raise GateError("initial_configuration", "TMDB_CREDENTIAL_INVALID", "La configuration TMDb privée est absente ou insuffisamment protégée.")
    return paths


def ini_value(value: str) -> str:
    return value.replace("\n", " ").replace("\r", " ").replace(";", "—")


def normalized_disc_title(value: object) -> str:
    """Return a conservative couch label while retaining raw state elsewhere."""
    title = ini_value(str(value or "")).strip()
    title = re.sub(r"(?i)(?:[ _.-]+)(?:DVD|DISC|DISK)\s*[12]\s*$", "", title).strip()
    return title or "Disque identifié"


def optical_home_label(optical: dict) -> str:
    title = normalized_disc_title(
        optical.get("tmdb_title") or optical.get("disc_title") or
        optical.get("normalized_volume_label") or optical.get("volume_label")
    )
    prefix = _optical_model.presentation(optical)["home_prefix"]
    # Flex receives the complete title. It can use the available item width;
    # the disc sheet remains the authoritative full-title presentation.
    return f"{prefix} - {title}"


def dvd_home_label(optical: dict, limit: int | None = None) -> str:
    """Compatibility name for callers from older Basic RCs."""
    return optical_home_label({**optical, "state": "DVD"})


def observed_display_size(environment=None) -> tuple[int, int] | None:
    environment = os.environ if environment is None else environment
    override = environment.get("OPENHTPC_DISPLAY_SIZE")
    if override:
        try:
            width, height = (int(value) for value in override.lower().split("x", 1))
            return (width, height) if width > 0 and height > 0 else None
        except ValueError:
            return None
    try:
        home = pathlib.Path(environment.get("OPENHTPC_HOME", pathlib.Path.home())) if isinstance(environment, dict) else pathlib.Path.home()
        install = pathlib.Path(os.environ.get("OPENHTPC_INSTALL_DIR", home / ".local/lib/openhtpc"))
        cap_path = install / "openhtpc-capabilities.py"
        if not cap_path.is_file():
            cap_path = pathlib.Path(__file__).with_name("openhtpc-capabilities.py")
        caps = sys.modules.get("openhtpc_capabilities")
        if caps is None and cap_path.is_file():
            try:
                spec = importlib.util.spec_from_file_location("openhtpc_capabilities", cap_path)
                if spec and spec.loader:
                    caps = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(caps)
            except Exception:
                caps = None
        context = {"status": "UNAVAILABLE", "environment": {}}
        if caps is not None and hasattr(caps, "resolve_graphical_context"):
            try:
                context = caps.resolve_graphical_context(environment=environment if isinstance(environment, dict) else None, home=home, install=install)
            except Exception:
                pass
        if (
            context.get("status") != "RESOLVED"
            or not context.get("environment")
            or (hasattr(caps, "is_graphical_context_usable") and not caps.is_graphical_context_usable(context["environment"]))
        ):
            return None
        env = os.environ.copy()
        for key in ("DISPLAY", "WAYLAND_DISPLAY", "XDG_RUNTIME_DIR", "DBUS_SESSION_BUS_ADDRESS"):
            env.pop(key, None)
        env.update(context["environment"])
        result = subprocess.run(["kscreen-doctor", "-j"], env=env, text=True, capture_output=True, timeout=5)
        data = json.loads(result.stdout) if result.returncode == 0 else {}
        sizes = []
        for output in data.get("outputs", []):
            if not output.get("enabled"):
                continue
            current = output.get("currentModeId")
            mode = next((item for item in output.get("modes", []) if item.get("id") == current), None)
            size = (mode or {}).get("size", {})
            if size.get("width") and size.get("height"):
                sizes.append((int(size["width"]), int(size["height"])))
        return max(sizes, key=lambda item: item[0] * item[1]) if sizes else None
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError, TypeError, ValueError):
        return None


def flex_scale(size: tuple[int, int] | None) -> dict[str, int]:
    basis = min(size) if size else 1080
    return {
        "icon": max(165, min(280, round(basis * 0.17))),
        "title": max(42, min(72, round(basis * 0.049))),
        "clock": max(34, min(74, round(basis * 0.043))),
        "padding": max(16, min(32, round(basis * 0.018))),
    }


def _load_media_types():
    import importlib.util
    for base in (pathlib.Path(__file__).resolve().parent, pathlib.Path.home() / ".local/lib/openhtpc"):
        target = base / "openhtpc-media-types.py"
        if target.is_file():
            spec = importlib.util.spec_from_file_location("openhtpc_media_types", target)
            if spec and spec.loader:
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                return mod
    return None

_media_types = _load_media_types()
VIDEO_EXTENSIONS = _media_types.VIDEO_EXTENSIONS if _media_types is not None else {".mkv", ".mp4", ".m4v", ".avi", ".mov", ".webm", ".mpg", ".mpeg", ".ts", ".m2ts", ".vob"}


def menu_name(prefix: str, value: object) -> str:
    return prefix + "_" + hashlib.blake2s(str(value).encode("utf-8"), digest_size=8).hexdigest()


def media_source_id(path: pathlib.Path) -> str:
    return hashlib.blake2s(os.fsencode(path), digest_size=8).hexdigest()


NETWORK_MEDIA_FILESYSTEMS = {"cifs", "smb3", "nfs", "nfs4", "fuse.sshfs", "sshfs"}


def _decode_mountinfo_path(value: str) -> pathlib.Path:
    for encoded, decoded in ((r"\040", " "), (r"\011", "\t"), (r"\012", "\n"), (r"\134", chr(92))):
        value = value.replace(encoded, decoded)
    return pathlib.Path(value)


def _source_filesystem_type(
    path: pathlib.Path,
    mountinfo_path: pathlib.Path = pathlib.Path("/proc/self/mountinfo"),
) -> str | None:
    """Return the filesystem type of the longest mount containing path."""
    try:
        resolved = path.resolve()
    except OSError:
        resolved = path
    best: tuple[int, int, str] | None = None
    try:
        lines = mountinfo_path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return None
    for line in lines:
        left, sep, right = line.partition(" - ")
        if not sep:
            continue
        left_fields = left.split()
        right_fields = right.split()
        if len(left_fields) < 5 or not right_fields:
            continue
        mountpoint = _decode_mountinfo_path(left_fields[4])
        try:
            contains = resolved == mountpoint or mountpoint in resolved.parents
        except (OSError, RuntimeError):
            contains = False
        if contains:
            score = len(str(mountpoint))
            filesystem = right_fields[0].casefold()
            if filesystem in NETWORK_MEDIA_FILESYSTEMS:
                priority = 2
            elif filesystem == "autofs":
                priority = 0
            else:
                priority = 1
            candidate = (score, priority, filesystem)
            if best is None or candidate[:2] > best[:2]:
                best = candidate
    return best[2] if best is not None else None


def _source_kind_label(path: pathlib.Path) -> str:
    filesystem = _source_filesystem_type(path)
    return "NAS / RÉSEAU" if filesystem in NETWORK_MEDIA_FILESYSTEMS else "LOCAL"


def media_item_id(source_id: str, relative_path: pathlib.PurePath, item_type: str) -> str:
    value=f"media:{source_id}:{item_type}:{relative_path.as_posix()}"
    return hashlib.blake2s(value.encode("utf-8"),digest_size=12).hexdigest()


def media_action_token(generation: str, item_id: str) -> str:
    value = f"{generation}:{item_id}"
    return "mact_" + hashlib.blake2s(value.encode("utf-8"), digest_size=16).hexdigest()


def current_media_manifest(home: pathlib.Path) -> pathlib.Path:
    return home/".local/state/openhtpc/media-actions/current.json"


def active_media_generation(home: pathlib.Path) -> str | None:
    """Return the generation bound to the authoritative active MEDIA manifest."""
    model = load_optional_object(current_media_manifest(home))
    generation = model.get("manifest_generation")
    return generation if isinstance(generation, str) and generation else None


def write_media_model_state(home: pathlib.Path, generation: str, sources: list[dict], actions: dict[str, dict], target: pathlib.Path | None = None) -> pathlib.Path:
    target=target or current_media_manifest(home);target.parent.mkdir(parents=True,exist_ok=True)
    fd,temporary=tempfile.mkstemp(prefix=target.name+".",dir=target.parent)
    try:
        with os.fdopen(fd,"w",encoding="utf-8") as stream:
            # This file is the current UI model registry, not a media database.
            # Atomic replacement invalidates every token from the old model.
            data={"schema":1,"manifest_generation":generation,"sources":sources,"items":actions}
            json.dump(data,stream,ensure_ascii=False,sort_keys=True);stream.write("\n")
        os.chmod(temporary,0o600);os.replace(temporary,target)
    finally:
        if os.path.exists(temporary):os.unlink(temporary)
    return target


_POSTER_TOKEN_RE = re.compile(r"^/[A-Za-z0-9_-]+\.jpg$")
_MAX_POSTER_TOKEN_CHARS = 128
_MAX_POSTER_BYTES = 5_000_000


def _canonical_poster_path(poster_path: str, home: pathlib.Path) -> pathlib.Path | None:
    """Resolve canonical cache path for a validated TMDb movie poster token."""
    if not isinstance(poster_path, str) or len(poster_path) > _MAX_POSTER_TOKEN_CHARS or not _POSTER_TOKEN_RE.fullmatch(poster_path):
        return None
    material = f"tmdb_movie|poster|w500|{poster_path}"
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()
    return home / ".cache/openhtpc/media/artwork/tmdb_movie/poster/w500" / f"{digest}.jpg"


def _project_work_poster(home: pathlib.Path, work_id: int, payload_json: str | None, uid: int) -> pathlib.Path | None:
    """Safely project a verified cached poster to an ephemeral short symlink in /tmp.

    Stale symlinks from previous presentations are unlinked.
    Non-symlink objects at the alias path are never blindly overwritten.
    Returns the short symlink Path if valid, or None (fallback to generic icon).
    """
    if type(work_id) is not int or work_id <= 0:
        return None
    alias_path = pathlib.Path(f"/tmp/ohtpc-{uid}-p{work_id}.jpg")

    def _cleanup_stale_alias() -> None:
        if alias_path.is_symlink():
            try:
                alias_path.unlink(missing_ok=True)
            except OSError:
                pass

    if payload_json is None:
        _cleanup_stale_alias()
        return None

    try:
        payload = json.loads(payload_json)
    except Exception:
        _cleanup_stale_alias()
        return None

    if not isinstance(payload, dict):
        _cleanup_stale_alias()
        return None

    token = payload.get("poster_path")
    canonical_target = _canonical_poster_path(token, home)
    if canonical_target is None:
        _cleanup_stale_alias()
        return None

    try:
        if canonical_target.is_symlink() or not canonical_target.is_file():
            _cleanup_stale_alias()
            return None
        st = canonical_target.stat()
        if not (0 < st.st_size <= _MAX_POSTER_BYTES):
            _cleanup_stale_alias()
            return None
    except OSError:
        _cleanup_stale_alias()
        return None

    # Defense against unsafe pre-existing non-symlink object at alias path
    if alias_path.exists(follow_symlinks=False) and not alias_path.is_symlink():
        return None

    # Atomic symlink update
    temp_alias = pathlib.Path(f"/tmp/.ohtpc-{uid}-p{work_id}-{os.getpid()}-{time.time_ns()}.tmp")
    try:
        temp_alias.symlink_to(canonical_target)
        os.replace(temp_alias, alias_path)
        return alias_path
    except OSError:
        try:
            if temp_alias.is_symlink() or temp_alias.exists(follow_symlinks=False):
                temp_alias.unlink(missing_ok=True)
        except OSError:
            pass
        _cleanup_stale_alias()
        return None


def _extract_year(release_date: Any, fallback_year: Any = None) -> str | None:
    """Extract 4-digit release year from date string or fallback year."""
    if isinstance(release_date, str) and release_date.strip():
        m = re.match(r"^\s*(\d{4})", release_date.strip())
        if m:
            return m.group(1)
    if fallback_year is not None and not isinstance(fallback_year, bool):
        try:
            y = int(fallback_year)
            if 1800 <= y <= 2100:
                return str(y)
        except (ValueError, TypeError):
            pass
    return None


def _format_runtime(runtime_minutes: Any) -> str | None:
    """Format movie runtime in minutes to compact French couch string (e.g. 109 -> '1 h 49')."""
    if runtime_minutes is None or isinstance(runtime_minutes, bool):
        return None
    try:
        minutes = int(runtime_minutes)
    except (ValueError, TypeError):
        return None
    if minutes <= 0:
        return None
    if minutes < 60:
        return f"{minutes} min"
    hours = minutes // 60
    rem = minutes % 60
    if rem > 0:
        return f"{hours} h {rem:02d}"
    return f"{hours} h"


def _format_genres(genres_json: Any) -> str | None:
    """Parse genres_json safely and format as comma-separated French string."""
    if not genres_json or not isinstance(genres_json, str):
        return None
    try:
        data = json.loads(genres_json)
    except Exception:
        return None
    if not isinstance(data, list):
        return None
    cleaned: list[str] = []
    for g in data:
        if isinstance(g, str) and g.strip():
            val = ini_value(g.strip()).strip()
            if val:
                cleaned.append(val)
        elif isinstance(g, dict) and isinstance(g.get("name"), str) and g["name"].strip():
            val = ini_value(g["name"].strip()).strip()
            if val:
                cleaned.append(val)
    if cleaned:
        return ", ".join(cleaned)
    return None


def _chunk_synopsis(overview: str, max_row_bytes: int = 120, max_rows: int = 2) -> list[str]:
    """Break untrusted overview into up to two Flex-safe, couch-readable rows."""
    cleaned = ini_value(overview).strip()
    cleaned = " ".join(cleaned.split())
    if not cleaned:
        return ["Aucun synopsis disponible."]

    words = cleaned.split(" ")
    rows: list[str] = []
    current_words: list[str] = []

    i = 0
    while i < len(words) and len(rows) < max_rows:
        word = words[i]
        test_line = " ".join(current_words + [word]) if current_words else word
        if len(test_line.encode("utf-8")) <= max_row_bytes:
            current_words.append(word)
            i += 1
        else:
            if current_words:
                rows.append(" ".join(current_words))
                current_words = []
            else:
                chars: list[str] = []
                for ch in word:
                    if len("".join(chars + [ch]).encode("utf-8")) <= max_row_bytes:
                        chars.append(ch)
                    else:
                        break
                part1 = "".join(chars)
                rows.append(part1)
                remaining_word = word[len(chars):]
                words[i] = remaining_word

    if current_words and len(rows) < max_rows:
        rows.append(" ".join(current_words))

    if i < len(words) and rows:
        last = rows[-1]
        ellipsis = "…"
        while last and len((last + ellipsis).encode("utf-8")) > max_row_bytes:
            last = last[:-1].rstrip()
        rows[-1] = last + ellipsis

    return rows if rows else ["Aucun synopsis disponible."]


def _chunk_synopsis_properties(overview: str, max_chunk_bytes: int = 135, max_chunks: int = 16) -> list[str]:
    """Split overview text into word-bounded chunks suitable for Synopsis1..N INI properties."""
    cleaned = ini_value(overview.replace("\n", " ").replace("\r", " ")).strip()
    if not cleaned:
        return ["Aucun synopsis disponible."]
    words = cleaned.split()
    chunks: list[str] = []
    current_words: list[str] = []
    current_bytes = 0
    for w in words:
        w_bytes = len(w.encode("utf-8"))
        if w_bytes > max_chunk_bytes:
            if current_words:
                chunks.append(" ".join(current_words))
                current_words = []
                current_bytes = 0
            chunks.append(w[:max_chunk_bytes // 2])
            continue
        extra = 1 if current_words else 0
        if current_bytes + extra + w_bytes <= max_chunk_bytes:
            current_words.append(w)
            current_bytes += extra + w_bytes
        else:
            if current_words:
                chunks.append(" ".join(current_words))
            current_words = [w]
            current_bytes = w_bytes
        if len(chunks) >= max_chunks:
            break
    if current_words and len(chunks) < max_chunks:
        chunks.append(" ".join(current_words))
    return chunks if chunks else ["Aucun synopsis disponible."]


def _movie_bokeh_background(home: pathlib.Path, section_id: str, artwork: pathlib.Path) -> pathlib.Path | None:
    """Build the validated movie-detail Bokeh: centered cover crop, blur 44, dark veil alpha 105."""
    try:
        from PIL import Image, ImageFilter, ImageOps
        source = artwork.resolve(strict=True)
        if not source.is_file():
            return None
        target_dir = home / ".cache/openhtpc/media/movie-detail-bokeh"
        target_dir.mkdir(parents=True, exist_ok=True)
        # Recipe is encoded in the filename so a visual-contract change can never
        # silently reuse an older cached rendition.
        target = target_dir / f"{section_id}-b44-a105.jpg"
        if target.is_file() and target.stat().st_mtime_ns >= source.stat().st_mtime_ns:
            return target
        with Image.open(source) as image:
            image = image.convert("RGB")
            image = ImageOps.fit(image, (1920, 1080), method=Image.Resampling.LANCZOS, centering=(0.5, 0.5))
            image = image.filter(ImageFilter.GaussianBlur(radius=44))
            base = image.convert("RGBA")
            veil = Image.new("RGBA", base.size, (0, 0, 0, 105))
            image = Image.alpha_composite(base, veil).convert("RGB")
            with tempfile.NamedTemporaryFile(dir=target_dir, prefix=f".{section_id}-", suffix=".jpg", delete=False) as tmp:
                tmp_path = pathlib.Path(tmp.name)
            image.save(tmp_path, format="JPEG", quality=84, optimize=True)
            os.replace(tmp_path, target)
        return target
    except Exception:
        return None


def _format_media_technical(info: dict[str, Any] | None) -> str:
    if not info:
        return ""
    parts: list[str] = []
    container = str(info.get("container") or "").lower()
    if "matroska" in container or "webm" in container:
        parts.append("MKV")
    elif container:
        parts.append(container.split(",", 1)[0].upper())
    codec = str(info.get("video_codec") or "").lower()
    codec_labels = {"mpeg2video": "MPEG-2", "mpeg2": "MPEG-2", "h264": "H.264", "hevc": "HEVC", "h265": "HEVC", "av1": "AV1", "vp9": "VP9"}
    if codec:
        parts.append(codec_labels.get(codec, codec.upper()))
    width, height = info.get("width"), info.get("height")
    if width and height:
        parts.append(f"{width}×{height}")
    fps = info.get("fps")
    if fps:
        parts.append(f"{fps:g} fps")
    audio_codec = str(info.get("audio_codec") or "").lower()
    audio_labels = {"ac3": "AC-3", "eac3": "E-AC-3", "dts": "DTS", "truehd": "TrueHD", "aac": "AAC", "flac": "FLAC"}
    channels = info.get("audio_channels")
    if audio_codec:
        audio = audio_labels.get(audio_codec, audio_codec.upper())
        if channels:
            audio += " 5.1" if int(channels) == 6 else " 7.1" if int(channels) == 8 else f" {channels} ch"
        parts.append(audio)
    langs = list(info.get("audio_languages") or [])
    if langs:
        parts.append("Audio " + "/".join(langs[:6]))
    subs = list(info.get("subtitle_languages") or [])
    if subs:
        parts.append("ST " + "/".join(subs[:8]))
    return " · ".join(parts)


def _build_movie_detail_section(
    section_id: str,
    token: str,
    stem: str,
    ext: str,
    ident: dict[str, Any] | None,
    pres_info: dict[str, Any] | None,
    item_icon: pathlib.Path,
    entry_icon: pathlib.Path,
    res_menu: str,
    background_image: pathlib.Path | None = None,
    technical_info: dict[str, Any] | None = None,
) -> str:
    """Construct one hermetic native movie detail [MEDIA_D...] section."""
    lines: list[str] = [
        f"[{section_id}]",
        "Layout=MovieDetail",
    ]
    if background_image is not None:
        lines.append(f"BackgroundImage={background_image}")
    play_cmd = f":tracked $HOME/.local/lib/openhtpc/openhtpc-play {token}"

    # Determine presentation validity
    is_unmatched = (ident is None) or (ident.get("work_id") is None) or (ident.get("identification_state") == "UNMATCHED")
    is_malformed = False
    if pres_info is not None:
        raw_payload = pres_info.get("payload_json")
        if raw_payload:
            try:
                parsed_payload = json.loads(raw_payload)
                if not isinstance(parsed_payload, dict):
                    is_malformed = True
            except Exception:
                is_malformed = True
        disp_title_val = pres_info.get("display_title")
        if disp_title_val is not None and not isinstance(disp_title_val, str):
            is_malformed = True
        overview_val = pres_info.get("overview")
        if overview_val is not None and not isinstance(overview_val, str):
            is_malformed = True

    # 1. Poster property
    lines.append(f"Poster={item_icon}")

    # 2. Title & Original Title properties
    disp_title = ""
    disp_orig = ""
    if not is_unmatched and not is_malformed and pres_info and isinstance(pres_info.get("display_title"), str) and pres_info["display_title"].strip():
        disp_title = ini_value(pres_info["display_title"]).strip()
        if isinstance(pres_info.get("display_original_title"), str):
            disp_orig = ini_value(pres_info["display_original_title"]).strip()
    elif not is_unmatched and ident and isinstance(ident.get("title"), str) and ident["title"].strip():
        disp_title = ini_value(ident["title"]).strip()
        if isinstance(ident.get("original_title"), str):
            disp_orig = ini_value(ident["original_title"]).strip()
    else:
        disp_title = ini_value(stem).strip() or "Vidéo"

    while len(f"Title={disp_title}".encode("utf-8")) > 155:
        disp_title = disp_title[:-1].rstrip()
    lines.append(f"Title={disp_title}")

    if disp_orig and disp_orig.casefold() != disp_title.casefold():
        while len(f"OriginalTitle={disp_orig}".encode("utf-8")) > 155:
            disp_orig = disp_orig[:-1].rstrip()
        lines.append(f"OriginalTitle={disp_orig}")

    # 3. Metadata property
    meta_parts: list[str] = []
    if not is_unmatched and not is_malformed:
        yr = None
        if pres_info and pres_info.get("release_date"):
            yr = _extract_year(pres_info["release_date"], ident.get("year") if ident else None)
        elif ident and ident.get("year"):
            yr = _extract_year(None, ident["year"])
        if yr:
            meta_parts.append(yr)

        if pres_info and pres_info.get("runtime_minutes") is not None:
            rt = _format_runtime(pres_info["runtime_minutes"])
            if rt:
                meta_parts.append(rt)

        if pres_info and pres_info.get("genres_json"):
            gn = _format_genres(pres_info["genres_json"])
            if gn:
                meta_parts.append(gn)

    technical_label = _format_media_technical(technical_info)
    if technical_label:
        meta_parts.append(technical_label)

    if meta_parts:
        meta_label = " · ".join(meta_parts)
    else:
        tech_ext = ext[1:].upper() if ext else "FICHIER VIDÉO"
        if not is_unmatched and ident and ident.get("year"):
            meta_label = f"{ident['year']} · {tech_ext}"
        elif is_unmatched:
            meta_label = "Média local non identifié"
        else:
            meta_label = tech_ext

    while len(f"Metadata={meta_label}".encode("utf-8")) > 198:
        meta_label = meta_label[:-1].rstrip()
    lines.append(f"Metadata={meta_label}")

    # 4. Synopsis properties (Synopsis1..N)
    if is_unmatched:
        raw_synopsis = "Fichier local non identifié."
    elif is_malformed:
        raw_synopsis = "Présentation non disponible."
    elif pres_info is not None:
        overview = pres_info.get("overview")
        if isinstance(overview, str) and overview.strip():
            raw_synopsis = overview
        else:
            raw_synopsis = "Aucun synopsis disponible."
    elif ident and ident.get("work_id"):
        raw_synopsis = "Aucun synopsis disponible."
    else:
        raw_synopsis = "Présentation non disponible."

    synopsis_chunks = _chunk_synopsis_properties(raw_synopsis, max_chunk_bytes=135, max_chunks=16)
    for idx, chunk in enumerate(synopsis_chunks, 1):
        lines.append(f"Synopsis{idx}={chunk}")

    # 5. Exactly three focusable action entries:
    # Entry 1: LIRE LE FILM
    lines.append(bounded_flex_entry(1, "LIRE LE FILM", item_icon, play_cmd))

    # Entry 2: CHANGER L’IDENTIFICATION / IDENTIFIER LE FILM
    if is_unmatched:
        ident_label = "IDENTIFIER LE FILM"
    else:
        ident_label = "CHANGER L’IDENTIFICATION"
    lines.append(bounded_flex_entry(2, ident_label, entry_icon, f":submenu {res_menu}"))

    # Entry 3: RETOUR
    lines.append(bounded_flex_entry(3, "RETOUR", entry_icon, ":back"))

    return "\n".join(lines)


def media_menu_sections(home: pathlib.Path, sources: list[pathlib.Path], icon: pathlib.Path, generation: str = "test-generation", manifest_target: pathlib.Path | None = None) -> tuple[str, str]:
    """Build a bounded complete media graph before the persistent Flex starts."""
    sections: list[str] = []
    actions: dict[str, dict] = {}
    unmatched_entries: list[tuple[str, pathlib.Path, str]] = []
    unmatched_resources: list[tuple[int, str, str]] = []
    generated_detail_ids: set[str] = set()
    source_roots: dict[str, pathlib.Path] = {}
    visited: set[pathlib.Path] = set(); inventory=[]
    install = home / ".local/lib/openhtpc"
    picker_bin = install / "openhtpc-media-picker"
    remove_bin = install / "openhtpc-media-remove"
    # MEDIA root visual language: each action gets a distinct semantic icon.
    media_ui = home / ".local/lib/openhtpc/assets/ui"
    update_icon = media_ui / "system-processing.png"
    library_icon = media_ui / "media.png"
    add_icon = media_ui / "folder.png"
    review_icon = media_ui / "diagnostic.png"
    back_icon = media_ui / "system-back.png"
    folder_icon = media_ui / "folder.png"
    remove_icon = home / ".local/lib/openhtpc/flex/assets/icons/drive-empty.png"

    # Short icon symlinks for line buffer economy (libinih INI_MAX_LINE 200)
    uid = os.getuid()
    short_icon = pathlib.Path(f"/tmp/ohtpc-{uid}-m.png")
    try:
        if short_icon.is_symlink() or short_icon.is_file():
            short_icon.unlink(missing_ok=True)
        short_icon.symlink_to(icon)
        entry_icon = short_icon
    except OSError:
        entry_icon = icon

    short_remove_icon = pathlib.Path(f"/tmp/ohtpc-{uid}-d.png")
    try:
        if short_remove_icon.is_symlink() or short_remove_icon.is_file():
            short_remove_icon.unlink(missing_ok=True)
        short_remove_icon.symlink_to(remove_icon)
        effective_remove_icon = short_remove_icon
    except OSError:
        effective_remove_icon = remove_icon

    # Preload identity map from media.db if present (single read-only pass)
    media_db_path = home / ".local/share/openhtpc/media/media.db"
    identity_map: dict[tuple[str, str], dict[str, Any]] = {}
    technical_map: dict[tuple[str, str], dict[str, Any]] = {}
    work_posters: dict[int, pathlib.Path] = {}
    library_summary: tuple[int, int, int] | None = None
    configured_source_ids: set[str] = set()
    for source in sources:
        try:
            canonical_source = source.resolve(strict=True)
        except OSError:
            continue
        if canonical_source.is_dir():
            configured_source_ids.add(media_source_id(canonical_source))
    if media_db_path.is_file():
        pres_map: dict[int, dict[str, Any]] = {}
        try:
            import sqlite3
            with sqlite3.connect(f"file:{media_db_path}?mode=ro", uri=True) as db:
                rows = db.execute(
                    """
                    SELECT r.source_id, r.relative_path, r.media_version_id,
                           mv.identification_state, mv.match_locked, mv.work_id,
                           w.title, w.year, w.original_title,
                           (SELECT COUNT(*) FROM match_candidates mc WHERE mc.media_version_id = mv.id AND mc.status = 'PENDING') AS cand_count
                    FROM resources r
                    JOIN media_versions mv ON mv.id = r.media_version_id
                    LEFT JOIN works w ON w.id = mv.work_id
                    """
                ).fetchall()
                for r in rows:
                    identity_map[(r[0], r[1])] = {
                        "media_version_id": r[2],
                        "identification_state": r[3],
                        "match_locked": r[4],
                        "work_id": r[5],
                        "title": r[6],
                        "year": r[7],
                        "original_title": r[8],
                        "candidate_count": r[9] or 0,
                    }

                lang_labels = {"fre": "FR", "fra": "FR", "fr": "FR", "eng": "EN", "en": "EN", "ita": "IT", "it": "IT", "dut": "NL", "nld": "NL", "spa": "ES", "por": "PT", "ara": "AR", "deu": "DE", "ger": "DE"}
                resource_rows = db.execute("SELECT id, source_id, relative_path, container_format FROM resources WHERE resource_kind='FILE' AND source_id IS NOT NULL AND relative_path IS NOT NULL").fetchall()
                for rr in resource_rows:
                    rid, sid, rel, container = rr
                    v = db.execute("SELECT codec,width,height,frame_rate_num,frame_rate_den FROM video_streams WHERE resource_id=? ORDER BY stream_index LIMIT 1", (rid,)).fetchone()
                    aud = db.execute("SELECT codec,channels,language FROM audio_streams WHERE resource_id=? ORDER BY is_default DESC,stream_index", (rid,)).fetchall()
                    sub = db.execute("SELECT language FROM subtitle_streams WHERE resource_id=? ORDER BY is_default DESC,stream_index", (rid,)).fetchall()
                    audio_langs: list[str] = []
                    for row in aud:
                        code = lang_labels.get(str(row[2] or '').lower(), str(row[2] or '').upper())
                        if code and code not in audio_langs: audio_langs.append(code)
                    sub_langs: list[str] = []
                    for row in sub:
                        code = lang_labels.get(str(row[0] or '').lower(), str(row[0] or '').upper())
                        if code and code not in sub_langs: sub_langs.append(code)
                    fps = None
                    if v and v[3] and v[4]:
                        try: fps = float(v[3]) / float(v[4])
                        except (TypeError, ValueError, ZeroDivisionError): fps = None
                    technical_map[(sid, rel)] = {
                        "container": container,
                        "video_codec": v[0] if v else None, "width": v[1] if v else None, "height": v[2] if v else None, "fps": fps,
                        "audio_codec": aud[0][0] if aud else None, "audio_channels": aud[0][1] if aud else None,
                        "audio_languages": audio_langs, "subtitle_languages": sub_langs,
                    }

                if configured_source_ids:
                    placeholders = ",".join("?" for _ in configured_source_ids)
                    summary_row = db.execute(
                        f"""
                        SELECT
                            COUNT(DISTINCT mv.id),
                            COUNT(DISTINCT CASE
                                WHEN mv.identification_state IN ('AUTO_MATCHED', 'USER_MATCHED')
                                THEN mv.id END),
                            COUNT(DISTINCT CASE
                                WHEN mv.identification_state = 'UNMATCHED'
                                THEN mv.id END)
                        FROM media_versions mv
                        JOIN resources r ON r.media_version_id = mv.id
                        WHERE r.resource_kind = 'FILE'
                          AND r.availability_status = 'AVAILABLE'
                          AND r.source_id IN ({placeholders})
                        """,
                        tuple(sorted(configured_source_ids)),
                    ).fetchone()
                    if summary_row is not None:
                        total, identified, review = (int(value or 0) for value in summary_row)
                        if total >= 0 and identified >= 0 and review >= 0 and identified + review <= total:
                            library_summary = (total, identified, review)

                unmatched_resources = db.execute(
                    """
                    SELECT mv.id, r.source_id, r.relative_path
                    FROM media_versions mv
                    JOIN resources r ON r.media_version_id = mv.id
                    WHERE mv.identification_state = 'UNMATCHED'
                      AND r.resource_kind = 'FILE'
                      AND r.availability_status = 'AVAILABLE'
                      AND r.source_id IS NOT NULL
                      AND r.relative_path IS NOT NULL
                    ORDER BY mv.id, r.source_id, r.relative_path, r.id
                    """
                ).fetchall()

                # DEV6B2 / DEV6B3: Batch presentation lookup for fr-FR movie posters & details
                # Provenance chain: work_presentations -> provider_snapshots -> external_ids
                pres_rows = db.execute(
                    """
                    SELECT wp.work_id, ps.payload_json,
                           wp.display_title, wp.display_original_title,
                           wp.release_date, wp.runtime_minutes,
                           wp.overview, wp.genres_json
                    FROM work_presentations wp
                    JOIN provider_snapshots ps ON ps.id = wp.source_snapshot_id
                    JOIN external_ids e ON e.id = ps.external_id_id
                    WHERE wp.locale = 'fr-FR'
                      AND ps.snapshot_kind = 'MOVIE_DETAILS'
                      AND ps.locale = 'fr-FR'
                      AND e.provider = 'tmdb_movie'
                      AND e.work_id = wp.work_id
                    """
                ).fetchall()
                for r in pres_rows:
                    pres_map[r[0]] = {
                        "payload_json": r[1],
                        "display_title": r[2],
                        "display_original_title": r[3],
                        "release_date": r[4],
                        "runtime_minutes": r[5],
                        "overview": r[6],
                        "genres_json": r[7],
                    }
        except Exception:
            identity_map = {}
            pres_map = {}
            unmatched_resources = []

        distinct_work_ids = {info["work_id"] for info in identity_map.values() if info.get("work_id") is not None}
        for wid in distinct_work_ids:
            pres_info = pres_map.get(wid)
            payload_json = pres_info.get("payload_json") if pres_info else None
            poster_link = _project_work_poster(home, wid, payload_json, uid)
            if poster_link is not None:
                work_posters[wid] = poster_link

    # Load UI helper for resolver menu construction
    match_ui = None
    ui_script = install / "openhtpc-media-match-ui"
    if not ui_script.is_file():
        ui_script = pathlib.Path(__file__).resolve().parent / "openhtpc-media-match-ui"
    if ui_script.is_file():
        try:
            import importlib.machinery
            loader = importlib.machinery.SourceFileLoader("openhtpc_media_match_ui", str(ui_script))
            spec = importlib.util.spec_from_loader("openhtpc_media_match_ui", loader)
            if spec and spec.loader:
                match_ui = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(match_ui)
        except Exception:
            match_ui = None

    def section_for(folder: pathlib.Path, source_root: pathlib.Path, source_id: str, depth: int = 0) -> str | None:
        try: resolved = folder.resolve(strict=True)
        except OSError: return None
        if resolved in visited or len(visited) >= 64 or depth > 3: return None
        visited.add(resolved); name = menu_name("MEDIA", resolved)
        entries = [("RETOUR", icon, ":back")]
        try:
            with os.scandir(resolved) as scanner:
                items = sorted(list(scanner), key=lambda it: it.name.casefold())
        except OSError:
            items = []
        for item in items:
            try:
                if item.is_dir(follow_symlinks=True):
                    child_path = pathlib.Path(item.path)
                    target = section_for(child_path, source_root, source_id, depth + 1)
                    if target:
                        relative = child_path.relative_to(source_root)
                        item_id = media_item_id(source_id, relative, "directory")
                        token = media_action_token(generation, item_id)
                        actions[token] = {"page_id": name, "item_type": "directory", "source_id": source_id, "relative_path": relative.as_posix(), "semantic_id": item_id}
                        entries.append(("DOSSIER — " + ini_value(item.name), folder_icon, f":submenu {target}"))
                elif item.is_file(follow_symlinks=True):
                    ext = os.path.splitext(item.name)[1].casefold()
                    if ext in VIDEO_EXTENSIONS:
                        child_path = pathlib.Path(item.path)
                        relative = child_path.relative_to(source_root)
                        item_id = media_item_id(source_id, relative, "file")
                        token = media_action_token(generation, item_id)
                        detail_menu = f"MEDIA_D{item_id[:8]}"
                        actions[token] = {"page_id": detail_menu, "parent_page_id": name, "item_type": "file", "source_id": source_id, "relative_path": relative.as_posix(), "semantic_id": item_id}
                        stem = os.path.splitext(item.name)[0]
                        ident = identity_map.get((source_id, relative.as_posix()))
                        mv_id = ident.get("media_version_id") if ident else None
                        state = ident.get("identification_state") if ident else "UNMATCHED"
                        work_id = ident.get("work_id") if ident else None
                        title_source = stem
                        if state in ("AUTO_MATCHED", "USER_MATCHED") and work_id is not None:
                            presentation = pres_map.get(work_id)
                            title_source = (presentation.get("display_title") if presentation else None) or ident.get("title") or stem
                        title = ini_value(title_source)
                        if len(title) > 72: title = title[:69].rstrip() + "…"

                        item_icon = work_posters.get(work_id) if state in ("AUTO_MATCHED", "USER_MATCHED") and work_id is not None else None
                        if item_icon is None:
                            item_icon = entry_icon

                        if state == "AUTO_MATCHED":
                            context_title = "CONFIRMER / CHANGER L’IDENTIFICATION"
                        elif state == "USER_MATCHED":
                            context_title = "CHANGER L’IDENTIFICATION"
                        else:
                            context_title = "IDENTIFIER LE FILM"

                        res_menu = f"MEDIA_R{item_id[:8]}"
                        context_cmd = f":submenu {res_menu}"

                        res_secs = None
                        if match_ui and mv_id is not None and media_db_path.is_file():
                            try:
                                import sqlite3
                                with sqlite3.connect(f"file:{media_db_path}?mode=ro", uri=True) as db:
                                    res_secs = match_ui.build_resolver_menu_sections(
                                        home=home,
                                        install=install,
                                        db=db,
                                        media_version_id=mv_id,
                                        res_section_id=res_menu,
                                        generation=generation,
                                        actions=actions,
                                        icon=entry_icon,
                                    )
                                    if res_secs:
                                        sections.extend(res_secs)
                            except Exception:
                                res_secs = None
                        if not res_secs:
                            token_suffix = item_id[:8]
                            search_helper_path = "$HOME/.local/lib/openhtpc/openhtpc-media-manual-search-ui"
                            ms_menu = f"MEDIA_MS_{token_suffix}"
                            ms_cmd = f":submenu {ms_menu}"
                            ms_launch_cmd = f":applyback {search_helper_path} --token {token}"
                            ms_e1 = bounded_flex_entry(1, "LANCER LA RECHERCHE", entry_icon, ms_launch_cmd)
                            ms_e2 = bounded_flex_entry(2, "RETOUR", entry_icon, ":back")
                            ms_sec = f"[{ms_menu}]\n{ms_e1}\n{ms_e2}"

                            r_e1 = bounded_flex_entry(1, "RECHERCHER MANUELLEMENT", entry_icon, ms_cmd)
                            r_e2 = bounded_flex_entry(2, "Aucune proposition disponible.", entry_icon, ":back")
                            r_e3 = bounded_flex_entry(3, "RETOUR", entry_icon, ":back")
                            res_sec = f"[{res_menu}]\n{r_e1}\n{r_e2}\n{r_e3}"

                            sections.append(res_sec)
                            sections.append(ms_sec)

                        detail_menu = f"MEDIA_D{item_id[:8]}"
                        fallback_bokeh = install / "assets/branding/openhtpc-wallpaper.png"
                        bokeh_source = item_icon if item_icon != entry_icon else (fallback_bokeh if fallback_bokeh.is_file() else entry_icon)
                        detail_background = _movie_bokeh_background(home, detail_menu, bokeh_source)
                        detail_sec = _build_movie_detail_section(
                            section_id=detail_menu,
                            token=token,
                            stem=stem,
                            ext=ext,
                            ident=ident,
                            pres_info=pres_map.get(work_id) if work_id is not None else None,
                            item_icon=item_icon,
                            entry_icon=entry_icon,
                            res_menu=res_menu,
                            background_image=detail_background,
                            technical_info=technical_map.get((source_id, relative.as_posix())),
                        )
                        sections.append(detail_sec)
                        generated_detail_ids.add(detail_menu)

                        parent_cmd = f":submenu {detail_menu}"
                        label = f"{title}  ·  {ext[1:].upper()}"
                        entries.append((label, item_icon, parent_cmd, context_cmd, context_title))
            except OSError:
                continue
        if resolved == source_root.resolve():
            entries.append(("RETIRER CETTE SOURCE D'OPENHTPC", effective_remove_icon, f"$HOME/.local/lib/openhtpc/openhtpc-media-remove \"{str(source_root)}\""))
        body_entries = []
        for i, entry_tuple in enumerate(entries, 1):
            if len(entry_tuple) == 5:
                lbl, ico, cmd, c_cmd, c_title = entry_tuple
                body_entries.append(bounded_flex_entry(i, lbl, ico, cmd, c_cmd, c_title))
            else:
                lbl, ico, cmd = entry_tuple
                body_entries.append(bounded_flex_entry(i, lbl, ico, cmd))
        body = "\n".join(body_entries)
        sections.append(f"[{name}]\n{body}")
        return name

    has_indexed_media = library_summary is not None and library_summary[0] > 0
    if not sources:
        roots = [("+ AJOUTER UNE SOURCE MÉDIA", add_icon, f"{picker_bin}")]
    else:
        update_label = "METTRE À JOUR LA MÉDIATHÈQUE" if has_indexed_media else "ANALYSER MES MÉDIAS"
        roots = [(update_label, update_icon, f":fork {install / 'openhtpc-media-update-request'}")]
        if has_indexed_media:
            total, identified, review = library_summary
            roots.append((
                f"MÉDIATHÈQUE — {total} médias · {identified} identifiés · {review} à vérifier",
                library_icon,
                ":fork true",
            ))
        for source in sources:
            try:canonical=source.resolve(strict=True)
            except OSError:canonical=None
            sid=media_source_id(canonical) if canonical is not None else media_source_id(source)
            target = section_for(canonical,canonical,sid) if canonical is not None and canonical.is_dir() else None
            if canonical is not None and canonical.is_dir():
                source_roots[sid] = canonical
            inventory.append({"source_id":sid,"configured_path":str(source),"canonical_path":str(canonical) if canonical is not None else None})
            source_name = ini_value(source.name or str(source))
            if target and canonical is not None:
                label = f"{source_name}  ·  {_source_kind_label(canonical)}"
                roots.append((label, folder_icon, f":submenu {target}"))
            else:
                label = f"{source_name}  ·  INDISPONIBLE"
                context_cmd = f"$HOME/.local/lib/openhtpc/openhtpc-media-remove \"{str(source)}\""
                roots.append((label, folder_icon, ":fork true", context_cmd, "RETIRER LA SOURCE"))
        roots.append(("+ AJOUTER UNE SOURCE", add_icon, f"{picker_bin}"))

    # The unmatched view is sourced from the DB, independent of the bounded folder graph.
    unmatched_ids: set[int] = set()
    for mv_id, source_id, relative_path in unmatched_resources:
        if (type(mv_id) is not int or type(source_id) is not str
                or type(relative_path) is not str
                or mv_id in unmatched_ids or source_id not in source_roots):
            continue
        relative = pathlib.PurePosixPath(relative_path)
        if (relative.is_absolute() or not relative.parts
                or any(part in ("", ".", "..") for part in relative.parts)):
            continue
        root = source_roots[source_id]
        try:
            physical = root.joinpath(*relative.parts).resolve(strict=True)
            if root not in physical.parents or not physical.is_file():
                continue
        except (OSError, RuntimeError):
            continue
        ext = relative.suffix.casefold()
        if ext not in VIDEO_EXTENSIONS:
            continue

        item_id = media_item_id(source_id, relative, "file")
        token = media_action_token(generation, item_id)
        detail_menu = f"MEDIA_D{item_id[:8]}"
        res_menu = f"MEDIA_R{item_id[:8]}"
        if detail_menu not in generated_detail_ids:
            actions[token] = {"page_id": detail_menu, "parent_page_id": "MEDIA_UNMATCHED",
                              "item_type": "file", "source_id": source_id,
                              "relative_path": relative.as_posix(), "semantic_id": item_id}
            res_secs = None
            if match_ui:
                try:
                    import sqlite3
                    with sqlite3.connect(f"file:{media_db_path}?mode=ro", uri=True) as db:
                        res_secs = match_ui.build_resolver_menu_sections(
                            home=home, install=install, db=db, media_version_id=mv_id,
                            res_section_id=res_menu, generation=generation,
                            actions=actions, icon=entry_icon,
                        )
                        if res_secs:
                            sections.extend(res_secs)
                except Exception:
                    res_secs = None
            if not res_secs:
                search_helper_path = "$HOME/.local/lib/openhtpc/openhtpc-media-manual-search-ui"
                ms_menu = f"MEDIA_MS_{item_id[:8]}"
                sections.append(f"[{res_menu}]\n" + "\n".join([
                    bounded_flex_entry(1, "RECHERCHER MANUELLEMENT", entry_icon, f":submenu {ms_menu}"),
                    bounded_flex_entry(2, "Aucune proposition disponible.", entry_icon, ":back"),
                    bounded_flex_entry(3, "RETOUR", entry_icon, ":back"),
                ]))
                sections.append(f"[{ms_menu}]\n" + "\n".join([
                    bounded_flex_entry(1, "LANCER LA RECHERCHE", entry_icon,
                                       f":applyback {search_helper_path} --token {token}"),
                    bounded_flex_entry(2, "RETOUR", entry_icon, ":back"),
                ]))
            fallback_bokeh = install / "assets/branding/openhtpc-wallpaper.png"
            unmatched_background = _movie_bokeh_background(
                home, detail_menu, fallback_bokeh if fallback_bokeh.is_file() else entry_icon
            )
            sections.append(_build_movie_detail_section(
                section_id=detail_menu, token=token, stem=relative.stem, ext=ext,
                ident={"media_version_id": mv_id, "identification_state": "UNMATCHED",
                       "work_id": None},
                pres_info=None, item_icon=entry_icon, entry_icon=entry_icon,
                res_menu=res_menu, background_image=unmatched_background,
                technical_info=technical_map.get((source_id, relative.as_posix())),
            ))
            generated_detail_ids.add(detail_menu)

        title = ini_value(relative.stem)
        if len(title) > 72:
            title = title[:69].rstrip() + "…"
        ident = identity_map.get((source_id, relative.as_posix()))
        candidate_count = ident.get("candidate_count", 0) if ident else 0
        if type(candidate_count) is not int or candidate_count < 0:
            candidate_count = 0
        if candidate_count == 1:
            hint = "1 proposition"
        elif candidate_count > 1:
            hint = f"{candidate_count} propositions"
        else:
            hint = "À rechercher"
        unmatched_entries.append((
            f"{hint}  ·  {title}",
            entry_icon,
            f":submenu {detail_menu}",
        ))
        unmatched_ids.add(mv_id)

    if unmatched_entries:
        unmatched_body = "\n".join([
            bounded_flex_entry(1, "RETOUR", icon, ":back"),
            *(bounded_flex_entry(i, label, item_icon, command)
              for i, (label, item_icon, command) in enumerate(unmatched_entries, 2)),
        ])
        sections.append(f"[MEDIA_UNMATCHED]\n{unmatched_body}")
        roots.append((f"À identifier — {len(unmatched_entries)}", review_icon, ":submenu MEDIA_UNMATCHED"))

    roots.append(("RETOUR À OPENHTPC", back_icon, ":back"))
    root_entries = []
    for i, entry_tuple in enumerate(roots, 1):
        if len(entry_tuple) == 5:
            label, entry_icon_root, command, context_cmd, context_title = entry_tuple
            root_entries.append(f"Entry{i}={label};{entry_icon_root};{command};{context_cmd};{context_title}")
        else:
            label, entry_icon_root, command = entry_tuple
            root_entries.append(f"Entry{i}={label};{entry_icon_root};{command}")
    root_body = "\n".join(root_entries)

    write_media_model_state(home,generation,inventory,actions,manifest_target)
    return "MEDIA_ROOT", "\n\n".join([f"[MEDIA_ROOT]\n{root_body}", *reversed(sections)])


def bounded_flex_entry(
    index: int,
    label: str,
    icon: pathlib.Path,
    command: str,
    context_cmd: str | None = None,
    context_title: str | None = None,
    max_bytes: int = 198,
) -> str:
    """Serialize an Entry line that fits in Flex/inih's 200-byte input buffer."""
    prefix = f"Entry{index}="
    if context_cmd is not None and context_title is not None:
        suffix = f";{icon};{command};{context_cmd};{context_title}"
    else:
        suffix = f";{icon};{command}"
    budget = max_bytes - len(prefix.encode("utf-8")) - len(suffix.encode("utf-8"))
    if budget < 1:
        if context_cmd is not None and context_title is not None:
            suffix = f";{icon};{command}"
            budget = max_bytes - len(prefix.encode("utf-8")) - len(suffix.encode("utf-8"))
        if budget < 1:
            raise ValueError("Flex entry metadata exceeds parser line limit")
    encoded = label.encode("utf-8")
    if len(encoded) > budget:
        ellipsis = "…"
        media_suffix = ""
        if "  ·  " in label:
            parts = label.split("  ·  ")
            if len(parts) >= 3:
                head = "  ·  ".join(parts[:-2])
                media_suffix = "  ·  " + "  ·  ".join(parts[-2:])
            else:
                head, tail = parts
                media_suffix = f"  ·  {tail}"
            encoded = head.encode("utf-8")
        reserved = len((ellipsis + media_suffix).encode("utf-8"))
        if budget < reserved:
            media_suffix = ""
            reserved = len(ellipsis.encode("utf-8"))
        encoded = encoded[:max(0, budget - reserved)]
        while True:
            try:
                label = encoded.decode("utf-8").rstrip() + ellipsis + media_suffix
                break
            except UnicodeDecodeError:
                encoded = encoded[:-1]
    line = prefix + label + suffix
    if len(line.encode("utf-8")) > max_bytes:
        raise ValueError("Flex entry exceeds parser line limit")
    return line


def protected_optical_menu_policy(home: pathlib.Path, install: pathlib.Path, optical: dict) -> tuple[str, dict, dict]:
    """Resolve protected-optical exposure through the production plugin authority."""
    neutral = {"owned": False, "visible": False, "enabled": False, "action_intent": "NONE"}
    try:
        core_path = install / "openhtpc-core.py"
        spec = importlib.util.spec_from_file_location("openhtpc_menu_p2_core", core_path)
        core = importlib.util.module_from_spec(spec); spec.loader.exec_module(core)
        registry = core.plugin_status(home, install)
        snapshot = _optical_model.protected_capability(home)
        _, decision = core.protected_optical_playback_decision_projection(home, install, registry, optical, snapshot)
        _, presentation = core.optical_presentation_descriptor(home, install, registry, optical)
        authority, contribution = core.protected_optical_ui_contribution(home, install, registry, presentation, decision)
        return authority, contribution, decision
    except (OSError, ImportError, AttributeError, TypeError, ValueError, SystemExit):
        return "PLUGIN_UNAVAILABLE", neutral, {"playback_action": "DISABLED", "playback_reason": "PLUGIN_BROKEN", "protection": optical.get("protection", "UNKNOWN")}



def disc_menu_entries(optical: dict, install: pathlib.Path, icons: tuple[pathlib.Path, pathlib.Path, pathlib.Path, pathlib.Path], home: pathlib.Path | None = None) -> str:
    state = _optical_model.canonical_state(optical); media = _optical_model.presentation(optical); entries = []
    play_icon, tmdb_icon, eject_icon, back_icon = icons
    play_action = install / "assets/ui/media.png"
    media_play_icon = play_action if play_action.is_file() else play_icon
    eject_action = install / "assets/ui/eject.png"
    action_eject_icon = eject_action if eject_action.is_file() else eject_icon
    back_action = install / "assets/ui/system-back.png"
    action_back_icon = back_action if back_action.is_file() else back_icon
    video_action = install / "assets/ui/system-processing.png"
    if not video_action.is_file():
        video_action = install / "assets/ui/traitement_video.png"
    video_icon = video_action if video_action.is_file() else play_icon
    diag_action = install / "assets/ui/diagnostic.png"
    if not diag_action.is_file():
        diag_action = install / "assets/ui/system-diagnostics.png"
    diagnostic_icon = diag_action if diag_action.is_file() else play_icon
    decision = _optical_model.playback_decision(optical, _optical_model.protected_capability(home)) if home else _optical_model.playback_decision(optical, {})
    ui_authority, ui_contribution = "CORE_FALLBACK", {"visible": False, "enabled": False, "action_intent": "NONE"}
    if state in {"BLURAY_VIDEO","UHD_BLURAY_VIDEO","BLURAY_FAMILY"} and home:
        ui_authority, ui_contribution, decision = protected_optical_menu_policy(home, install, optical)

    core_path = install / "openhtpc-core.py"
    policy = {"unplayable": False}
    if core_path.is_file():
        try:
            spec = importlib.util.spec_from_file_location("openhtpc_menu_p2_core", core_path)
            core = importlib.util.module_from_spec(spec); spec.loader.exec_module(core)
            policy = core.resolve_protected_optical_policy(home, install, optical, _optical_model.protected_capability(home) if home else {})
        except Exception:
            policy = {"unplayable": False}
    is_protected_unplayable = bool(policy.get("unplayable"))

    has_token = bool(home and (home / ".config/openhtpc/secrets/tmdb-token").is_file())
    cached_meta = {}
    if home:
        tmdb_path = install / "openhtpc-tmdb.py"
        if tmdb_path.is_file():
            try:
                spec = importlib.util.spec_from_file_location("openhtpc_menu_tmdb", tmdb_path)
                tmdb_model = importlib.util.module_from_spec(spec); spec.loader.exec_module(tmdb_model)
                query = normalized_disc_title(optical.get("tmdb_title") or optical.get("disc_title") or optical.get("volume_label"))
                cache_target = tmdb_model.cache_path(home, optical, query)
                if cache_target is not None: cached_meta = load_optional_object(cache_target)
            except (OSError, AttributeError, ImportError, ValueError):
                cached_meta = {}

    meta_status = cached_meta.get("status")
    recovery = install / "openhtpc-tmdb-recovery"
    if meta_status == "AMBIGUOUS":
        disc_id = str(optical.get("disc_id") or "")
        generation = int(optical.get("generation", 0) or 0)
        canonical = state
        query = normalized_disc_title(optical.get("tmdb_title") or optical.get("disc_title") or optical.get("volume_label"))
        bind_script = install / "openhtpc-bind-disc"
        for cand in cached_meta.get("candidates", [])[:3]:
            cid = int(cand.get("tmdb_id") or cand.get("id", 0))
            ctitle = str(cand.get("title") or "Film").strip()
            cyear = str((cand.get("release_date") or "")[:4]).strip()
            runtime_val = cand.get("runtime")
            cdur = ""
            if runtime_val not in (None, "", [], {}):
                try:
                    r_val = float(runtime_val)
                    if r_val > 0:
                        mins = round(r_val / 60) if r_val > 300 else int(r_val)
                        cdur = f"{mins // 60} h {mins % 60:02d}" if mins >= 60 else f"{mins} min"
                except (ValueError, TypeError):
                    pass
            meta_bits = []
            if cyear: meta_bits.append(cyear)
            if cdur: meta_bits.append(cdur)
            meta_str = " • ".join(meta_bits)
            label = f"{ctitle}  ·  {meta_str}" if meta_str else ctitle
            identity_args = (f"--disc-id {shlex.quote(disc_id)}" if disc_id else
                             f"--generation {generation} --canonical-state {shlex.quote(canonical)} --title {shlex.quote(query)}")
            cmd = f":fork {bind_script} {identity_args} --tmdb-id {cid}"
            cand_icon = tmdb_icon
            p_file = cand.get("poster_file")
            if p_file and pathlib.Path(p_file).is_file():
                cand_icon = pathlib.Path(p_file)
            elif cand.get("poster_path") and home:
                p_path = cand.get("poster_path")
                pf = home / ".cache/openhtpc/tmdb" / (hashlib.sha256(p_path.encode()).hexdigest() + ".jpg")
                if pf.is_file() and pf.stat().st_size > 0:
                    cand_icon = pf
            entries.append((label, cand_icon, cmd))
        # Non-candidate dock actions
        if state == "DVD_VIDEO":
            device = shlex.quote(str(optical.get("device") or ""))
            entries.append(("LIRE LE DVD", media_play_icon,
                            f":tracked env OPENHTPC_FLEX_RETAINED=1 {install/'openhtpc-play-dvd'} {device}"))
        elif is_protected_unplayable:
            entries.append(("DIAGNOSTIC", diagnostic_icon, ":submenu SYSTEM_MEDIA_OPTICAL"))
    elif is_protected_unplayable:
        device = shlex.quote(str(optical.get("device") or ""))
        entries.append(("DIAGNOSTIC", diagnostic_icon, ":submenu SYSTEM_MEDIA_OPTICAL"))
        entries.append(("ÉJECTER", action_eject_icon, f":fork env OPENHTPC_RETURN_UI=/bin/true {install/'openhtpc-eject'} {device}" if device else ":fork true"))
        entries.append(("RETOUR", action_back_icon, ":back"))
        return "\n".join(f"Entry{i}={ini_value(label)};{icon};{command}" for i, (label, icon, command) in enumerate(entries, 1))
    else:
        if state == "DVD_VIDEO":
            device = shlex.quote(str(optical.get("device") or ""))
            entries.append(("LIRE LE DVD", media_play_icon,
                            f":tracked env OPENHTPC_FLEX_RETAINED=1 {install/'openhtpc-play-dvd'} {device}"))
        elif optical.get("state") == "INITIALIZING": entries.append(("INITIALISATION DU DISQUE…", media_play_icon, ":fork true"))
        elif state in {"BLURAY_VIDEO","UHD_BLURAY_VIDEO","BLURAY_FAMILY"}:
            pass
        else: entries.append(("AUCUN DISQUE DÉTECTÉ", media_play_icon, ":fork true"))

        if not has_token or meta_status == "NOT_CONFIGURED":
            entries.append(("CONFIGURER TMDb", tmdb_icon, f":fork {install/'openhtpc-configure-tmdb'}"))
        elif meta_status in {"UNAVAILABLE", "AUTH_ERROR", "AUTH_FAILED"}:
            entries.append(("RECONNECTER TMDb", tmdb_icon, f":fork {install/'openhtpc-configure-tmdb'}"))
        elif meta_status == "NO_RESULT":
            entries.append(("RECHERCHE MANUELLE", tmdb_icon, f":fork {recovery}"))

    if state in {"BLURAY_VIDEO","UHD_BLURAY_VIDEO","BLURAY_FAMILY"}:
        media_name = {"BLURAY_VIDEO":"BLU-RAY","UHD_BLURAY_VIDEO":"UHD BLU-RAY","BLURAY_FAMILY":"BLU-RAY / UHD"}[state]
        if ui_authority != "PLUGIN_P2" or not ui_contribution.get("visible"):
            pass
        elif ui_contribution.get("enabled") and ui_contribution.get("action_intent")=="PLAY_CURRENT_OPTICAL_MEDIA":
            device = shlex.quote(str(optical.get("device") or "")); generation = int(optical.get("generation", 0) or 0)
            token = _optical_model.playback_action_token(optical, _optical_model.protected_capability(home) if home else {})
            entries.append((f"LIRE LE {media_name}", media_play_icon,
                            f":tracked {install/'openhtpc-play-optical'} --device {device} --generation {generation} --action-token {token}"))
        elif not is_protected_unplayable:
            reason_labels = {
                "PROTECTION_UNKNOWN":"PROTECTION NON DÉTERMINÉE",
                "MEDIA_TYPE_INDETERMINATE":"TYPE ET PROTECTION NON DÉTERMINÉS",
                "STRUCTURAL_SUPPORT_NOT_AVAILABLE":"SUPPORT STRUCTUREL NON DISPONIBLE",
                "PROTECTED_SUPPORT_NOT_CONFIGURED":"SUPPORT PROTÉGÉ NON CONFIGURÉ",
                "PROTECTED_SUPPORT_NOT_AVAILABLE":"SUPPORT PROTÉGÉ NON DISPONIBLE",
                "PROTECTED_SUPPORT_BLOCKED":"SUPPORT PROTÉGÉ BLOQUÉ",
            }
            entries.append((f"{media_name} · {reason_labels.get(decision['playback_reason'],'LECTURE NON DISPONIBLE')}", media_play_icon, ":fork true"))

    device = shlex.quote(str(optical.get("device") or ""))
    entries.append(("ÉJECTER", action_eject_icon, f":fork env OPENHTPC_RETURN_UI=/bin/true {install/'openhtpc-eject'} {device}" if device else ":fork true"))
    entries.append(("RETOUR", action_back_icon, ":back"))
    return "\n".join(f"Entry{i}={ini_value(label)};{icon};{command}" for i, (label, icon, command) in enumerate(entries, 1))


def optical_navigation_event(previous: dict, current: dict) -> tuple[int, int]:
    """Return generation-scoped (auto-open, eject-home) requests for a live transition."""
    empty = {"DRIVE_PRESENT_NO_MEDIA", "NO_OPTICAL_DRIVE", "DETECTION_INDETERMINATE"}
    old = _optical_model.canonical_state(previous); new = _optical_model.canonical_state(current)
    generation = int(current.get("generation", 0) or 0)
    if generation <= int(previous.get("generation", 0) or 0):
        return (0, 0)
    if old in empty and new not in empty:
        return (generation, 0)
    if old not in empty and new in {"DRIVE_PRESENT_NO_MEDIA", "NO_OPTICAL_DRIVE"}:
        return (0, generation)
    return (0, 0)


def write_live_optical_state(home: pathlib.Path, optical: dict, icon: pathlib.Path,
                             auto_open_generation: int = 0, eject_home_generation: int = 0) -> pathlib.Path:
    # One resolver for every writer: the menu publication resolves the enriched
    # title from the media cache, and the controller's post-publication refresh
    # used to rewrite this file from the raw optical state, silently dropping the
    # title the menu was displaying.
    optical = enriched_optical(home, optical)
    state = optical.get("state"); canonical = _optical_model.canonical_state(optical)
    labels = {"NO_DRIVE":"LECTEUR · AUCUN LECTEUR", "EMPTY":"LECTEUR · Aucun disque",
              "INITIALIZING":"LECTEUR · Initialisation du disque…", "UNKNOWN_DISC":"LECTEUR · DISQUE INCONNU",
              "UNSUPPORTED_IN_V1":"LECTEUR · MÉDIA NON PRIS EN CHARGE"}
    label = optical_home_label(optical) if canonical in {"DVD_VIDEO","BLURAY_VIDEO","UHD_BLURAY_VIDEO","BLURAY_FAMILY","UNKNOWN_OPTICAL_MEDIA"} else labels.get(state, "LECTEUR · ÉTAT INCONNU")
    target = home / ".local/state/openhtpc/flex-optical-state"
    target.parent.mkdir(parents=True, exist_ok=True)
    generation = int(optical.get("generation", 0) or 0)
    auto_open_generation = generation if int(auto_open_generation or 0) == generation else 0
    eject_home_generation = generation if int(eject_home_generation or 0) == generation else 0
    fd, temporary = tempfile.mkstemp(prefix=target.name + ".", dir=target.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            title = normalized_disc_title(optical.get("tmdb_title") or optical.get("disc_title") or optical.get("volume_label"))
            stream.write(ini_value(label) + "\n" + str(icon) + "\n" + str(state or "UNKNOWN") + "\n" +
                         str(optical.get("device") or "") + "\n" + ini_value(title) + "\n" +
                         str(generation) + "\n" + str(auto_open_generation) + "\n" +
                         str(eject_home_generation) + "\n")
            stream.flush(); os.fsync(stream.fileno())
        os.chmod(temporary, 0o600); os.replace(temporary, target)
    finally:
        if os.path.exists(temporary): os.unlink(temporary)
    return target


def enriched_optical(home: pathlib.Path, optical: dict) -> dict:
    """Return ``optical`` with the TMDb title resolved from the media cache.

    The menu publication reads the cache when the canonical optical state
    carries no ``tmdb_title``; the live-state writer must resolve it the same
    way.  Two writers with two resolutions is the defect this replaces: the
    controller's post-publication refresh rewrote flex-optical-state from the
    raw optical state and silently dropped the title the menu was displaying.
    """
    if not optical or _optical_model.canonical_state(optical) != "DVD_VIDEO" or not optical.get("disc_id") or optical.get("tmdb_title"):
        return optical
    cache_target = (home / ".local/share/openhtpc/media-cache/dvd"
                    / hashlib.sha256(str(optical["disc_id"]).encode()).hexdigest() / "metadata.json")
    cached_meta = load_optional_object(cache_target)
    if cached_meta.get("status") == "PASS" and cached_meta.get("title"):
        enriched = dict(optical)
        enriched["tmdb_title"] = cached_meta.get("title")
        return enriched
    return optical


def enrichment_presentation_signature(home: pathlib.Path, st: dict, tmdb=None) -> str:
    """Identity of the metadata/enrichment presentation for one optical state.

    MOVED VERBATIM out of the home controller (2026-10-17, v2): the body, its
    local names and its literals are unchanged, only the module that hosts it.
    The controller calls it through ``disc_presentation_signature()``; keeping one
    implementation lets the controller's trigger and the behavioural interlock
    test execute the same code instead of a copy.  The controller passes the TMDb
    module it has already loaded, so this stays a pure read of one cache file.
    """
    if tmdb is None or not st:
        return ""
    title = st.get("tmdb_title") or st.get("disc_title") or st.get("volume_label") or ""
    cache_target = tmdb.cache_path(home, st, str(title))
    if cache_target is None:
        return ""
    identity = str(st.get("disc_id") or f"{int(st.get('generation', 0) or 0)}:{_optical_model.canonical_state(st)}")
    if not cache_target.is_file():
        return f"{identity}:NO_CACHE"
    try:
        data = json.loads(cache_target.read_text(encoding="utf-8"))
        status = data.get("status", "")
        if status == "PASS":
            return f"{identity}:PASS:{data.get('tmdb_id')}:{data.get('confidence')}"
        elif status == "AMBIGUOUS":
            c_ids = ",".join(str(c.get("tmdb_id") or c.get("id")) for c in data.get("candidates", []))
            return f"{identity}:AMBIGUOUS:{c_ids}"
        return f"{identity}:{status}"
    except Exception:
        return f"{identity}:ERR"


def _c4_processing_entries(home: pathlib.Path, install: pathlib.Path, local_icon: pathlib.Path) -> str:
    """Return read-only navigation for the Magnificence status page.

    The single user-facing place that changes PURE / MAGNIFICENCE is
    LECTURE -> MODE VIDEO.  This page explains the current decision only.
    """
    return f"Entry1=RETOUR;{local_icon};:back"

def _playback_policy_sections(home: pathlib.Path, install: pathlib.Path, icons: dict[str, pathlib.Path]) -> tuple[str, str, str, str]:
    """Couch-native selectors backed by persistent user configuration."""
    if not isinstance(icons, dict):
        icons = {key: icons for key in ("video", "processing", "audio", "subtitles", "status", "about", "back")}
    policy_path = install / "openhtpc-playback-policy.py"
    setting = install / "openhtpc-playback-setting"
    video_icon, processing_icon, audio_icon = icons["video"], icons["processing"], icons["audio"]
    subtitle_icon, back_icon = icons["subtitles"], icons["back"]
    try:
        spec = importlib.util.spec_from_file_location("openhtpc_playback_policy_menu", policy_path)
        policy = importlib.util.module_from_spec(spec); spec.loader.exec_module(policy)
        prefs = policy.read_preferences(home)
    except (OSError, AttributeError, ImportError):
        prefs = {"presentation_mode":"PURE","audio_language_policy":"AUTO","audio_output_mode":"PCM","subtitle_policy":"AUTO"}
    presentation = "MAGNIFICENCE" if prefs["presentation_mode"] == "CINEMA_AUTO" else "PURE"
    audio = {"AUTO":"AUTO","FR":"FRANÇAIS","DEFAULT":"PISTE PAR DÉFAUT"}[prefs["audio_language_policy"]]
    subtitle = {"AUTO":"AUTO","OFF":"DÉSACTIVÉS","FR_FORCED":"FRANÇAIS FORCÉS","FR_FULL":"FRANÇAIS COMPLETS"}[prefs["subtitle_policy"]]
    root = os.linesep.join((
        f"Entry1=MODE VIDÉO;{video_icon};:submenu PLAYBACK_VIDEO",
        f"Entry2=TRAITEMENT VIDÉO;{processing_icon};:submenu SYSTEM_PROCESSING",
        f"Entry3=LANGUE AUDIO;{audio_icon};:submenu PLAYBACK_AUDIO",
        f"Entry4=SOUS-TITRES;{subtitle_icon};:submenu PLAYBACK_SUBTITLES",
        f"Entry5=RETOUR;{back_icon};:back",
    ))
    video = os.linesep.join((
        f"Entry1=PURE;{video_icon};:applyback {setting} presentation_mode PURE",
        f"Entry2=MAGNIFICENCE;{video_icon};:applyback {setting} presentation_mode CINEMA_AUTO",
        f"Entry3=RETOUR;{back_icon};:back",
    ))
    audio_menu = os.linesep.join((
        f"Entry1=AUTO;{audio_icon};:applyback {setting} audio_language_policy AUTO",
        f"Entry2=FRANÇAIS;{audio_icon};:applyback {setting} audio_language_policy FR",
        f"Entry3=PISTE PAR DÉFAUT;{audio_icon};:applyback {setting} audio_language_policy DEFAULT",
        f"Entry4=RETOUR;{back_icon};:back",
    ))
    subtitles = os.linesep.join((
        f"Entry1=AUTO;{subtitle_icon};:applyback {setting} subtitle_policy AUTO",
        f"Entry2=DÉSACTIVÉS;{subtitle_icon};:applyback {setting} subtitle_policy OFF",
        f"Entry3=FRANÇAIS FORCÉS;{subtitle_icon};:applyback {setting} subtitle_policy FR_FORCED",
        f"Entry4=FRANÇAIS COMPLETS;{subtitle_icon};:applyback {setting} subtitle_policy FR_FULL",
        f"Entry5=RETOUR;{back_icon};:back",
    ))
    return root, video, audio_menu, subtitles


def canonical_flex_config_path(home: pathlib.Path | None = None) -> pathlib.Path:
    """Canonical authoritative path for the active Flex appliance configuration."""
    if home is None:
        home = pathlib.Path(os.environ.get("OPENHTPC_HOME", pathlib.Path.home()))
    env_override = os.environ.get("OPENHTPC_FLEX_CONFIG")
    if env_override:
        return pathlib.Path(env_override)
    return home / ".config/openhtpc/flex-v1.ini"


@contextmanager
def flex_publication_lock(home: pathlib.Path):
    """Serialize complete Flex generation/publication across HOME and CLI writers."""
    target = home / ".local/state/openhtpc/flex-publication.lock"
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a+b") as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)


def write_flex_config(path: pathlib.Path, home: pathlib.Path, sources: list[pathlib.Path], install: pathlib.Path | None = None, expected_optical_generation: int | None = None, media_generation: str | None = None) -> bool:
    with flex_publication_lock(home):
        if expected_optical_generation is not None and media_generation is None:
            media_generation = active_media_generation(home)
        return _write_flex_config(path, home, sources, install, expected_optical_generation, media_generation)


def flex_cjk_fallback_font() -> pathlib.Path | None:
    """Return the Fedora system CJK font used only when Open Sans lacks a glyph."""
    candidates = (
        pathlib.Path("/usr/share/fonts/google-noto-sans-cjk-vf-fonts/NotoSansCJK-VF.ttc"),
        pathlib.Path("/usr/share/fonts/google-noto-cjk/NotoSansCJK-Regular.ttc"),
        pathlib.Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
    )
    return next((path for path in candidates if path.is_file()), None)


SYSTEM_PAGE_KEYS = (
    "overview", "codecs", "display", "audio", "media_optical", "extensions", "metadata",
    "tmdb", "processing", "playback", "diagnostics", "technical", "about",
)


def render_system_pages(home: pathlib.Path, install: pathlib.Path, ui_module=None) -> tuple[dict, pathlib.Path, dict]:
    """Render the System views from current runtime truth.

    This is intentionally separate from Flex configuration publication so the
    home controller can refresh bootstrap health after the authoritative Flex
    PID has been persisted, without rewriting the live menu configuration.
    """
    system_pages = {name: home / f".cache/openhtpc/system-{name}.png" for name in SYSTEM_PAGE_KEYS}
    dashboard = home / ".cache/openhtpc/system-dashboard.png"
    system_model = {}
    system_page = install / "openhtpc-system-page"
    if not system_page.is_file():
        return system_pages, dashboard, system_model

    loader = importlib.machinery.SourceFileLoader("openhtpc_system_live", str(system_page))
    spec = importlib.util.spec_from_loader("openhtpc_system_live", loader)
    system_live = importlib.util.module_from_spec(spec)
    loader.exec_module(system_live)
    system_model = system_live.status_model(home, install)

    management_path = install / "openhtpc-tmdb-management.py"
    if management_path.is_file():
        loader = importlib.machinery.SourceFileLoader("openhtpc_tmdb_management_ui", str(management_path))
        management_spec = importlib.util.spec_from_loader("openhtpc_tmdb_management_ui", loader)
        management = importlib.util.module_from_spec(management_spec)
        loader.exec_module(management)
        system_model["tmdb_management"] = management.status(home)

    ui = ui_module
    if ui is None:
        ui_path = install / "openhtpc-ui.py"
        if not ui_path.is_file():
            ui_path = pathlib.Path(__file__).with_name("openhtpc-ui.py")
        ui_spec = importlib.util.spec_from_file_location("openhtpc_system_ui", ui_path)
        ui = importlib.util.module_from_spec(ui_spec)
        ui_spec.loader.exec_module(ui)

    font = install / "flex/assets/fonts/OpenSans-Regular.ttf"
    ui.system_page_png(system_model, dashboard, font, "root")
    for key in SYSTEM_PAGE_KEYS:
        ui.system_page_png(system_model, system_pages[key], font, key)
    return system_pages, dashboard, system_model


def _write_flex_config(path: pathlib.Path, home: pathlib.Path, sources: list[pathlib.Path], install: pathlib.Path | None = None, expected_optical_generation: int | None = None, media_generation: str | None = None) -> bool:
    install = install or pathlib.Path(os.environ.get("OPENHTPC_INSTALL_DIR", home / ".local/lib/openhtpc"))
    font = install / "flex/assets/fonts/OpenSans-Regular.ttf"
    fallback_font = flex_cjk_fallback_font()
    icon_dir = install / "assets/ui"
    optical_empty_icon = icon_dir / "optical-empty.png"
    dvd_icon = icon_dir / "optical-dvd.png"
    bluray_icon = icon_dir / "optical-bluray.png"
    uhd_icon = icon_dir / "optical-uhd.png"
    media_icon = icon_dir / "media.png"
    eject_icon = icon_dir / "eject.png"
    local_icon = optical_empty_icon
    browser = home / ".local/bin/openhtpc-media-browser"
    dvd_ui = install / "openhtpc-dvd-ui"
    eject = install / "openhtpc-eject-current"
    power = install / "openhtpc-power-menu"
    system = install / "openhtpc-system-page"
    quit_openhtpc = install / "openhtpc-quit"
    system_view = install / "openhtpc-system-view"
    disc_view = install / "openhtpc-disc-view.py"
    theme = load_theme(install)
    logo = theme.assets(install)["logo"]
    scale = flex_scale(observed_display_size())
    optical = load_optional_object(home / ".local/state/openhtpc/optical-current.json")
    if expected_optical_generation is not None and int(optical.get("generation", 0) or 0) != expected_optical_generation:
        return False
    optical = enriched_optical(home, optical)
    canonical = _optical_model.canonical_state(optical); media = _optical_model.presentation(optical)
    disc_state = optical_home_label(optical) if canonical in {"DVD_VIDEO","BLURAY_VIDEO","UHD_BLURAY_VIDEO","BLURAY_FAMILY","UNKNOWN_OPTICAL_MEDIA"} else {
        "NO_OPTICAL_DRIVE": "AUCUN LECTEUR", "DRIVE_PRESENT_NO_MEDIA": "Aucun disque",
        "DETECTION_INDETERMINATE": "ÉTAT INCONNU",
    }.get(canonical, "ÉTAT INCONNU")
    optical_icon = icon_dir / media["icon"]
    live_optical_state = write_live_optical_state(home, optical, optical_icon)
    live_activity_state = home / ".local/state/openhtpc/media/activity-state"
    ready = canonical in {"DVD_VIDEO","BLURAY_VIDEO","UHD_BLURAY_VIDEO","BLURAY_FAMILY","UNKNOWN_OPTICAL_MEDIA"}
    entries = [
        f"Entry1={ini_value(str(disc_state)) if ready else 'LECTEUR · ' + ini_value(str(disc_state))};{optical_icon};:submenu DISQUE",
        f"Entry2=ÉJECTER;{eject_icon};:fork env OPENHTPC_STAY_IN_FLEX=1 {eject}",
        f"Entry3=MÉDIA;{media_icon};:submenu MEDIA_ROOT",
        f"Entry4=SYSTÈME;{logo};:submenu SYSTEME",
    ]
    index = 5
    for plugin_entry in plugin_menu_entries(home, install):
        entries.append(f"Entry{index}={ini_value(plugin_entry['label'])};{local_icon};:replace {plugin_entry['command']}")
        index += 1
    power_icon = install / "assets/ui/power.png"
    entries.append(f"Entry{index}=ÉTEINDRE;{power_icon};:submenu ALIMENTATION")
    source_inventory = os.linesep.join(f"Source{number}={ini_value(str(source))}" for number, source in enumerate(sources, 1)) or "SourceCount=0"
    optical_generation = int(optical.get("generation", 0) or 0)
    ui_spec = importlib.util.spec_from_file_location("openhtpc_ui", install / "openhtpc-ui.py" if (install / "openhtpc-ui.py").is_file() else pathlib.Path(__file__).with_name("openhtpc-ui.py"))
    ui = importlib.util.module_from_spec(ui_spec); ui_spec.loader.exec_module(ui)
    state_hash = hashlib.sha256(json.dumps(optical, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16]
    ui_generation_id = ui.generation_id(optical)
    system_pages, dashboard, system_model = render_system_pages(home, install, ui)
    sys_ui_dir = install / "assets/ui"
    root_ui_dir = pathlib.Path(__file__).resolve().parent / "assets/ui"

    def resolve_sys_icon(name, fallback):
        for d in (sys_ui_dir, root_ui_dir):
            p = d / name
            if p.is_file():
                return p
        return fallback

    icon_overview = resolve_sys_icon("system-overview.png", resolve_sys_icon("vue_ensemble.png", logo))
    icon_codecs = resolve_sys_icon("system-video.png", resolve_sys_icon("compatibilite_video.png", media_icon))
    icon_display = resolve_sys_icon("system-display.png", resolve_sys_icon("affichage.png", logo))
    icon_audio = resolve_sys_icon("system-audio.png", resolve_sys_icon("audio.png", media_icon))
    icon_optical = resolve_sys_icon("system-media-optical.png", resolve_sys_icon("media_optique.png", media_icon))
    icon_processing = resolve_sys_icon("system-processing.png", resolve_sys_icon("traitement_video.png", logo))
    icon_diagnostic = resolve_sys_icon("system-diagnostics.png", resolve_sys_icon("diagnostic.png", logo))
    icon_metadata = resolve_sys_icon("system-media-optical.png", resolve_sys_icon("media_optique.png", media_icon))
    icon_back = resolve_sys_icon("system-back.png", resolve_sys_icon("retour.png", logo))
    playback_icons = {
        "video": resolve_sys_icon("playback-video.png", icon_codecs),
        "processing": icon_processing,
        "audio": resolve_sys_icon("playback-language.png", icon_audio),
        "subtitles": resolve_sys_icon("playback-subtitles.png", media_icon),
        "status": resolve_sys_icon("playback-audio-status.png", icon_audio),
        "about": resolve_sys_icon("playback-about.png", logo),
        "back": icon_back,
    }
    playback_root, playback_video, playback_audio, playback_subtitles = _playback_policy_sections(home, install, playback_icons)
    user_cfg = load_optional_object(home / ".config/openhtpc/user-config.json")
    try:
        audio_mode = user_cfg.get("audio_output_mode", "PCM")
    except (OSError, AttributeError):
        audio_mode = "PCM"
    if audio_mode not in {"PCM", "BITSTREAM"}: audio_mode = "PCM"

    refresh_matching = user_cfg.get("refresh_matching", "OFF") if isinstance(user_cfg, dict) else "OFF"
    refresh_setting_label = "AUTOMATIQUE" if refresh_matching == "AUTO" else "DÉSACTIVÉE"

    audio_target = user_cfg.get("audio_output_target")
    if not isinstance(audio_target, dict):
        audio_target = {"mode": "SYSTEM", "node_name": None, "bus_path": None, "edid_name": None, "display_label": "SYSTEM", "device_type": "UNKNOWN"}

    audio_mod = None
    try:
        import openhtpc_audio
        audio_mod = openhtpc_audio
    except ImportError:
        pass
    if audio_mod is None:
        for candidate in (
            install / "openhtpc-audio.py",
            pathlib.Path(__file__).resolve().parent / "openhtpc-audio.py",
            pathlib.Path.home() / ".local/lib/openhtpc/openhtpc-audio.py",
        ):
            if candidate.is_file():
                try:
                    spec = importlib.util.spec_from_file_location("openhtpc_audio", candidate)
                    if spec and spec.loader:
                        audio_mod = importlib.util.module_from_spec(spec)
                        spec.loader.exec_module(audio_mod)
                        break
                except Exception:
                    pass

    discovered_outputs = []
    if audio_mod and hasattr(audio_mod, "discover_outputs"):
        try:
            discovered_outputs = audio_mod.discover_outputs()
        except Exception:
            discovered_outputs = []
    physical_outputs = [o for o in discovered_outputs if isinstance(o, dict) and not o.get("is_network")]
    kind_order = {"HDMI": 0, "USB": 1, "ANALOG": 2, "BLUETOOTH": 3, "UNKNOWN": 4}
    physical_outputs.sort(key=lambda o: (kind_order.get(o.get("device_type"), 4), str(o.get("display_label", "")).lower(), str(o.get("node_name", "")).lower()))

    routing = audio_mod.resolve_audio(audio_target, physical_outputs) if audio_mod and hasattr(audio_mod, "resolve_audio") else {
        "CONFIGURED": audio_target,
        "AVAILABLE": audio_target.get("mode") == "SYSTEM",
        "EFFECTIVE": audio_target if audio_target.get("mode") == "SYSTEM" else {"mode": "SYSTEM"},
    }

    t_mode = audio_target.get("mode", "SYSTEM")
    if t_mode == "SYSTEM":
        target_display_label = "Sortie système — Fedora"
    else:
        target_display_label = audio_target.get("display_label") or audio_target.get("edid_name") or audio_target.get("node_name") or "DEVICE"

    target_entries = []
    entry_idx = 1
    found_configured = False
    for o in physical_outputs:
        is_sel = (t_mode == "DEVICE" and routing.get("AVAILABLE") and routing.get("EFFECTIVE", {}).get("node_name") == o.get("node_name"))
        if is_sel:
            found_configured = True
        prefix = "• " if is_sel else ""
        label = (
            audio_target.get("display_label")
            if is_sel and audio_target.get("display_label")
            else o["display_label"]
        )
        target_entries.append(f"Entry{entry_idx}={prefix}{ini_value(label)};{icon_audio};:applyback {install/'openhtpc-playback-setting'} audio_output_target {o['node_name']}")
        entry_idx += 1

    if t_mode == "DEVICE" and not found_configured:
        unavail_entry = f"Entry{entry_idx}=• {ini_value(target_display_label)} (Indisponible);{icon_audio};:applyback {install/'openhtpc-playback-setting'} audio_output_target {audio_target.get('node_name', 'UNKNOWN')}"
        target_entries.insert(0, unavail_entry)
        target_entries = [f"Entry{i+1}=" + e.split("=", 1)[1] for i, e in enumerate(target_entries)]
        entry_idx = len(target_entries) + 1

    sys_sel = (t_mode == "SYSTEM")
    sys_prefix = "• " if sys_sel else ""
    target_entries.append(f"Entry{entry_idx}={sys_prefix}Sortie système — Fedora;{icon_audio};:applyback {install/'openhtpc-playback-setting'} audio_output_target SYSTEM")
    entry_idx += 1
    target_entries.append(f"Entry{entry_idx}=RETOUR;{icon_back};:back")
    audio_output_target_section = os.linesep.join(target_entries)
    disc_sheet = home / ".cache/openhtpc/disc-sheet.png"
    if not disc_sheet_is_current(home,optical):
        for stale in (disc_sheet,home/".local/state/openhtpc/disc-sheet-state.json"):
            try: stale.unlink()
            except OSError: pass
        _optical_model.trace_event(home,"PRESENTATION_INVALIDATED",optical_generation=optical_generation,canonical_state=canonical,presentation_state="INVALIDATED",event_reason="GENERATION_PROVENANCE_MISMATCH")
    if disc_view.is_file():
        subprocess.run([str(disc_view), "--home", str(home), "--generation", str(optical_generation)], timeout=DISC_VIEW_TIMEOUT_S, check=False,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if not disc_sheet_is_current(home,optical): disc_sheet = theme.assets(install)["wallpaper"]
    counter_path = home / ".local/state/openhtpc/menu-generation"
    counter_path.parent.mkdir(parents=True, exist_ok=True)
    with open(counter_path, "a+", encoding="utf-8") as counter:
        fcntl.flock(counter, fcntl.LOCK_EX); counter.seek(0)
        try: menu_generation = int(counter.read().strip() or "0") + 1
        except ValueError: menu_generation = 1
        counter.seek(0); counter.truncate(); counter.write(str(menu_generation)); counter.flush(); os.fsync(counter.fileno())
    media_generation=media_generation or f"{ui_generation_id}-{menu_generation}"
    manifest_candidate=path.with_name(path.name+".media-actions.json")
    _media_root, media_sections = media_menu_sections(home, sources, media_icon, media_generation,manifest_candidate)
    content = f"""# OPENHTPC menu_generation={menu_generation} ui_generation_id={ui_generation_id} media_generation={media_generation} optical_generation={optical_generation} state_hash={state_hash}
[General]
DefaultMenu=OPENHTPC
VSync=true
OnLaunch=Blank
WrapEntries=true
ResetOnBack=true
MouseSelect=true
InhibitOSScreensaver=true
LiveOpticalState={live_optical_state}
LiveActivityState={live_activity_state}

{theme.background_block(install, 52)}

[Layout]
MaxButtons=9
IconSize={scale['icon']}
IconSpacing=3%
VCenter=50%

{theme.title_block(font, scale['title'], scale['padding'], fallback_font)}

{theme.highlight_block()}

[Scroll Indicators]
Enabled=true
FillColor=#FFFFFF
OutlineSize=0
OutlineColor=#000000
Opacity=100%

[Clock]
Enabled=true
ShowDate=true
Alignment=Right
Font={font}
FontSize={scale['clock']}
FontColor=#FFFFFF
Shadows=false
Margin=4%
Opacity=100%
TimeFormat=24hr
DateFormat=Auto
IncludeWeekday=true

[Screensaver]
Enabled=false

[Hotkeys]
Hotkey1=#1B;:back
Hotkey2=#08;:back

[Gamepad]
Enabled=true
DeviceIndex=-1
LStickX-=:left
LStickX+=:right
LStickY-=:left
LStickY+=:right
ButtonA=:select
ButtonB=:back
ButtonDPadLeft=:left
ButtonDPadRight=:right
ButtonDPadUp=:left
ButtonDPadDown=:right

[OPENHTPC]
{os.linesep.join(entries)}

[SYSTEME]
BackgroundImage={dashboard}
Entry1=VUE D'ENSEMBLE;{icon_overview};:submenu SYSTEM_OVERVIEW
Entry2=VIDÉO;{icon_codecs};:submenu SYSTEM_CODECS
Entry3=AFFICHAGE;{icon_display};:submenu SYSTEM_DISPLAY
Entry4=LECTURE;{icon_processing};:submenu SYSTEM_PLAYBACK
Entry5=AUDIO;{icon_audio};:submenu SYSTEM_AUDIO
Entry6=MÉDIAS & DISQUES;{icon_optical};:submenu SYSTEM_MEDIA_OPTICAL
Entry7=MÉTADONNÉES;{icon_metadata};:submenu SYSTEM_METADATA
Entry8=EXTENSIONS;{logo};:submenu SYSTEM_EXTENSIONS
Entry9=DIAGNOSTIC;{icon_diagnostic};:submenu SYSTEM_DIAGNOSTICS
Entry10=À PROPOS;{logo};:submenu SYSTEM_ABOUT
Entry11=RETOUR;{icon_back};:back

[SYSTEM_OVERVIEW]
BackgroundImage={system_pages['overview']}
Entry1=RETOUR;{icon_back};:back

[SYSTEM_CODECS]
BackgroundImage={system_pages['codecs']}
Entry1=RETOUR;{icon_back};:back

[SYSTEM_DISPLAY]
BackgroundImage={system_pages['display']}
Entry1=ADAPTATION DE FRÉQUENCE : {refresh_setting_label};{icon_display};:submenu DISPLAY_REFRESH_MATCHING
Entry2=RETOUR;{icon_back};:back

[DISPLAY_REFRESH_MATCHING]
BackgroundImage={system_pages['display']}
Entry1=AUTOMATIQUE;{icon_display};:applyback {install/'openhtpc-playback-setting'} refresh_matching AUTO
Entry2=DÉSACTIVÉE;{icon_display};:applyback {install/'openhtpc-playback-setting'} refresh_matching OFF
Entry3=RETOUR;{icon_back};:back

[SYSTEM_AUDIO]
BackgroundImage={system_pages['audio']}
Entry1=SORTIE AUDIO : {target_display_label};{icon_audio};:submenu AUDIO_OUTPUT_TARGET
Entry2=MODE AUDIO : {audio_mode};{playback_icons['audio']};:submenu AUDIO_OUTPUT_MODE
Entry3=RETOUR;{icon_back};:back

[AUDIO_OUTPUT_TARGET]
BackgroundImage={system_pages['audio']}
{audio_output_target_section}

[AUDIO_OUTPUT_MODE]
BackgroundImage={system_pages['audio']}
Entry1=PCM;{playback_icons['audio']};:applyback {install/'openhtpc-playback-setting'} audio_output_mode PCM
Entry2=BITSTREAM;{playback_icons['audio']};:applyback {install/'openhtpc-playback-setting'} audio_output_mode BITSTREAM
Entry3=RETOUR;{icon_back};:back

[SYSTEM_MEDIA_OPTICAL]
BackgroundImage={system_pages['media_optical']}
Entry1=RETOUR;{icon_back};:back

[SYSTEM_EXTENSIONS]
BackgroundImage={system_pages['extensions']}
Entry1=RETOUR;{icon_back};:back

[SYSTEM_METADATA]
BackgroundImage={system_pages['metadata']}
Entry1=TMDb;{icon_metadata};:submenu SYSTEM_TMDB
Entry2=RETOUR;{icon_back};:back

[SYSTEM_TMDB]
BackgroundImage={system_pages['tmdb']}
{(f"Entry1=CONFIGURER;{icon_metadata};:fork {install/'openhtpc-tmdb-management.py'} configure\nEntry2=RETOUR;{icon_back};:back" if not system_model.get('tmdb_management',{}).get('masked') else f"Entry1=TESTER;{icon_metadata};:fork {install/'openhtpc-tmdb-management.py'} test\nEntry2=MODIFIER;{icon_metadata};:fork {install/'openhtpc-tmdb-management.py'} modify\nEntry3=SUPPRIMER;{icon_metadata};:fork {install/'openhtpc-tmdb-management.py'} delete\nEntry4=RETOUR;{icon_back};:back")}

[SYSTEM_PROCESSING]
BackgroundImage={system_pages['processing']}
{_c4_processing_entries(home, install, icon_processing)}

[SYSTEM_PLAYBACK]
BackgroundImage={system_pages['playback']}
{playback_root}

[PLAYBACK_VIDEO]
BackgroundImage={system_pages['playback']}
{playback_video}

[PLAYBACK_AUDIO]
BackgroundImage={system_pages['playback']}
{playback_audio}

[PLAYBACK_SUBTITLES]
BackgroundImage={system_pages['playback']}
{playback_subtitles}

[SYSTEM_DIAGNOSTICS]
BackgroundImage={system_pages['diagnostics']}
Entry1=ACTUALISER LES CAPACITÉS;{icon_diagnostic};:fork {install/'openhtpc-system-action'} refresh
Entry2=CRÉER UN RAPPORT SUPPORT;{icon_diagnostic};:fork {install/'openhtpc-system-action'} support
Entry3=INFORMATIONS TECHNIQUES;{icon_diagnostic};:submenu SYSTEM_TECHNICAL
Entry4=RETOUR;{icon_back};:back

[SYSTEM_TECHNICAL]
BackgroundImage={system_pages['technical']}
Entry1=RETOUR;{icon_back};:back

[SYSTEM_ABOUT]
BackgroundImage={system_pages['about']}
Entry1=RETOUR;{icon_back};:back

[DISQUE]
BackgroundImage={disc_sheet}
{disc_menu_entries(optical, install, (media_icon, media_icon, eject_icon, icon_back), home)}

{media_sections}

[ALIMENTATION]
Entry1=QUITTER OPENHTPC;{install/'assets/ui/quit.png'};:fork {quit_openhtpc}
Entry2=ÉTEINDRE LE PC;{power_icon};systemctl poweroff
Entry3=RETOUR;{icon_back};:back

[MediaSidebar]
Entry1=MÉDIAS LOCAUX;{local_icon};{browser}
Entry2=LECTEUR DVD / BLU-RAY / UHD;{dvd_icon};{dvd_ui}

[Configured Media]
{source_inventory}
"""
    ui.validate_config_text(content)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(content)
            stream.flush(); os.fsync(stream.fileno())
        latest = load_optional_object(home / ".local/state/openhtpc/optical-current.json")
        if expected_optical_generation is not None and int(latest.get("generation", 0) or 0) != expected_optical_generation:
            return False
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try: os.fsync(directory)
        finally: os.close(directory)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return True


def menu_identity(path: pathlib.Path) -> int:
    try:
        first = path.open(encoding="utf-8").readline()
        return int(first.split("menu_generation=", 1)[1].split()[0])
    except (OSError, ValueError, IndexError):
        return 0


def activate_media_manifest(config_path:pathlib.Path,home:pathlib.Path)->pathlib.Path:
    """Publish only the action manifest loaded by the authoritative Flex."""
    candidate=config_path.with_name(config_path.name+".media-actions.json")
    data=load_object(candidate,"media_actions","ACTION_MANIFEST_MISSING","ACTION_MANIFEST_INVALID")
    if data.get("schema")!=1 or not isinstance(data.get("items"),dict) or not isinstance(data.get("sources"),list):
        raise GateError("media_actions","ACTION_MANIFEST_INVALID","Le manifeste MEDIA candidat est invalide.")
    target=current_media_manifest(home);target.parent.mkdir(parents=True,exist_ok=True)
    fd,temporary=tempfile.mkstemp(prefix=target.name+".",dir=target.parent)
    try:
        with os.fdopen(fd,"w",encoding="utf-8") as stream:json.dump(data,stream,ensure_ascii=False,sort_keys=True);stream.write("\n");stream.flush();os.fsync(stream.fileno())
        os.chmod(temporary,0o600);os.replace(temporary,target)
    finally:
        if os.path.exists(temporary):os.unlink(temporary)
    return target


def publish_flex_config(path:pathlib.Path,home:pathlib.Path,sources:list[pathlib.Path],install:pathlib.Path|None=None)->bool:
    """Publish one MEDIA generation at the synchronous Flex action boundary."""
    with flex_publication_lock(home):
        return _publish_flex_config(path, home, sources, install)


def _publish_flex_config(path:pathlib.Path,home:pathlib.Path,sources:list[pathlib.Path],install:pathlib.Path|None=None)->bool:
    path.parent.mkdir(parents=True,exist_ok=True)
    fd,name=tempfile.mkstemp(prefix=path.name+".publish.",dir=path.parent);os.close(fd);staged=pathlib.Path(name)
    candidate=path.with_name(path.name+".media-actions.json");staged_candidate=staged.with_name(staged.name+".media-actions.json")
    current=current_media_manifest(home);targets=(path,candidate,current)
    previous={target:(target.read_bytes() if target.is_file() else None) for target in targets}
    def replace_bytes(target:pathlib.Path,data:bytes)->None:
        target.parent.mkdir(parents=True,exist_ok=True);fd,tmp=tempfile.mkstemp(prefix=target.name+".",dir=target.parent)
        try:
            with os.fdopen(fd,"wb") as stream:stream.write(data);stream.flush();os.fsync(stream.fileno())
            os.chmod(tmp,0o600);os.replace(tmp,target)
        finally:
            if os.path.exists(tmp):os.unlink(tmp)
    try:
        staged.unlink()
        if not _write_flex_config(staged,home,sources,install):return False
        model=load_object(staged_candidate,"media_actions","ACTION_MANIFEST_MISSING","ACTION_MANIFEST_INVALID")
        if model.get("schema")!=1 or not isinstance(model.get("items"),dict):raise GateError("media_actions","ACTION_MANIFEST_INVALID","Le manifeste MEDIA candidat est invalide.")
        replace_bytes(candidate,staged_candidate.read_bytes())
        activate_media_manifest(path,home)
        replace_bytes(path,staged.read_bytes())
        return True
    except Exception:
        for target,data in previous.items():
            if data is None:
                try:target.unlink()
                except OSError:pass
            else:replace_bytes(target,data)
        raise
    finally:
        for target in (staged,staged_candidate):
            try:target.unlink()
            except OSError:pass


def load_optional_object(path: pathlib.Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}

def disc_sheet_is_current(home: pathlib.Path, optical: dict) -> bool:
    provenance=load_optional_object(home/".local/state/openhtpc/disc-sheet-state.json")
    return (int(provenance.get("optical_generation",-1) or -1)==int(optical.get("generation",0) or 0) and
            provenance.get("canonical_state")==_optical_model.canonical_state(optical) and
            provenance.get("ui_state_hash")==optical.get("ui_state_hash") and
            (home/".cache/openhtpc/disc-sheet.png").is_file())

def publish_generation_fallback(home: pathlib.Path, install: pathlib.Path, optical: dict, reason: str,
                                expected_generation: int | None = None) -> bool:
    """Publish a truthful, generation-matching fallback after bounded worker failure.

    ``expected_generation`` is the generation whose worker failed.  It must match
    the generation carried by ``optical``: a failure of G must never publish a
    fallback for G+1, because the fallback is stamped with the generation it
    describes.  Returns whether anything was published.
    """
    generation = int(optical.get("generation", 0) or 0)
    if expected_generation is not None and int(expected_generation or 0) != generation:
        return False
    target = home/".cache/openhtpc/disc-sheet.png"; target.parent.mkdir(parents=True,exist_ok=True)
    source = load_theme(install).assets(install)["wallpaper"]
    fd, temporary = tempfile.mkstemp(prefix=target.name+".",dir=target.parent)
    try:
        with os.fdopen(fd,"wb") as stream:
            stream.write(source.read_bytes());stream.flush();os.fsync(stream.fileno())
        os.chmod(temporary,0o600);os.replace(temporary,target)
    finally:
        if os.path.exists(temporary):os.unlink(temporary)
    provenance={"schema":1,"optical_generation":generation,"canonical_state":_optical_model.canonical_state(optical),
                "ui_state_hash":optical.get("ui_state_hash"),"render_identity":f"fallback-{generation}",
                "metadata_status":"FALLBACK","presentation_state":"FALLBACK","error_reason":reason}
    _optical_model.atomic_json(home/".local/state/openhtpc/disc-sheet-state.json",provenance)
    _optical_model.trace_event(home,"PRESENTATION_FALLBACK",optical_generation=generation,
                               canonical_state=provenance["canonical_state"],presentation_state="FALLBACK",
                               render_generation=generation,metadata_job_state="FALLBACK",event_reason=reason)
    return True


class RegenerationSupervisor:
    """Bounded lifecycle of the menu-regeneration worker.

    Owns the worker handle, the process group that worker opened, the execution
    accounting, the watchdog decision, the stale-failure rejection, the
    process-group termination and the guarded fallback, so the whole policy is
    executable without starting the home controller — importing openhtpc-home.py
    renders the menu and launches Flex, which no hermetic test can do.

    ``spawn(generation)`` must return a ``subprocess.Popen`` started with
    ``start_new_session=True`` (the group termination depends on it).
    ``current_optical()`` returns the live optical state dict.  A successful
    render is published by the CONTROLLER, not here, so the dev11 order
    (render -> publish -> navigation detection) stays readable in its source.

    LIFECYCLE RULE.  The worker's group is captured at spawn and released before
    anything else takes that worker's slot: before a retry, before a
    supersession, before a new generation, and as soon as the leader is seen to
    have exited.  The release happens BEFORE the leader is reaped, so the group
    is still addressed while its pid is pinned — which is what makes a
    descendant reachable even though the worker's leader is already gone.
    Reaping first frees the pid, and the same ``killpg`` becomes a guess about a
    number the kernel may already have handed to somebody else.

    V6 (findings A/B/D/E of the AGY + Codex review of v5) tightened four things,
    and each one is a rule this class enforces rather than documents:

    * A  ownership is a PRECONDITION, checked BEFORE the terminator is called.
         For a supervised worker whose group is not proven ours, the terminator
         is never invoked at all: no ``_terminate_single_process``, no ``poll``,
         no ``wait``, no reap, no signal to the pid alone — only a fail-closed
         outcome (``NO_GROUP_UNPROVEN`` / ``GROUP_UNKNOWN``).
    * B  the leader is reaped only AFTER a release is PROVEN.  An unproven
         release keeps the group and the pinned pid, so its disappearance can
         still be proved — and acted on — by a later attempt.
    * D  a retained generation carries an INTENT in one explicit slot, so
         nothing is lost (a blocked success is resumed, not dropped), a retry or
         a fallback never races a descendant that may still write, and a stale
         publication never crosses into a new generation.
    * E  ``shutdown()`` drains the same way, bounded, on every exit path: the
         controller is never allowed to replace itself or exit "normally" over a
         group it failed to release.

    V7 (findings of the AGY + Codex review of v6) refines three of those rules,
    each one again enforced in code rather than documented:

    * D  a REQUEST for the generation whose render already SUCCEEDED is NOT
         absorbed: it SUPERSEDES the retained success, because it carries the
         newer presentation need (the post-enrichment rerender) — the rendered
         title is never silently left pre-enrichment;
    * D  ``_fail_closed_output`` NEVER writes: while the release is UNPROVEN no
         presentation artifact is touched, and the last valid/stale content is
         KEPT instead of being overwritten from a guess;
    * E  ``shutdown()`` is driven by ``guarded_release()``, which keeps the
         controller ALIVE — holding its memory identity and its inherited
         ``ui-session.lock`` — and paced until the release is proven; it no
         longer exits over a retained group and hands the machine to a controller
         that would race one it cannot remember.
    """

    def __init__(self, spawn, current_optical, home=None, install=None, log=None,
                 clock=time.monotonic, terminate=terminate_worker_group,
                 capture=capture_worker_group, proc_root: pathlib.Path = PROC_ROOT,
                 max_attempts: int = REGENERATION_MAX_ATTEMPTS,
                 budget_s: float = REGENERATION_WORKER_BUDGET_S,
                 require_group: bool = True,
                 max_cleanup_attempts: int = CLEANUP_MAX_RECOVERY_ATTEMPTS):
        self._spawn = spawn
        self._current_optical = current_optical
        self._home = home
        self._install = install
        self._log = log or (lambda *args, **kwargs: None)
        self._clock = clock
        self._terminate = terminate
        self._capture = capture
        self._proc_root = proc_root
        self.max_attempts = int(max_attempts)
        self.budget_s = budget_s
        # The controller spawns its workers with ``start_new_session=True``: each
        # one MUST be a session/group leader, so a group we failed to capture —
        # or one that belongs to somebody else — is an UNPROVEN ownership, never
        # a licence to fall back to signalling the pid alone and call it cleaned
        # (finding A).
        self.require_group = bool(require_group)
        self.max_cleanup_attempts = int(max_cleanup_attempts)
        self.proc = None
        self.group = None
        self.generation = 0
        self.started_at = None
        self.executions = 0
        # Ownership of the previous worker's release, and its recovery (findings
        # B and D): ONE explicit, unique slot records what a retained generation
        # is waiting for — ``{"generation": int, "intent": ...}``.  It is never a
        # queue: a newer generation owns the presentation, so the newest fact
        # replaces the oldest, and the replacement is logged, never silent.
        self.cleanup_state = CLEANUP_PROVEN
        self.recovery_attempts = 0
        self.fail_closed = False
        self.pending = None
        self.publish_pending = None
        # A worker that was still RUNNING when it was stopped (supersession,
        # stall) is a termination; a group released after its leader had already
        # exited is a release.  They are kept apart on purpose: the cap counts
        # executions, and a release is not an attempt.
        self.terminations = []
        self.releases = []

    @property
    def live(self) -> bool:
        """True while the worker's leader has not exited.

        Probed WITHOUT reaping: ``proc.poll()`` would collect an exited leader
        and free its pid before the group has been released — the exact order
        this lifecycle forbids.  ``/proc`` gives the state; when it cannot, the
        answer comes from a non-reaping ``waitid``, never from ``poll()``.
        """
        return self.proc is not None and self._leader_running(self.proc)

    def _leader_running(self, proc) -> bool:
        if proc is None or proc.returncode is not None:
            return False
        state = worker_process_state(proc.pid, self._proc_root)
        if state is not None:
            return state != "Z"
        # /proc cannot answer (finding D).  ``proc.poll()`` would REAP the leader
        # here — freeing the pid, and with it the pgid that makes the group safe
        # to address.  ``waitid(WNOWAIT)`` peeks without collecting; when even
        # that cannot tell, the answer is "still running": fail-closed, and the
        # watchdog bounds it.
        exited = leader_exited_without_reaping(proc.pid)
        return True if exited is None else not exited

    def current_generation(self) -> int:
        return int(self._current_optical().get("generation", 0) or 0)

    def _start(self, generation: int):
        """Spawn one worker and TAKE OWNERSHIP of its group immediately.

        Capturing here is the whole point: the leader is alive and unreaped, so
        its pid — and the pgid, which IS that pid — cannot be recycled, and the
        group can be addressed later without ever resolving a pgid from a pid.
        """
        proc = self._spawn(generation)
        self.proc = proc
        captured = self._capture(proc, self._proc_root) if proc is not None else None
        if captured is None and proc is not None:
            # Ownership could not be captured AT SPAWN.  The identity is not
            # thrown away: the pid (pinned while the leader is unreaped) is kept
            # so a later attempt still addresses something real — but the group
            # is unproven and every release treats it as such.
            captured = WorkerGroup(proc, proc.pid, None, None, None)
        self.group = captured
        return proc

    def _ownership_proven(self, group) -> bool:
        """True only when ``group`` is a CAPTURED group this supervisor may signal.

        Finding A (v6): the check happens BEFORE the terminator is called, never
        after.  v5 called the terminator first and overwrote its answer
        afterwards — so the single-process path had already run on the leader
        (polled it, possibly reaped it, and could have signalled its pid alone)
        for a worker whose group was never proven ours.  Ownership is a
        precondition of touching the worker at all.
        """
        return isinstance(group, WorkerGroup) and group.owns_group

    def _unproven_ownership_outcome(self, group) -> str:
        """The fail-closed outcome for a supervised worker whose group is not ours."""
        if group is None or group.pgid is None:
            return NO_GROUP_UNPROVEN      # no group was ever captured to address
        return "GROUP_UNKNOWN"            # a group NUMBER not proven to be ours

    def _reap_released(self) -> None:
        """Collect the leader — ONLY once its group has been PROVEN released.

        Finding B (v6): the reap frees the pid, and with it the pgid that pins the
        group.  It may therefore follow the proof, never precede it, and never be
        used to manufacture one.
        """
        holder = self.group
        proc = holder.proc if holder is not None else None
        if proc is None:
            proc = self.proc
        _reap_worker(proc, EXIT_REAP_TIMEOUT_S)

    def _release(self, reason: str) -> str | None:
        """Release the group owned for the previous worker.

        Called before every decision that gives the slot to somebody else, and
        it works on the CAPTURED group, so it still reaches the descendants of a
        worker whose leader has already exited.

        TWO RULES, enforced here rather than asserted in a comment.

        * Finding A.  For a supervisor whose workers MUST be group leaders
          (``require_group``), an absent or unproven group is fail-closed: the
          terminator is NOT called, the leader is not polled, not waited on, not
          reaped, and no signal is aimed at its pid alone.  A worker whose
          descendants cannot be reached was not cleaned, and no outcome may say
          it was.
        * Findings B and D.  Ownership is cleared ONLY when the release is
          PROVEN, and the leader is collected ONLY after that proof.  An unproven
          release KEEPS ``self.group`` — it is the identity proof — sets
          ``CLEANUP_UNPROVEN``, and invalidates any publication still waiting for
          the controller, so nothing may take the slot, retry, or publish while
          it holds.
        """
        target = self.group if self.group is not None else self.proc
        if target is None:
            self.cleanup_state = CLEANUP_PROVEN
            return None
        running = self.live          # before the release: afterwards the leader is gone
        if self.require_group and not self._ownership_proven(self.group):
            outcome = self._unproven_ownership_outcome(self.group)
        else:
            outcome = self._terminate(target)
        if running:
            self.terminations.append((self.generation, outcome))
        else:
            self.releases.append((self.generation, outcome, reason))
        if outcome in RELEASE_PROVEN:
            self._reap_released()            # the proof came first; only now the reap
            self.group = None
            self.cleanup_state = CLEANUP_PROVEN
            self.recovery_attempts = 0
        else:
            self.cleanup_state = CLEANUP_UNPROVEN
            # (D4) A publication waiting for the controller describes the OLD
            # slot; it must not survive into an unproven one.
            self.publish_pending = None
        return outcome

    @property
    def pending_request(self):
        """The generation the retained slot is waiting for, or None.

        Kept as a name because that is what it is from the caller's side; the
        supervisor stores it in the single ``pending`` slot together with the
        INTENT, which is what makes "resume exactly once" decidable.
        """
        return None if self.pending is None else int(self.pending["generation"])

    def _hold_pending(self, generation: int, intent: str) -> None:
        """Record, in the ONE slot, what ``generation`` must resume to.

        Finding D (v6).  A retained generation without a recorded intent is a
        silent loss, so the intent is explicit and any replacement is LOGGED.

        Finding (AGY, v7).  v6 also ABSORBED a ``REQUEST`` for the very
        generation whose render already SUCCEEDED (``REGENERATION_PENDING_
        REQUEST_ABSORBED``), on the principle that a render is a fact and a
        request a wish.  That absorption lost the ONE rerender that matters
        here: a worker succeeds PRE-enrichment, the cleanup is UNPROVEN, the
        enricher then finishes and the controller asks for the SAME generation
        again — carrying the enriched TMDb metadata.  v6 absorbed it, resumed
        only the pre-enrichment success, and the enriched presentation was never
        rendered.  A later request is therefore NOT absorbed: it SUPERSEDES the
        retained success of the SAME generation, because it describes a strictly
        NEWER presentation need.  Publishing the older render would flash
        exactly the stale fiche the request exists to replace, and the request
        itself will re-render and publish — so nothing is lost, and the
        supersession is journalised rather than silent.  Every other
        replacement is logged too.
        """
        generation = int(generation or 0)
        current = self.pending
        if (current is not None and current["intent"] == PENDING_SUCCESS
                and int(current["generation"]) == generation and intent == PENDING_REQUEST):
            self._log("REGENERATION_PENDING_SUCCESS_SUPERSEDED_BY_REQUEST",
                      optical_generation=generation)
            self.pending = {"generation": generation, "intent": intent}
            return
        if current is not None and (current["intent"] != intent
                                    or int(current["generation"]) != generation):
            self._log("REGENERATION_PENDING_REPLACED",
                      previous_generation=int(current["generation"]), previous_intent=current["intent"],
                      optical_generation=generation, new_intent=intent)
        self.pending = {"generation": generation, "intent": intent}

    def request(self, generation: int):
        """Start the single worker for ``generation``, superseding any live one.

        A superseded worker is not a failed attempt: a newer optical generation
        owns the presentation, so the replaced worker is terminated as such and
        the execution count restarts at one.  Whatever the previous worker left
        is released FIRST, including a group whose leader has already exited.

        When the slot is UNPROVEN nothing starts: the request is RETAINED in the
        pending slot (finding D), so it is neither enacted over a group that may
        still be writing the same files, nor silently forgotten.
        """
        generation = int(generation or 0)
        # (D4) A publication waiting for the controller describes the PREVIOUS
        # generation; a new request invalidates it instead of letting it travel
        # into the new one.
        self.publish_pending = None
        if self.cleanup_state == CLEANUP_UNPROVEN:
            self._hold_pending(generation, PENDING_REQUEST)
            self.proc = None
            self._log("REGENERATION_REQUEST_BLOCKED_CLEANUP_UNPROVEN",
                      optical_generation=generation, cleanup_state=self.cleanup_state)
            return None
        self._release("SUPERSEDED")
        if self.cleanup_state == CLEANUP_UNPROVEN:
            self._hold_pending(generation, PENDING_REQUEST)
            self.proc = None
            self._log("REGENERATION_REQUEST_BLOCKED_CLEANUP_UNPROVEN",
                      optical_generation=generation, cleanup_state=self.cleanup_state)
            return None
        self.generation = generation
        self.executions = 1
        self.started_at = self._clock()
        self._start(self.generation)
        return self.proc

    def note_published(self):
        """A render of the current generation was published: the budget is free again."""
        self.executions = 0

    def tick(self) -> list:
        """One controller iteration: the watchdog, then the worker's own exit.

        Returns the event names, in order, for the caller and for tests.
        A successful render is left in ``self.proc`` for the controller to
        publish (``EXITED_OK``): this method never publishes it.

        Whichever way the worker ends, its group is released here — before the
        controller reaps the leader and before any retry — so that no descendant
        outlives the generation it was rendering.
        """
        events = []
        if self.cleanup_state == CLEANUP_UNPROVEN:
            return self._recover_cleanup()
        if self.proc is None:
            return events
        if self._leader_running(self.proc):
            if self.started_at is not None and regeneration_watchdog_expired(self._clock() - self.started_at, self.budget_s):
                released = self._release("STALLED")
                failed = self.generation
                self.proc = None
                self.started_at = None
                if self.cleanup_state == CLEANUP_UNPROVEN:
                    # A stalled worker whose group is not proven gone: no retry,
                    # no new generation, and NO FALLBACK YET — a descendant may
                    # still be writing exactly the files a fallback would stamp
                    # (finding D).  The generation and its intent are RETAINED,
                    # and the bounded recovery decides later.
                    self._hold_pending(failed, "STALLED")
                    self._log("REGENERATION_STALLED_BLOCKED_CLEANUP_UNPROVEN",
                              optical_generation=int(failed or 0), group_release=released)
                    events.append("STALLED_CLEANUP_UNPROVEN")
                    return events
                events.append(self._resolve("STALLED", failed, released))
            return events
        # the leader has exited.  Read its status WITHOUT reaping: this is where
        # v4's reach for ``proc.poll()`` collected the leader before the group
        # had been released.
        succeeded = leader_exit_success_without_reaping(self.proc.pid)
        released = self._release("EXITED")
        failed = self.generation
        if self.cleanup_state == CLEANUP_UNPROVEN:
            self.proc = None
            self.started_at = None
            if succeeded is True:
                # a render that succeeded but whose group could not be proven
                # released is NOT published — no success may race a descendant —
                # and is NOT forgotten either: the pending slot records it, so
                # the recovery can hand it over instead of losing it (finding D,
                # the v5 silent loss).
                self._hold_pending(failed, PENDING_SUCCESS)
                self._log("REGENERATION_SUCCESS_BLOCKED_CLEANUP_UNPROVEN",
                          optical_generation=int(failed or 0), group_release=released)
                events.append("SUCCESS_BLOCKED_CLEANUP_UNPROVEN")
            else:
                # Same rule for a failure: no fallback while a descendant of the
                # failed worker may still write.  The bounded recovery (or its
                # fail-closed exhaustion) owns that decision.
                self._hold_pending(failed, "FAILED")
                self._log("REGENERATION_FAILURE_BLOCKED_CLEANUP_UNPROVEN",
                          optical_generation=int(failed or 0), group_release=released)
                events.append("FAILED_CLEANUP_UNPROVEN")
            return events
        _reap_worker(self.proc, EXIT_REAP_TIMEOUT_S)
        returncode = self.proc.returncode
        failed = self.generation
        if returncode == 0:
            if regeneration_failure_is_stale(failed, self.current_generation()):
                self.proc = None
                self.started_at = None
                self._log("REGENERATION_RESULT_SUPERSEDED", optical_generation=int(failed or 0),
                          current_generation=self.current_generation())
                events.append("SUPERSEDED")
            else:
                # A successful render whose group is PROVEN released: handed to
                # the controller for publication, in the dev11 order.  ``proc``
                # is cleared so nobody polls a reaped pid.
                self.publish_pending = (failed, True)
                self.proc = None
                self.started_at = None
                events.append("EXITED_OK")
            return events
        self.proc = None
        self.started_at = None
        events.append(self._resolve("FAILED", failed, released))
        return events

    def take_publishable(self):
        """Hand the controller the render to publish, or None.

        The supervisor — not the controller — owns the decision that a render is
        both successful AND its process group proven released.  The controller
        never calls ``poll()``/``wait()`` on ``supervisor.proc``; it asks here
        (finding E).
        """
        pending = self.publish_pending
        self.publish_pending = None
        return pending

    def shutdown(self, attempts: int | None = None):
        """Bounded, ownership-respecting drain before the controller leaves.

        Finding E.  Every exit path of the HOME controller — the stop signal, the
        normal end of the loop, and the Flex-recovery ``execv`` — funnels here.
        The rules are exactly the release rules: the CAPTURED group is addressed,
        the single-process fallback is never used for a supervised worker, the
        leader is never reaped before the proof, and a group that cannot be
        proven released within the bounded budget FAILS CLOSED instead of being
        silently abandoned.  No pending work is resumed: the controller is
        leaving, and starting a worker here is the opposite of draining.

        Returns ``(may_exit, outcome, events)``.  ``may_exit`` is False when the
        caller must NOT replace itself (``execv``) or exit "normally" over a
        retained group: doing so would hand the machine to a new controller that
        knows nothing about the group it is about to race.
        """
        events = []
        if self.proc is None and self.group is None and self.cleanup_state == CLEANUP_PROVEN:
            return True, None, ["SHUTDOWN_CLEAN"]
        budget = SHUTDOWN_RELEASE_ATTEMPTS if attempts is None else max(1, int(attempts))
        outcome = None
        for _ in range(budget):
            outcome = self._release("SHUTDOWN")
            self.proc = None
            self.started_at = None
            if self.cleanup_state == CLEANUP_PROVEN:
                events.append("SHUTDOWN_RELEASED")
                return True, outcome, events
        self.fail_closed = True
        self._log("REGENERATION_CLEANUP_FAIL_CLOSED", group_release=outcome,
                  attempts=budget, event_reason="SHUTDOWN")
        events.append("SHUTDOWN_CLEANUP_UNPROVEN")
        return False, outcome, events

    def _recover_cleanup(self) -> list:
        """Bounded, deterministic recovery from an unproven release (finding B).

        Each call re-attempts the release of the RETAINED group.  The first
        attempt that proves the group gone switches back to ``CLEANUP_PROVEN``
        and resumes the retained generation EXACTLY ONCE.  After
        ``max_cleanup_attempts`` unproven attempts the supervisor settles into an
        observable fail-closed state instead of retrying forever: no silent
        progression, no unbounded loop.
        """
        events = []
        if self.fail_closed:
            return events
        self.recovery_attempts += 1
        outcome = self._release("RECOVERY")
        if self.cleanup_state == CLEANUP_PROVEN:
            events.append("CLEANUP_PROVEN")
            events.extend(self._resume_pending())
        elif self.recovery_attempts >= self.max_cleanup_attempts:
            self.fail_closed = True
            self._log("REGENERATION_CLEANUP_FAIL_CLOSED", group_release=outcome,
                      attempts=self.recovery_attempts)
            events.append("CLEANUP_FAIL_CLOSED")
            events.extend(self._fail_closed_output())
        return events

    def _resume_pending(self) -> list:
        """Resume, EXACTLY ONCE, what the retained generation was waiting for.

        Finding D.  ONE slot, one intent, one resumption:
          * ``SUCCESS``            a render that DID succeed while its group was
                                   unproven is handed to the controller — unless
                                   a newer generation has since taken the
                                   presentation, in which case it is dropped
                                   EXPLICITLY, never silently;
          * ``REQUEST``            a newer generation asked for while the slot was
                                   unproven starts now, exactly once;
          * ``FAILED`` / ``STALLED`` the bounded failure policy decides again for
                                   that same generation: the group is proven gone,
                                   so the retry — or the truthful fallback — is
                                   safe again, and the execution count it had
                                   already spent is the one it is judged on.
        """
        pending = self.pending
        if pending is None:
            return []
        self.pending = None
        generation = int(pending["generation"])
        intent = pending["intent"]
        if intent == PENDING_SUCCESS:
            if regeneration_failure_is_stale(generation, self.current_generation()):
                self._log("REGENERATION_PENDING_SUCCESS_SUPERSEDED", optical_generation=generation,
                          current_generation=self.current_generation())
                return ["PENDING_SUCCESS_SUPERSEDED"]
            self.publish_pending = (generation, True)
            self._log("REGENERATION_PENDING_SUCCESS_RESUMED", optical_generation=generation)
            return ["PENDING_SUCCESS_RESUMED"]
        if intent == PENDING_REQUEST:
            self.generation = generation
            self.executions = 1
            self.started_at = self._clock()
            self._start(self.generation)
            self._log("REGENERATION_PENDING_GENERATION_STARTED", optical_generation=self.generation)
            return ["PENDING_GENERATION_STARTED"]
        self.generation = generation
        return [self._resolve(intent, generation, None)]

    def _safe_to_write_fallback(self, generation: int) -> bool:
        """True only when a fallback write is PROVEN unable to race a writer.

        Finding D (v6) and finding AGY-2 (v7).  The conditions, ALL required:
          * the release is PROVEN (``CLEANUP_PROVEN``).  This is the v7 absolute
            rule: while ``cleanup_state`` is UNPROVEN the release ITSELF was
            never established, so nothing here may authorise a write — a helper
            that merely ESTIMATES the group gone is guessing from its own blind
            angle, and that guess may not overwrite a valid disc sheet;
          * no process that could touch the same files is left — the retained
            group is either absent, or proven ours AND proven gone (a group
            holding only zombies holds no writer: ``process_group_liveness``
            answers GONE for it);
          * no CURRENT render would be destroyed: a disc sheet already matching
            this generation is left untouched;
          * the generation is still the current one, so the fallback describes
            the presentation it is stamped with.
        """
        if self.cleanup_state != CLEANUP_PROVEN:
            return False
        if self.group is not None:
            if not self._ownership_proven(self.group):
                return False
            if process_group_liveness(self.group.pgid, self._proc_root) != LIVENESS_GONE:
                return False
        if self._home is not None:
            try:
                if disc_sheet_is_current(self._home, self._current_optical()):
                    return False
            except OSError:
                return False
        return not regeneration_failure_is_stale(generation, self.current_generation())

    def _fail_closed_output(self) -> list:
        """At exhaustion: NEVER write.  The retained content stays as it is.

        Finding AGY-2 (v7).  v6 could still call ``_publish_fail_closed_fallback``
        here — a valid disc sheet was then overwritten and a provenance stamped
        that the release itself had never proved.  The absolute rule now lived in
        code: this method is reached ONLY at the exhaustion of the bounded
        recovery, i.e. with ``cleanup_state != CLEANUP_PROVEN``, and in that state
        NO presentation artifact may be written — neither ``disc-sheet.png``, nor
        ``disc-sheet-state.json``, nor ``flex-v1.ini``.  The last valid/stale
        content is KEPT (a stale fiche is recoverable; a fiche stamped from a
        guess is a lie the next writer can contradict).  A SUCCESS or a REQUEST
        is refused too: neither is a failed render, so neither may ever be
        restamped as a fallback.  The observable trace is a log line and the
        returned ``CLEANUP_FAIL_CLOSED_NO_WRITE`` — never a write.
        """
        pending = self.pending
        generation = int(pending["generation"]) if pending is not None else 0
        intent = pending["intent"] if pending is not None else None
        if self.cleanup_state != CLEANUP_PROVEN:
            self._log("REGENERATION_CLEANUP_FAIL_CLOSED_NO_WRITE", optical_generation=generation,
                      cleanup_state=self.cleanup_state, intent=intent,
                      event_reason="CLEANUP_UNPROVEN",
                      generation_is_current=not regeneration_failure_is_stale(
                          generation, self.current_generation()))
            return ["CLEANUP_FAIL_CLOSED_NO_WRITE"]
        # Unreachable from the exhaustion path above; a defensive refusal kept so
        # that no future caller can turn a SUCCESS / REQUEST into a fallback, nor
        # a write into a race the proof did not cover.
        if pending is None or intent not in ("FAILED", "STALLED"):
            self._log("REGENERATION_FAIL_CLOSED_NO_WRITE", optical_generation=generation,
                      cleanup_state=self.cleanup_state, intent=intent,
                      event_reason="INTENT_NOT_A_FAILURE")
            return ["CLEANUP_FAIL_CLOSED_NO_WRITE"]
        if not self._safe_to_write_fallback(generation):
            self._log("REGENERATION_FAIL_CLOSED_NO_WRITE", optical_generation=generation,
                      cleanup_state=self.cleanup_state, intent=intent,
                      event_reason="WRITER_NOT_EXCLUDED")
            return ["CLEANUP_FAIL_CLOSED_NO_WRITE"]
        return self._publish_fail_closed_fallback(pending)

    def _publish_fail_closed_fallback(self, pending: dict) -> list:
        """The truthful fallback of a generation that never rendered, once safe."""
        generation = int(pending["generation"])
        if self._home is None or self._install is None:
            return ["FAIL_CLOSED_NO_RENDERER"]
        optical = self._current_optical()
        reason = "MENU_REGENERATION_TIMEOUT" if pending["intent"] == "STALLED" else "MENU_REGENERATION_FAILED"
        published = publish_generation_fallback(self._home, self._install, optical, reason,
                                                expected_generation=generation)
        self._log("PRESENTATION_FALLBACK" if published else "PRESENTATION_FALLBACK_REFUSED",
                  optical_generation=generation, event_reason=reason, outcome="FAIL_CLOSED")
        return ["FAIL_CLOSED_FALLBACK" if published else "FAIL_CLOSED_FALLBACK_REFUSED"]

    def _resolve(self, outcome: str, failed_generation: int, released=None) -> str:
        current = self.current_generation()
        if regeneration_failure_is_stale(failed_generation, current):
            self._log("REGENERATION_FAILURE_STALE", outcome=outcome,
                      failed_generation=int(failed_generation or 0), current_generation=current,
                      executions=self.executions)
            return "STALE_FAILURE"
        if regeneration_recovery(outcome, self.executions, self.max_attempts) == "RETRY":
            if released in RELEASE_UNPROVEN or self.cleanup_state == CLEANUP_UNPROVEN:
                # A retry renders the SAME generation: starting it while the
                # previous worker's group may still be alive would put two
                # writers on one presentation.  Fall through to the fallback,
                # which publishes truthful, generation-matching provenance.
                self._log("REGENERATION_RETRY_BLOCKED_GROUP", optical_generation=int(failed_generation or 0),
                          outcome=outcome, group_release=released, executions=self.executions)
            else:
                self._log("REGENERATION_RETRY_SCHEDULED", optical_generation=int(failed_generation or 0),
                          outcome=outcome, attempt=self.executions + 1, max_attempts=self.max_attempts,
                          worker_budget_seconds=self.budget_s)
                self.executions += 1
                self.generation = int(failed_generation or 0)
                self.started_at = self._clock()
                self._start(self.generation)
                return "RETRY"
        if self._home is not None and self._install is not None:
            optical = self._current_optical()
            if disc_sheet_is_current(self._home, optical):
                self._log("PRESENTATION_FALLBACK_SKIPPED", optical_generation=current,
                          event_reason="DISC_SHEET_ALREADY_CURRENT", outcome=outcome,
                          attempts=self.executions)
                return "FALLBACK_SKIPPED"
            reason = "MENU_REGENERATION_TIMEOUT" if outcome == "STALLED" else "MENU_REGENERATION_FAILED"
            published = publish_generation_fallback(self._home, self._install, optical, reason,
                                                    expected_generation=failed_generation)
            self._log("PRESENTATION_FALLBACK" if published else "PRESENTATION_FALLBACK_REFUSED",
                      optical_generation=current, event_reason=reason, outcome=outcome,
                      attempts=self.executions)
            return "FALLBACK" if published else "FALLBACK_REFUSED"
        return "FALLBACK"


def _safe_log(log, event, **fields):
    """Journalise sans jamais abandonner un groupe retenu (l'autorité prime).

    Finding (Codex, v8).  ``log`` is the caller's logging seam — for the
    controller, a function that reaches the runtime's journal writer.  Catching
    only ``Exception`` left the class OPEN: a logger raising a ``BaseException``
    (``SystemExit`` from a broken CLI helper, ``KeyboardInterrupt`` from a
    terminal signal) escaped ``guarded_release`` and returned to a caller that
    had NOT been told the release was proven — so the caller's exit path ran
    with the retained group abandoned, which is the exact failure this gate
    exists to forbid.  No logging failure of ANY kind may decide anything here:
    the authority outranks the journal.
    """
    try:
        log(event, **fields)
    except BaseException:                    # noqa: BLE001 — a logger never decides
        pass


UNKNOWN_TYPE_NAME = "unknown-type"


def safe_type_name(value):
    """The CLASS NAME of ``value`` — total, and never raising (Codex on v9).

    Finding (Codex, v9 — blocker 2).  v9 read ``type(exc).__name__`` OUTSIDE any
    guard, in ``safe_exception_text``, in the controller's boundary and in
    ``guarded_release``'s POST-PROOF diagnostics.  Naming a value is an
    ATTRIBUTE READ, and a metaclass may implement ``__name__`` as anything —
    including a property that raises.  A description therefore decided the fate
    of the very exception it was describing: it escaped the boundary (no
    quarantine, lock released) or replaced the original instance after the
    proof (masked re-raise).

    Total by construction: the class, then its ``__name__``, then the stringness
    of that name are each read inside their own ``BaseException`` guard, so a
    hostile metaclass yields a STABLE placeholder and nothing else.  Every
    diagnostic of this module goes through here — no payload reads
    ``type(x).__name__`` outside a guard.
    """
    try:
        cls = type(value)
    except BaseException:                    # noqa: BLE001 — a diagnostic never decides anything
        return UNKNOWN_TYPE_NAME
    try:
        name = cls.__name__
    except BaseException:                    # noqa: BLE001 — a hostile metaclass lands here
        return UNKNOWN_TYPE_NAME
    try:
        if isinstance(name, str) and name:
            return name
    except BaseException:                    # noqa: BLE001
        return UNKNOWN_TYPE_NAME
    return UNKNOWN_TYPE_NAME


def safe_repr(value):
    """``repr(value)`` that NEVER raises — fail-closed diagnostics (Codex on v8).

    Finding (Codex, v8 — blocker 2).  A diagnostic may never outrank the
    authority.  ``repr()`` of an object this gate merely RETAINS (an unreaped
    ``Popen``, an object whose ``__repr__`` raises) was evaluated as an
    ARGUMENT of the logging seam — i.e. OUTSIDE the seam's own guard — so a
    raising ``__repr__`` escaped ``guarded_release`` and returned to a caller
    that had not been told the release was proven.  Every representation the
    gate emits now goes through here: a broken ``__repr__`` yields a stable
    placeholder and nothing else.
    """
    try:
        return repr(value)
    except BaseException:                    # noqa: BLE001 — a diagnostic never decides anything
        return f"<unrepresentable {safe_type_name(value)}>"


def safe_exception_text(exc):
    """A stable description of an exception, computed WITHOUT ever raising.

    Finding (Codex, v8 — blocker 2).  ``exception=str(exc)`` was evaluated
    BEFORE the non-escaping logging seam, so a custom exception whose
    ``__str__`` raised a ``BaseException`` escaped the controller's boundary,
    MASKED the original failure and never reached ``guarded_release`` at all —
    the authority was released without any proof.

    Finding (Codex, v9 — blocker 2).  The type name was read OUTSIDE the guard:
    a metaclass whose ``__name__`` raises escaped exactly the same way.  It now
    comes from :func:`safe_type_name`, which is total, and the message stays
    best-effort: when ``__str__`` refuses, a fixed placeholder is returned
    instead of propagating anything.
    """
    name = safe_type_name(exc)
    try:
        text = str(exc)
    except BaseException:                    # noqa: BLE001 — a diagnostic never decides anything
        return f"<{name}: unprintable>"
    return text


def _retained_repr(supervisor):
    """A stable description of the group the gate retains — never raises.

    ``getattr`` with a default only absorbs ``AttributeError``: a ``group``
    PROPERTY that raises would otherwise escape from inside the quarantine.  A
    diagnostic is never allowed to end the quarantine, so this absorbs
    everything and answers a placeholder.
    """
    try:
        return safe_repr(getattr(supervisor, "group", None))
    except BaseException:                    # noqa: BLE001 — a diagnostic never decides anything
        return "<unreadable retained group>"


def _recovery_interval(seconds):
    """The recovery interval as a safe, non-negative float — never raises.

    A negative or NaN interval (or a value of the wrong type) must not shorten
    the quarantine and must not escape the gate: either answers the production
    cadence instead.
    """
    try:
        value = float(seconds)
    except BaseException:                    # noqa: BLE001 — the pacing never decides anything
        return GUARDED_RECOVERY_PAUSE_S
    if not value >= 0.0:                     # NaN or negative: never shorten the quarantine
        return GUARDED_RECOVERY_PAUSE_S
    return value


# ── Pacing primitives, captured ONCE at import (blocker Codex v9-1) ──────────
# None of them is a parameter; none of them is the caller's seam; each one is a
# BOUND method or a syscall wrapper, so patching ``threading.Event.wait`` or
# ``time.sleep`` later cannot reach it.  They are named at module level so a
# review can FAULT one deliberately — a fault is absorbed like any other, and
# never ends the quarantine.
_PACE_CLOCK_WAIT = threading.Event().wait        # tier 2 — bounded clock-wait
_PACE_SELECT = select.select                     # tier 3 — kernel, not the clock


def _pace_default_clock():
    """The production monotonic clock — resolved at CALL time (a faultable seam)."""
    return time.monotonic()


_PACE_CLOCK = _pace_default_clock                # tier 0 — the deadline clock
#: The PROOF reading: the SAME physical clock, read through a DIFFERENT symbol
#: (blocker Codex v10-1).  ``_PACE_CLOCK`` is a deliberately faultable seam, and
#: a proof can never rest on the very name under test: v10 asked that one name
#: both to pace and to measure, and answered "the interval was spent" for a wait
#: it had not measured as soon as the name broke.  Both the function and the
#: clock id are captured ONCE, at import, out of the real ``time`` module — so
#: neither a later patch of ``time.monotonic`` nor a REPLACED ``time`` name can
#: reach the reading that carries the proof.  It is what keeps a broken seam from
#: turning every legitimate quarantine into a permanent hold — WITHOUT letting
#: any unmeasured wait pass for a proof.
_PACE_CLOCK_ALT_NS = time.clock_gettime_ns
_PACE_CLOCK_ALT_CLOCK_ID = time.CLOCK_MONOTONIC


def _pace_alt_clock():
    """The proof reading, in SECONDS — same physical clock, different symbol."""
    return _PACE_CLOCK_ALT_NS(_PACE_CLOCK_ALT_CLOCK_ID) / 1e9


_PACE_CLOCK_ALT = _pace_alt_clock


def _pace_now():
    """A monotonic reading in SECONDS, or ``None`` when NO clock answers.

    ``None`` means the interval cannot be PROVEN — never that the pacing is
    optional.  The caller must then fall through to its next INDEPENDENT
    primitive and, if none of them can prove either, to the conservative HOLD.
    It NEVER propagates (Codex v9-1) and it is NEVER read as a proof (Codex
    v10-1): ``None`` feeds ``_pace_wait``'s unverified branch, which answers
    False and hands the remainder — not the decision — to the next tier.
    """
    try:
        return float(_PACE_CLOCK())
    except BaseException:                    # noqa: BLE001 — a clock never decides anything
        pass
    try:
        return float(_PACE_CLOCK_ALT())
    except BaseException:                    # noqa: BLE001
        return None


def _pace_syscall_wait(interval):
    """A bounded wait through the KERNEL (``select``), independent of ``time``."""
    _PACE_SELECT([], [], [], interval)


#: The accounting demands the WHOLE interval: a waiter that under-consumes is
#: NEVER accepted as proof of a spent interval (finding Codex v10-1 — the old
#: ``0.9`` floor blessed a 10 % deficit, and any other floor would only have
#: blessed a smaller one).  What is left is the RESOLUTION of the verification
#: clock, not a discount: the deadline is a float sum, and a residual below one
#: microsecond can be spent by NOTHING (``select`` and ``Event.wait`` round UP to
#: the scheduler tick), so re-waiting it could only spin.  Every deficit a real
#: waiter can produce — an instant return, a spurious wake-up, 90 %, 99 % — is
#: orders of magnitude above this floor and is REFUSED, its remainder going to
#: the next INDEPENDENT primitive (tier 3) or to the conservative hold.
_PACE_ACCOUNTING_TOLERANCE_S = 1e-6


def _pace_deadline(interval):
    """``start + interval`` from a measured reading, or ``None`` without a clock."""
    started = _pace_now()
    if started is None:
        return None
    return started + interval


def _pace_remaining(deadline):
    """What is STILL owed on ``deadline``, or ``None`` when the clock is gone."""
    if deadline is None:
        return None
    now = _pace_now()
    if now is None:
        return None
    return deadline - now


def _pace_unavailable(tier, exc, interval, *, log, rounds):
    """Journal a waiter that RAISED — one event per tier, and no decision."""
    _safe_log(log, "HOME_PACING_UNAVAILABLE", pacing_tier=tier,
              exception_type=safe_type_name(exc), recovery_rounds=rounds,
              interval_s=interval, event_status="QUARANTINE")


def _pace_unverified(tier, interval, reason, *, log, rounds, remaining=0.0):
    """Journal a waiter that could NOT be PROVEN — the absence of proof, named."""
    _safe_log(log, "HOME_PACING_UNVERIFIED", pacing_tier=tier, pacing_reason=reason,
              remaining_s=remaining, recovery_rounds=rounds,
              interval_s=interval, event_status="QUARANTINE")


def _pace_wait(tier, waiter, deadline, *, interval, log, rounds):
    """ONE bounded wait of the REMAINDER — True ONLY with a PROOF it was spent.

    The proof is a MEASUREMENT, made with an independent clock reading before
    and after the wait.  Every other outcome answers False, which means « this
    tier proved nothing; the next INDEPENDENT primitive gets the remainder » —
    and when no tier proves anything, ``_pace_block`` ends in ``_pace_hold`` and
    never hands the loop back.  False covers ALL of:

      * a waiter that RAISED (absorbed, journalled, never a decision);
      * a waiter that returned EARLY — instantly, or after 90 % of the interval;
      * a waiter nobody could MEASURE, because no clock answers;
      * a clock lost between the two readings.

    Finding (Codex, v10 — blocker 1).  v10 trusted ``waiter`` the moment its own
    clock was unavailable (``started is None`` ⇒ ``return True``): a clock-wait
    that returned immediately WITHOUT raising was counted as a spent interval,
    ``_PACE_SELECT`` was never reached, and the recovery loop ran unpaced.  An
    unverifiable waiter is not a measurement — it is now never True.
    """
    remaining = _pace_remaining(deadline)
    if remaining is None:
        # No clock answers at all: NOTHING here can be proven.  The bounded
        # primitive is still spent (fail-closed direction, never a shortcut to a
        # proof), then the next tier is tried — and only a HOLD can end this.
        try:
            waiter(interval)
        except BaseException as exc:         # noqa: BLE001 — a wait never decides anything
            _pace_unavailable(tier, exc, interval, log=log, rounds=rounds)
        else:
            _pace_unverified(tier, interval, "CLOCK_UNAVAILABLE", log=log, rounds=rounds)
        return False
    if remaining <= _PACE_ACCOUNTING_TOLERANCE_S:
        return True                          # nothing is owed: the interval is spent
    try:
        waiter(remaining)
    except BaseException as exc:             # noqa: BLE001 — a wait never decides anything
        _pace_unavailable(tier, exc, interval, log=log, rounds=rounds)
        return False
    left = _pace_remaining(deadline)
    if left is None:
        _pace_unverified(tier, interval, "CLOCK_LOST", log=log, rounds=rounds)
        return False
    if left <= _PACE_ACCOUNTING_TOLERANCE_S:
        return True                          # FULL interval accounted: the only proof
    _pace_unverified(tier, interval, "UNDERSPENT", log=log, rounds=rounds, remaining=left)
    return False


def _pace_hold(*, log, rounds):
    """THE LAST RESORT: hold the quarantine instead of returning to the loop.

    Finding (Codex, v9 — blocker 1, last clause).  When every BOUNDED primitive
    is broken the interval cannot be spent — so the pacing must not pretend it
    was.  A "conservative hold" is the fail-closed answer: this process keeps
    the only memory identity of the retained group and its ``ui-session.lock``,
    so it stays here, blocked, instead of handing control back to a recovery
    loop that would spin on the same broken primitives.

    Finding (Codex, v10 — blocker 1, third clause).  « Broken » is not the only
    way to lose the interval: a tier can also be UNPROVABLE — no clock answers,
    so nothing measured the wait.  Losing the MEASUREMENT is the same verdict as
    losing the primitive: an unproven interval is never returned to the loop, so
    the hold is also the answer when the gate cannot prove what it spent.

    Each primitive below is a blocking operation with NO timeout: a ``Event``
    created fresh on every iteration (it cannot have been set in advance), then
    ``signal.pause`` (a syscall that returns only when a signal arrives).  They
    consume no CPU while they block.  Nothing is published, no worker is
    started, no exec and no exit happens: only a PROOF could end the quarantine,
    and a proof requires a drain that this hold never re-runs.

    Honest limit: an actor that made BOTH primitives raise would leave this loop
    retrying — busy, but still inside the quarantine, with the identity and the
    session lock retained.  There is no path from here to an exit, an exec or a
    release.
    """
    _safe_log(log, "HOME_PACING_HOLD", recovery_rounds=rounds,
              event_status="QUARANTINE",
              event_reason="PACING_INTERVAL_UNPROVEN")
    while True:
        try:
            threading.Event().wait()         # fresh, never set: blocks for good
        except BaseException:                # noqa: BLE001 — a hold never decides anything
            try:
                signal.pause()               # last resort: a syscall, no clock at all
            except BaseException:            # noqa: BLE001
                pass                         # still no escape, no release, no proof


def _pace_block(deadline, interval, *, log, rounds):
    """Spend the REMAINDER on the gate's OWN primitives — or HOLD, never return.

    The two bounded tiers below are INDEPENDENT of the caller's seam and of each
    other (a clock-wait, then a raw kernel wait), and each one must PROVE the
    interval it covered.  A tier that cannot prove hands the REMAINDER over
    rather than the decision: the deadline is shared, so a tier that spent half
    of it leaves half to spend — never a rescheduled interval, never an accepted
    deficit.  When neither can prove, the gate HOLDS.
    """
    if _pace_wait("CLOCK_WAIT", _PACE_CLOCK_WAIT, deadline, interval=interval, log=log, rounds=rounds):
        return
    if _pace_wait("SELECT", _pace_syscall_wait, deadline, interval=interval, log=log, rounds=rounds):
        return
    _pace_hold(log=log, rounds=rounds)


def _pace(sleep, seconds, *, log, rounds):
    """Spend ONE recovery interval — fail-closed, NEVER a spin, never a decision.

    Finding (Codex, v8 — blocker 1).  ``sleep(recovery_pause_s)`` sat OUTSIDE
    the ``BaseException`` guard: a sleeper that raised during an UNPROVEN
    cleanup killed HOME, released ``ui-session.lock``, abandoned the retained
    ``WorkerGroup`` and could even mask the caller's original exception —
    exactly the failure this gate exists to forbid.

    Finding (Codex, v9 — blocker 1).  Two escapes and one spin survived v8:
    ``type(exc).__name__`` and ``time.monotonic()`` were evaluated OUTSIDE any
    guard, and the CLOCK_WAIT tier answered ``return`` the moment its own wait
    failed — so a quarantine whose clock-wait was broken returned instantly on
    every round and became a busy-loop (Codex: 10 000 nominal 10 ms rounds in
    8 ms).

    Finding (Codex, v10 — blocker 1).  v10 measured the interval with ONE name,
    the very name an actor can fault, and read an unverifiable waiter as a spent
    interval: with the clock broken and a clock-wait that returned instantly
    WITHOUT raising, ``_PACE_SELECT`` was never reached and the loop ran unpaced.
    The model is now ONE accounting routine over ONE deadline, and no tier
    inherits another's proof:

      * TIER 0 — the deadline, read from TWO independent clocks.  A missing
        reading is never a proof: it forbids the tier and triggers the fall-through.
      * TIER 1 — the caller's sleeper.  ONE call, then MEASURED.  Its failure is
        absorbed and journalled; its early return is not trusted; either way the
        gate's own tiers get the REMAINDER of the SAME deadline.
      * TIER 2 — the gate's own bounded clock-wait (``_PACE_CLOCK_WAIT``).
      * TIER 3 — an independent, bounded KERNEL wait (``select``), captured at
        import, so a broken ``time`` module cannot disable it.
      * TIER 4 — a conservative HOLD (``_pace_hold``): unusable — or simply
        unprovable — bounded primitives mean the quarantine STAYS HELD, blocked,
        never handed back.

    The objective is fail-closed authority, not temporal precision: over-spending
    is acceptable, returning early is not.  Only a PROOF reaches the loop; a
    missing proof reaches the HOLD.  Only the RELEASE PROOF ends the quarantine.
    """
    interval = _recovery_interval(seconds)
    deadline = _pace_deadline(interval)
    if _pace_wait("SEAM", sleep, deadline, interval=interval, log=log, rounds=rounds):
        return
    _pace_block(deadline, interval, log=log, rounds=rounds)


def guarded_release(supervisor, drain, log, *, reason, sleep=time.sleep,
                    recovery_pause_s: float = GUARDED_RECOVERY_PAUSE_S,
                    max_recovery_rounds: int | None = None, exception=None):
    """Hold the controller ALIVE until its worker's group is PROVEN released (v7).

    Finding (Codex on v6).  v6 drained ONCE and, when the release could not be
    proven, exited with ``EXIT_CLEANUP_UNPROVEN``.  Leaving WAS the bug: this
    process holds the only memory identity of the worker's group (the captured
    ``WorkerGroup``, whose unreaped pid pins the pgid) AND the ``ui-session.lock``
    it inherited on fd 8.  Exiting releases both, so the next plain
    ``openhtpc-session-start`` starts a controller that races a group nobody
    remembers — and no later attempt can identify it.

    ``drain(reason)`` is the controller's bounded, ownership-respecting drain
    (``supervisor.shutdown()``).  Until it PROVES the release:
      * nothing is published, no new worker is started, and the caller does NOT
        exec or exit — its exit path is GATED on this function returning True;
      * the process STAYS ALIVE and keeps its authority (identity + session lock);
      * the bounded drain is retried at a spaced cadence (``recovery_pause_s``) —
        paced, never a CPU spin.  The pacing itself is FAIL-CLOSED (``_pace``):
        a sleeper that fails is absorbed, the interval is still spent on the
        gate's own blocking clock-wait, and the quarantine goes on.

    Returns True once the release is proven (the caller may then act), or False
    when ``max_recovery_rounds`` bounds the quarantine — a TEST-ONLY bound:
    production passes ``None`` and NEVER abandons a retained group.

    ``exception`` (the controller's exception boundary): when given, it is
    journalised and RE-RAISED — the very SAME instance, unchanged — after the
    proof.  No unhandled exception may abandon a live or unproven group, and
    none is ever masked.  When NO exception is given (a planned departure), a
    failure of the sleeper still cannot create a premature unguarded exit: the
    only way out of this function remains the PROOF.
    """
    bound = None
    if max_recovery_rounds is not None:
        try:
            bound = int(max_recovery_rounds)
        except BaseException:                # noqa: BLE001 — the bound is TEST-ONLY bookkeeping
            bound = None
    rounds = 0
    while True:
        try:
            may_exit = bool(drain(reason))
        except BaseException as exc:         # noqa: BLE001 — the quarantine cannot itself escape
            _safe_log(log, "HOME_DRAIN_EXCEPTION", exception_type=safe_type_name(exc),
                      retained_worker=_retained_repr(supervisor),
                      event_status="QUARANTINE")
            may_exit = False
        if may_exit:
            break
        rounds += 1
        _safe_log(log, "HOME_GUARDED_RECOVERY", authority="RETAINED", recovery_rounds=rounds,
                  retained_worker=_retained_repr(supervisor),
                  event_status="QUARANTINE")
        if bound is not None and rounds >= bound:
            return False
        _pace(sleep, recovery_pause_s, log=log, rounds=rounds)
    _safe_log(log, "HOME_AUTHORITY_RELEASE_PROVEN", recovery_rounds=rounds, event_reason=reason)
    if exception is not None:
        # Finding (Codex, v9 — blocker 2, post-proof clause).  Naming the
        # exception here read ``type(exception).__name__`` UNGUARDED: a hostile
        # metaclass raised from the diagnostic and MASKED the instance this gate
        # had just proven it could re-raise.  Only SAFE diagnostics now, and the
        # raise is the LAST statement — of the very same object.
        _safe_log(log, "HOME_SESSION_EXCEPTION_RERAISED",
                  exception_type=safe_type_name(exception))
        raise exception
    return True


def plugin_menu_entries(home: pathlib.Path, install: pathlib.Path) -> list[dict[str, str]]:
    core_path = install / "openhtpc-core.py"
    if not core_path.is_file():
        return []
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location("openhtpc_core", core_path)
        core = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(core)
        plugins, errors = core.installed_plugins(home, install)
        if errors:
            return []
        result = []
        for plugin in sorted(plugins, key=lambda item: item["plugin_id"]):
            for entry in plugin["menu_entries"]:
                if isinstance(entry, dict) and isinstance(entry.get("label"), str) and isinstance(entry.get("command"), str):
                    command = entry["command"]
                    if command.startswith(str(install) + "/") and "\n" not in command and ";" not in command:
                        result.append({"label": entry["label"], "command": command})
        return result
    except (OSError, AttributeError, TypeError):
        return []


def evaluate(home: pathlib.Path) -> dict:
    root = home / ".config/openhtpc"
    profile = load_object(root / "profile.json", "hardware_profile", "PROFILE_MISSING", "PROFILE_INVALID")
    validate_profile(profile)
    snapshot_path = root / "runtime/capabilities.json"
    snapshot = load_object(snapshot_path, "capabilities", "CAPABILITIES_MISSING", "CAPABILITIES_INVALID") if snapshot_path.exists() else {}
    validate_capability_provenance(profile, snapshot)
    decision = viability(profile)
    if decision["status"] != "PASS":
        raise GateError("viability", "MACHINE_NOT_VIABLE", "; ".join(decision["failures"]))
    validate_runtime(profile, home)
    user = load_object(root / "user-config.json", "initial_configuration", "CONFIGURATION_MISSING", "CONFIGURATION_INVALID")
    sources = validate_user_config(user, root / "secrets/tmdb-token")
    return {"profile": profile, "viability": decision, "user_config": user, "sources": sources}
