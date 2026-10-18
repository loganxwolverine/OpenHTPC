#!/usr/bin/env python3
"""Keep the running HOME menu synchronized with canonical optical state."""
import atexit, hashlib, importlib.util, json, os, pathlib, signal, subprocess, sys, time

home = pathlib.Path(os.environ.get("OPENHTPC_HOME", pathlib.Path.home()))
install = pathlib.Path(os.environ.get("OPENHTPC_INSTALL_DIR", home / ".local/lib/openhtpc"))
def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

engine = load("session_engine", install / "openhtpc-session-engine.py")
target = pathlib.Path(sys.argv[1]) if len(sys.argv) == 2 else engine.canonical_flex_config_path(home)
runtime = load("runtime", install / "openhtpc-runtime.py") if (install / "openhtpc-runtime.py").is_file() else None
optical = load("optical", install / "openhtpc-optical.py")
tmdb = load("home_tmdb", install / "openhtpc-tmdb.py") if (install / "openhtpc-tmdb.py").is_file() else None

def optical_state():
    try: return json.loads((home / ".local/state/openhtpc/optical-current.json").read_text())
    except (OSError, json.JSONDecodeError): return {}

def optical_key():
    return optical.ui_state_hash(optical_state())

def disc_presentation_signature():
    """Metadata/enrichment signature — one implementation, in the engine."""
    return engine.enrichment_presentation_signature(home, optical_state(), tmdb)

def protected_capability_signature():
    value = optical.protected_capability(home)
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()

def optical_transition_key():
    """Identity of a real optical transition: generation + canonical UI state.

    Deliberately EXCLUDES the enrichment signature.  The enricher rewrites the
    TMDb cache as it progresses; those intermediate writes used to look like new
    optical transitions and spawned a regeneration worker that the next write
    killed a second later.
    """
    st = optical_state()
    return (int(st.get("generation", 0) or 0), optical_key(), protected_capability_signature())

def enrichment_presentation_key():
    """Identity of the metadata/enrichment presentation alone."""
    return disc_presentation_signature()

def regenerate():
    state = engine.evaluate(home)
    engine.publish_flex_config(target, home, state["sources"])
    if runtime:
        runtime.log(home, "ui", "MENU_GENERATED", menu_generation=engine.menu_identity(target), optical_generation=optical_state().get("generation", 0), current_optical_state=optical_state().get("state"))

if len(sys.argv) >= 2 and sys.argv[1] == "--regenerate-only":
    target = pathlib.Path(sys.argv[2])
    generation = int(sys.argv[3])
    state = engine.evaluate(home)
    changed = engine.write_flex_config(
        target, home, state["sources"], expected_optical_generation=generation,
        # The engine reads the active MEDIA generation under its publication lock.
    )
    if changed and runtime:
        st = optical_state()
        runtime.log(home, "ui", "MENU_GENERATED", menu_generation=engine.menu_identity(target), optical_generation=st.get("generation", 0), current_optical_state=st.get("state"))
    raise SystemExit(0 if changed else 3)

disc_view = install / "openhtpc-disc-view.py"
media_control = load("media_update_control", install / "openhtpc-media-update-control.py")
media_action_control = load("media_action_control", install / "openhtpc-media-action-control.py")
media_search_control = load("media_search_control", install / "openhtpc-media-search-control.py")
media_activity = load("media_activity", install / "openhtpc-media-activity.py")
enricher = None
current_enrichment_generation = None
completed_enrichment_generation = None

def start_enrichment():
    global enricher, current_enrichment_generation, completed_enrichment_generation
    st = optical_state()
    generation = int(st.get("generation", 0) or 0)
    canonical = optical.canonical_state(st)
    title = st.get("tmdb_title") or st.get("disc_title") or st.get("volume_label") or ""
    configured = (home / ".config/openhtpc/secrets/tmdb-token").is_file()
    eligible = canonical in {"DVD_VIDEO", "BLURAY_VIDEO", "UHD_BLURAY_VIDEO", "BLURAY_FAMILY"} and bool(str(title).strip()) and configured
    if completed_enrichment_generation == generation:
        return
    if not eligible:
        if enricher is not None:
            try:
                enricher.terminate()
                enricher.wait(timeout=0.2)
            except Exception:
                pass
            enricher = None
            current_enrichment_generation = None
            completed_enrichment_generation = None
        return

    if enricher is not None and enricher.poll() is None:
        if current_enrichment_generation == generation:
            return
        try:
            enricher.terminate()
            enricher.wait(timeout=0.2)
        except Exception:
            pass
        enricher = None

    if disc_view.is_file():
        current_enrichment_generation = generation
        command = [str(disc_view), "--home", str(home), "--enrich", "--generation", str(generation)]
        if st.get("disc_id"):
            command.extend(["--disc-id", str(st["disc_id"])])
        enricher = subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True
        )

