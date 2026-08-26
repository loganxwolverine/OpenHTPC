#!/usr/bin/env python3
"""Keep the running HOME menu synchronized with canonical optical state."""
import hashlib, importlib.util, json, os, pathlib, subprocess, sys, time

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
    st = optical_state()
    if tmdb is None:
        return ""
    title = st.get("tmdb_title") or st.get("disc_title") or st.get("volume_label") or ""
    cache_target = tmdb.cache_path(home, st, str(title))
    if cache_target is None:
        return ""
    identity = str(st.get("disc_id") or f"{int(st.get('generation', 0) or 0)}:{optical.canonical_state(st)}")
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

def full_state_key():
    st = optical_state()
    return (int(st.get("generation", 0) or 0), optical_key(), disc_presentation_signature())

def regenerate():
    state = engine.evaluate(home)
    engine.write_flex_config(target, home, state["sources"])
    if runtime:
        runtime.log(home, "ui", "MENU_GENERATED", menu_generation=engine.menu_identity(target), optical_generation=optical_state().get("generation", 0), current_optical_state=optical_state().get("state"))

if len(sys.argv) >= 2 and sys.argv[1] == "--regenerate-only":
    target = pathlib.Path(sys.argv[2])
    generation = int(sys.argv[3])
    state = engine.evaluate(home)
    changed = engine.write_flex_config(target, home, state["sources"], expected_optical_generation=generation)
    if changed and runtime:
        st = optical_state()
        runtime.log(home, "ui", "MENU_GENERATED", menu_generation=engine.menu_identity(target), optical_generation=st.get("generation", 0), current_optical_state=st.get("state"))
    raise SystemExit(0 if changed else 3)

disc_view = install / "openhtpc-disc-view.py"
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

regenerate()
engine.activate_media_manifest(target, home)
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

start_enrichment()
if runtime:
    runtime.log(home, "ui", "FLEX_STARTED", ui_instance_identity=f"flex-{proc.pid}", authoritative_flex_pid=proc.pid, session_id=os.environ.get("OPENHTPC_SESSION_ID", "unknown"), start_reason="SESSION_START", caller_component="home-controller", caller_pid=os.getpid(), optical_generation=optical_state().get("generation", 0), menu_generation=engine.menu_identity(target), current_optical_state=optical_state().get("state"))

key = full_state_key()
regenerator = None
regenerator_generation = None
regenerator_started = None

def request_regeneration():
    global regenerator, regenerator_generation, regenerator_started
    st = optical_state(); generation = int(st.get("generation", 0) or 0)
    media = optical.presentation(st); icon = install / "assets/ui" / media["icon"]
    engine.write_live_optical_state(home, st, icon)
    if regenerator is not None and regenerator.poll() is None:
        regenerator.terminate()
        try: regenerator.wait(timeout=1)
        except subprocess.TimeoutExpired: regenerator.kill(); regenerator.wait()
    regenerator_generation = generation
    regenerator_started = time.monotonic()
    regenerator = subprocess.Popen(
        [sys.executable, str(pathlib.Path(__file__)), "--regenerate-only", str(target), str(generation)],
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True
    )

while proc.poll() is None:
    time.sleep(0.3)
    if enricher is not None and enricher.poll() is not None:
        completed_enrichment_generation = current_enrichment_generation
        enricher = None
        request_regeneration()
    if regenerator is not None and regenerator.poll() is None and regenerator_started is not None and time.monotonic()-regenerator_started > 5:
        regenerator.terminate()
        try: regenerator.wait(timeout=1)
        except subprocess.TimeoutExpired: regenerator.kill(); regenerator.wait()
        stale_generation = regenerator_generation
        regenerator = None
        current = optical_state()
        if stale_generation == int(current.get("generation", 0) or 0):
            engine.publish_generation_fallback(home, install, current, "MENU_REGENERATION_TIMEOUT")
            if runtime:
                runtime.log(home,"ui","PRESENTATION_FALLBACK",optical_generation=stale_generation,event_reason="MENU_REGENERATION_TIMEOUT")
    if regenerator is not None and regenerator.poll() is not None:
        completed_generation = regenerator_generation
        successful = regenerator.returncode == 0
        regenerator = None
        if successful and completed_generation == int(optical_state().get("generation", 0) or 0):
            start_enrichment()
    newest = full_state_key()
    if newest!=key:
        key = newest
        request_regeneration()
        if runtime:
            runtime.log(home, "ui", "OPTICAL_GENERATION_DEFERRED", flex_pid=proc.pid, action_type="STATE_UPDATE", source_page="ANY", destination_page="CURRENT", optical_generation=optical_state().get("generation", 0))

if runtime:
    runtime.record_flex_exit(home, proc.returncode, time.monotonic() - started)
    runtime.log(home, "ui", "FLEX_STOPPED", ui_instance_identity=f"flex-{proc.pid}", stop_reason="NORMAL_EXIT" if proc.returncode == 0 else "CRASH", caller_component="flex", caller_pid=proc.pid, returncode=proc.returncode)
raise SystemExit(proc.returncode)