# Failsafe: Flex Launcher must never be spawned when SDL has no usable graphical device
cap_path = install / "openhtpc-capabilities.py"
has_graphical = False
if cap_path.is_file():
    try:
        spec = importlib.util.spec_from_file_location("openhtpc_capabilities", cap_path)
        if spec and spec.loader:
            caps = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(caps)
            if hasattr(caps, "is_graphical_context_usable") and caps.is_graphical_context_usable(dict(os.environ)):
                has_graphical = True
            elif hasattr(caps, "resolve_graphical_context"):
                env_proc = os.environ.get("OPENHTPC_PROC_ROOT")
                proc_root = pathlib.Path(env_proc) if env_proc else pathlib.Path("/proc")
                ctx = caps.resolve_graphical_context(proc_root=proc_root, home=home, install=install)
                if ctx.get("status") == "RESOLVED" and ctx.get("environment"):
                    if not hasattr(caps, "is_graphical_context_usable") or caps.is_graphical_context_usable(ctx["environment"]):
                        os.environ.update(ctx["environment"])
                        has_graphical = True
    except Exception:
        pass
if not has_graphical:
    has_graphical = bool(os.environ.get("WAYLAND_DISPLAY") or os.environ.get("DISPLAY"))

if not has_graphical:
    if runtime:
        runtime.log(home, "ui", "FLEX_START_BLOCKED_NO_GRAPHICAL_SESSION")
    raise SystemExit("OPENHTPC: démarrage Flex impossible sans session graphique active (OPENHTPC_GRAPHICAL_SESSION_UNAVAILABLE).")

regenerate()
pass_fds = ()
try:
    lock_fd = int(os.environ.get("OPENHTPC_SESSION_LOCK_FD", "-1"))
    if lock_fd >= 0:
        os.fstat(lock_fd)
        pass_fds = (lock_fd,)
except (ValueError, OSError):
    pass_fds = ()

if runtime and runtime.crash_loop_state(home)["blocked"]:
    runtime.log(home, "ui", "FLEX_START_BLOCKED_CRASH_LOOP", crash_count=runtime.crash_loop_state(home)["count"])
    raise SystemExit("OPENHTPC: démarrage Flex suspendu après trois échecs en cinq minutes; consultez openhtpc doctor.")

started = time.monotonic()
if runtime:
    existing = runtime.managed_processes(home, install)["ui"]
    if existing:
        runtime.log(home, "ui", "FLEX_DUPLICATE_START_BLOCKED", existing_pids=existing)
        raise SystemExit("OPENHTPC: une instance Flex autoritaire existe déjà.")

proc = subprocess.Popen([str(install / "flex/bin/flex-launcher"), "-c", str(target)], pass_fds=pass_fds)
if runtime:
    try: session = json.loads(runtime.paths(home)["session"].read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError): session = {"schema": 2, "state": "RUNNING"}
    session.update(authoritative_flex_pid=proc.pid, ui_generation=engine.menu_identity(target), session_id=os.environ.get("OPENHTPC_SESSION_ID", session.get("session_id", "unknown")))
    runtime.atomic_json(runtime.paths(home)["session"], session)

try:
    flex_observed = runtime is None
    deadline = time.monotonic() + 2.0
    while runtime and proc.poll() is None and time.monotonic() < deadline:
        if proc.pid in runtime.managed_processes(home, install)["ui"]:
            flex_observed = True
            break
        time.sleep(0.02)
    engine.render_system_pages(home, install)
    if runtime:
        runtime.log(home, "ui", "SYSTEM_PAGES_POST_START_REFRESHED", authoritative_flex_pid=proc.pid, flex_observed=flex_observed)
except Exception as exc:
    # Flex is already the authoritative UI. A diagnostic image refresh must
    # never orphan it or turn a successful session start into a crash loop.
    if runtime:
        runtime.log(home, "ui", "SYSTEM_PAGES_POST_START_REFRESH_FAILED", authoritative_flex_pid=proc.pid, error_type=engine.safe_type_name(exc))

start_enrichment()
if runtime:
    runtime.log(home, "ui", "FLEX_STARTED", ui_instance_identity=f"flex-{proc.pid}", authoritative_flex_pid=proc.pid, session_id=os.environ.get("OPENHTPC_SESSION_ID", "unknown"), start_reason="SESSION_START", caller_component="home-controller", caller_pid=os.getpid(), optical_generation=optical_state().get("generation", 0), menu_generation=engine.menu_identity(target), current_optical_state=optical_state().get("state"))

key = optical_transition_key()
enrichment_key = enrichment_presentation_key()
previous_optical_state = optical_state()
pending_auto_open_generation = 0
pending_eject_home_generation = 0
update_controller = media_control.UpdateController(home, install)
action_controller = media_action_control.ActionController(home, install)
search_controller = media_search_control.SearchController(home, install)
activity_publisher = media_activity.ActivityPublisher(home)
atexit.register(update_controller.close)
atexit.register(action_controller.close)
atexit.register(search_controller.close)
atexit.register(activity_publisher.close)
stop_requested = False
stop_signal = None

def stop_home(received_signal, _frame):
    global stop_requested, stop_signal
    stop_requested = True
    try:
        stop_signal = signal.Signals(received_signal).name
    except (ValueError, TypeError):
        stop_signal = str(received_signal)
    if runtime:
        runtime.log(home, "ui", "HOME_STOP_SIGNAL_RECEIVED", signal=stop_signal, flex_pid=proc.pid)

signal.signal(signal.SIGTERM, stop_home)
signal.signal(signal.SIGINT, stop_home)

def request_regeneration():
    st = optical_state(); generation = int(st.get("generation", 0) or 0)
    media = optical.presentation(st); icon = install / "assets/ui" / media["icon"]
    engine.write_live_optical_state(home, st, icon)
    supervisor.request(generation)

def spawn_regeneration_worker(generation):
    """Spawn one regeneration worker.

    It is started as a session leader (``start_new_session=True``) so that its
    own children — the disc-sheet render, the media-graph rebuild — share its
    process group: that group is what the engine terminates on a stall, and
    signalling the parent PID alone would leave them running.
    """
    return subprocess.Popen(
        [sys.executable, str(pathlib.Path(__file__)), "--regenerate-only", str(target), str(generation)],
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True
    )

def log_controller_event(event, **fields):
    """The controller's SINGLE logging seam — and it NEVER escapes.

    Finding (Codex, v8).  This callable is handed to the regeneration supervisor
    AND to ``engine.guarded_release``, and the exception boundary below calls it
    BEFORE the gate.  A journal write that fails — an unwritable state
    directory, a full disk, a runtime diagnostic that raises — therefore used to
    REPLACE the exception being reported and to skip the gate entirely: the
    original failure was masked AND the authority was released without proof.  A
    logger decides nothing, so a logger may raise nothing: this is exactly what
    ``engine._safe_log`` already does for the gate's own events, applied here to
    every event of this controller, before any handler can lose the story.
    """
    if runtime:
        try:
            runtime.log(home, "ui", event, **fields)
        except BaseException:                # noqa: BLE001 — a logger never decides
            pass

# The worker's whole lifecycle lives in the engine, where it is executable in a
# test: this controller only publishes a render it has accepted as successful.
supervisor = engine.RegenerationSupervisor(
    spawn=spawn_regeneration_worker,
    current_optical=optical_state,
    home=home,
    install=install,
    log=log_controller_event,
)

def drain_supervisor_for_exit(reason):
    """ONE bounded, ownership-respecting drain attempt before HOME leaves.

    Finding E (v6), tightened by finding Codex (v7).  Every way out of this
    controller funnels through here — the stop signal, the end of the loop, and
    the Flex-recovery replacement.  The controller is NOT an authority on the
    worker's group: it asks the engine, which applies the same rules as
    everywhere else (captured group, no single-process fallback, no reap before
    the proof).

    Returns True only when the release is PROVEN and leaving is therefore safe.
    False is NOT a decision to leave anyway: a fresh controller would race a
    worker it knows nothing about, and the retained identity would die with the
    process that held it.  ``engine.guarded_release`` — not this function — owns
    what happens next, and it answers False by KEEPING this process alive (and
    its ui-session.lock held) and retrying here at a spaced cadence.
    """
    may_exit, outcome, events = supervisor.shutdown()
    if may_exit:
        if events != ["SHUTDOWN_CLEAN"]:
            log_controller_event("HOME_DRAIN_COMPLETE", event_reason=reason,
                                 group_release=outcome, flex_pid=proc.pid)
        return True
    log_controller_event("HOME_DRAIN_CLEANUP_UNPROVEN", event_reason=reason,
                         group_release=outcome, flex_pid=proc.pid,
                         retained_worker=repr(supervisor.group), event_status="FAIL_CLOSED")
    return False

class PlannedDeparture(BaseException):
    """The departure this controller DECIDED on — raised only AFTER the proof.

    The boundary below journals and quarantines FAILURES; a departure is not
    one.  ``PlannedDeparture`` is raised at the very end of a normal path
    (a stop signal, a Flex exit, a Flex recovery replacement), only once
    ``engine.guarded_release`` has returned True — i.e. only once the worker's
    group is PROVEN released and leaving cannot orphan anything.  The boundary
    lets it through as a plain ``SystemExit``: a clean exit stays clean, is never
    journalled as a failure, and is never quarantined a second time.  It is a
    ``BaseException`` on purpose, so that no ``except Exception`` of a future
    caller can turn leaving into a recovered failure.

    It carries no payload: the status is the one the body computed for the
    departure it decided on, and the boundary raises EXACTLY the v7 statement —
    ``SystemExit(0 if stop_requested else (proc.returncode or 0))`` — from its
    departure handler, which is reachable in no other way.
    """


def controller_loop():
    """Run the dev11 menu loop, then LEAVE only once the worker is proven gone.

    The order of the loop is the dev11 contract and is NOT touched by this
    tranche (render -> publish -> navigation detection).

    Finding (Codex, v7).  v6 drained ONCE and, when the release could not be
    proven, exited with ``EXIT_CLEANUP_UNPROVEN``.  Leaving WAS the bug: this
    process holds the only memory identity of the worker's group (the captured
    ``WorkerGroup``, whose unreaped pid pins the pgid) AND the ``ui-session.lock``
    it inherited on fd 8.  Every way out therefore funnels through the SAME gate,
    ``engine.guarded_release``: it keeps this process alive — identity and lock
    held — and retries the bounded drain, PACED, until the release is PROVEN;
    only then does the requested action run, exactly once.

    Finding (Codex, v8) — ONE TOTAL BOUNDARY.  v7 drew the boundary around the
    LOOP only; everything that ran AFTER it was still bare.  The crash-loop
    lookup (``runtime.crash_loop_state``), the recovery/exit DECISION, the two
    exit gates and any exception THEY raise escaped the controller with no drain
    at all: HOME died, released ``ui-session.lock`` and abandoned a retained
    group — precisely the failure the gate exists to prevent, and a logger
    raising on the way out could even mask the original exception before the
    gate was ever reached.

    In v8 the WHOLE post-supervisor life is inside ONE boundary: the loop, the
    crash-loop lookup, the recovery/exit decision, the ``FLEX_RECOVERY``
    replacement and the ordinary ``STOP_SIGNAL`` / ``FLEX_EXIT`` departures —
    and the diagnostics of every one of them.  No exception raised anywhere in
    that life can leave it: it is journalled (by a seam that cannot raise), the
    SAME gate quarantines this process until the release is PROVEN, and the
    exception is then re-raised EXACTLY as it was raised.  No ``execv``, no
    exit, no ``SystemExit`` and no re-raise can happen before that proof.

    A PLANNED departure (``PlannedDeparture``, raised at the end of a normal
    path once the gate returned True) is let through as a plain ``SystemExit``:
    a clean exit stays a clean exit.
    """

    global pending_auto_open_generation, pending_eject_home_generation
    global enricher, completed_enrichment_generation
    global key, enrichment_key, previous_optical_state
    try:
        while proc.poll() is None and not stop_requested:
            time.sleep(0.3)
            if stop_requested:
                break
            update_controller.poll()
            action_controller.poll()
            search_controller.poll()
            activity_publisher.poll()
            if enricher is not None and enricher.poll() is not None:
                completed_enrichment_generation = current_enrichment_generation
                enricher = None
                request_regeneration()
                # The completion is the one settled regeneration of this enrichment
                # episode.  Consume the metadata signature it carries: without this, a
                # write that lands in the same interval as the exit would be seen by the
                # trigger below as a fresh settled change and request a SECOND
                # regeneration for the same enrichment.
                enrichment_key = enrichment_presentation_key()
            # The supervisor owns the worker's whole lifecycle: watchdog, bounded retry,
            # stale-failure rejection, process-group termination and the guarded
            # fallback.  It never publishes a successful render — that stays below, in
            # the order the dev11 contract fixes.
            supervisor.tick()
            # The supervisor is the ONLY authority on its worker: the controller NEVER
            # calls poll()/wait() on supervisor.proc.  A concurrent poll() here could
            # reap the leader between the supervisor's non-reaping check and this line,
            # clearing the worker and losing a surviving descendant with it.  Instead the
            # supervisor hands back a render it accepted as successful AND whose process
            # group it PROVED released; the controller only publishes it, in the dev11
            # order (render -> publish -> navigation detection).
            pending_publication = supervisor.take_publishable()
            if pending_publication is not None:
                completed_generation, successful = pending_publication
                if successful and completed_generation == int(optical_state().get("generation", 0) or 0):
                    current = optical_state(); media = optical.presentation(current); icon = install / "assets/ui" / media["icon"]
                    engine.write_live_optical_state(home, current, icon,
                                                    pending_auto_open_generation, pending_eject_home_generation)
                    if completed_generation == pending_auto_open_generation:
                        pending_auto_open_generation = 0
                    if completed_generation == pending_eject_home_generation:
                        pending_eject_home_generation = 0
                    supervisor.note_published()
                    start_enrichment()
            newest_optical = optical_transition_key()
            newest_enrichment = enrichment_presentation_key()
            optical_changed = newest_optical != key
            enrichment_changed = newest_enrichment != enrichment_key
            key = newest_optical
            enrichment_key = newest_enrichment
            trigger = engine.regeneration_trigger(optical_changed, enrichment_changed,
                                                  enricher is not None and enricher.poll() is None)
            if trigger == "OPTICAL":
                current = optical_state()
                auto_generation, eject_generation = engine.optical_navigation_event(previous_optical_state, current)
                previous_optical_state = current
                if auto_generation:
                    pending_auto_open_generation = auto_generation
                    pending_eject_home_generation = 0
                elif eject_generation:
                    pending_auto_open_generation = 0
                    pending_eject_home_generation = eject_generation
                request_regeneration()
                if runtime:
                    # Report the navigation decision actually taken.  The former
                    # hardcoded STATE_UPDATE / "CURRENT" made a requested-then-lost
                    # navigation read as a deliberate choice to stay on the page.
                    deferred_action = "AUTO_OPEN" if auto_generation else "EJECT_HOME" if eject_generation else "STATE_UPDATE"
                    deferred_page = "DISQUE" if auto_generation else "OPENHTPC" if eject_generation else "CURRENT"
                    runtime.log(home, "ui", "OPTICAL_GENERATION_DEFERRED", flex_pid=proc.pid, action_type=deferred_action, source_page="ANY", destination_page=deferred_page, optical_generation=optical_state().get("generation", 0))
            elif trigger == "ENRICHMENT":
                # The metadata signature settled (the enricher finished): this is the one
                # regeneration that carries the enriched title.
                request_regeneration()
            elif trigger == "SUPPRESSED_ENRICHMENT":
                # An intermediate write of the enricher is not an optical transition: a
                # worker started here would be killed by the next write.
                log_controller_event("REGENERATION_TRIGGER_SUPPRESSED", flex_pid=proc.pid,
                                     event_reason="ENRICHMENT_IN_PROGRESS", source_page="ANY",
                                     destination_page="CURRENT", optical_generation=optical_state().get("generation", 0))

        if stop_requested and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()

        activity_publisher.close()
        search_controller.close()
        action_controller.close()
        update_controller.close()
        if runtime:
            if stop_requested:
                runtime.log(home, "ui", "FLEX_STOPPED", ui_instance_identity=f"flex-{proc.pid}", stop_reason="SIGNAL_STOP", caller_component="home-controller", caller_pid=os.getpid(), flex_pid=proc.pid, signal=stop_signal, returncode=proc.returncode)
            else:
                runtime.record_flex_exit(home, proc.returncode, time.monotonic() - started)
                runtime.log(home, "ui", "FLEX_STOPPED", ui_instance_identity=f"flex-{proc.pid}", stop_reason="NORMAL_EXIT" if proc.returncode == 0 else "CRASH", caller_component="flex", caller_pid=proc.pid, returncode=proc.returncode)

        # In appliance mode, a vanished Flex window must never leave only KWin and a
        # black screen behind.  A zero exit status is not proof that the user asked
        # to leave OPENHTPC: only the controller's explicit stop intent is
        # authoritative.  The crash-loop protection is preserved so a persistently
        # broken Flex cannot restart forever.
        if not stop_requested:
            blocked = runtime.crash_loop_state(home)["blocked"] if runtime else False
            if not blocked:
                # Finding Codex (v7): the replacement is GATED.  It may only happen
                # once the worker's group is PROVEN released — the gate below keeps
                # this process alive (identity + ui-session.lock held) and retries,
                # paced, until that proof; in production it never returns False, so
                # a retained group is never abandoned.
                if engine.guarded_release(supervisor, drain_supervisor_for_exit, log_controller_event,
                                          reason="FLEX_RECOVERY", sleep=time.sleep,
                                          recovery_pause_s=engine.GUARDED_RECOVERY_PAUSE_S):
                    if runtime:
                        runtime.log(home, "ui", "FLEX_RECOVERY_REQUESTED", failed_pid=proc.pid, returncode=proc.returncode)
                    os.execv(sys.executable, [sys.executable, str(pathlib.Path(__file__)), str(target)])
        # The ordinary exits drain through the SAME gate (finding E, v6): a stop or a
        # Flex exit taken while the worker's group is retained is not a clean exit.
        engine.guarded_release(supervisor, drain_supervisor_for_exit, log_controller_event,
                               reason="STOP_SIGNAL" if stop_requested else "FLEX_EXIT", sleep=time.sleep,
                               recovery_pause_s=engine.GUARDED_RECOVERY_PAUSE_S)
        raise PlannedDeparture()
    except PlannedDeparture:
        # A DECIDED exit, reached only past the gate — the statement OBEYED in the
        # body is the gate call right above the departure.  Hand the runtime the
        # very status v7 raised here: no second quarantine, no journal entry, no
        # re-entered gate.  A clean exit stays a clean exit.
        raise SystemExit(0 if stop_requested else (proc.returncode or 0))
    except BaseException as exc:
        # THE boundary (finding Codex, v8).  Everything above is one life: the
        # loop, the crash-loop lookup, the recovery/exit decision and every way
        # out of them.  An exception from ANY of those is journalled through the
        # seam that cannot raise (so the original failure is never replaced by
        # the logger's), quarantined by the SAME gate — this process stays alive
        # and keeps its ``ui-session.lock`` until the worker's group is PROVEN
        # released — and only then re-raised, unchanged.
        #
        # Finding (Codex, v8 — blocker 2).  The description of ``exc`` is built
        # by ``engine.safe_exception_text``: ``str(exc)`` here used to be
        # evaluated BEFORE the seam, so a custom exception whose ``__str__``
        # raised escaped this very handler, masked the original failure and
        # skipped the gate entirely.  The type name comes from the CLASS and the
        # message is best-effort, so NOTHING about the exception can decide here.
        #
        # Finding (Codex, v9 — blocker 2).  ``type(exc).__name__`` was still read
        # UNGUARDED here — and naming a value is an ATTRIBUTE READ a hostile
        # metaclass may make raise.  The name now comes from
        # ``engine.safe_type_name``, which is total: nothing about the exception
        # can decide here, not even its name.
        log_controller_event("HOME_SESSION_LOOP_FAILED",
                             exception_type=engine.safe_type_name(exc),
                             exception=engine.safe_exception_text(exc))
        engine.guarded_release(supervisor, drain_supervisor_for_exit, log_controller_event,
                               reason="EXCEPTION", sleep=time.sleep,
                               recovery_pause_s=engine.GUARDED_RECOVERY_PAUSE_S, exception=exc)
        raise


# The controller's whole post-supervisor life — the loop, the crash-loop lookup,
# the recovery/exit decision and EVERY way out of them — is owned by one gate.
# While a supervised group or an UNPROVEN cleanup exists nothing leaves: the
# process stays alive holding its authority (identity + ui-session.lock), and the
# bounded drain is retried, paced, until the release is PROVEN.  One boundary
# covers that whole life, so no exception can escape it and none is ever masked.
controller_loop()
