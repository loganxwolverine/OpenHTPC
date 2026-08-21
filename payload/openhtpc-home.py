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

def optical_state():
    try: return json.loads((home / ".local/state/openhtpc/optical-current.json").read_text())
    except (OSError, json.JSONDecodeError): return {}

def optical_key():
    return optical.ui_state_hash(optical_state())

def disc_presentation_signature():
    st = optical_state()
    disc_id = st.get("disc_id")
    if not disc_id:
        return ""
    cache_target = home / ".local/share/openhtpc/media-cache/dvd" / hashlib.sha256(str(disc_id).encode()).hexdigest() / "metadata.json"
    if not cache_target.is_file():
        return f"{disc_id}:NO_CACHE"
    try:
        data = json.loads(cache_target.read_text(encoding="utf-8"))
        status = data.get("status", "")
        if status == "PASS":
            return f"{disc_id}:PASS:{data.get('tmdb_id')}:{data.get('confidence')}"
        elif status == "AMBIGUOUS":
            c_ids = ",".join(str(c.get("tmdb_id") or c.get("id")) for c in data.get("candidates", []))
            return f"{disc_id}:AMBIGUOUS:{c_ids}"
        return f"{disc_id}:{status}"
    except Exception:
        return f"{disc_id}:ERR"

def full_state_key():
    return (optical_key(), disc_presentation_signature())

def regenerate():
    state = engine.evaluate(home)
    engine.write_flex_config(target, home, state["sources"])
    if runtime:
        runtime.log(home, "ui", "MENU_GENERATED", menu_generation=engine.menu_identity(target), optical_generation=optical_state().get("generation", 0), current_optical_state=optical_state().get("state"))

disc_view = install / "openhtpc-disc-view.py"
enricher = None
current_enrichment_disc_id = None

def start_enrichment():
    global enricher, current_enrichment_disc_id
    st = optical_state()
    disc_id = st.get("disc_id")
    if not disc_id:
        if enricher is not None:
            try:
                enricher.terminate()
                enricher.wait(timeout=0.2)
            except Exception:
                pass
            enricher = None
            current_enrichment_disc_id = None
        return

    if enricher is not None and enricher.poll() is None:
        if current_enrichment_disc_id == disc_id:
            return
        try:
            enricher.terminate()
            enricher.wait(timeout=0.2)
        except Exception:
            pass
        enricher = None

    if disc_view.is_file():
        current_enrichment_disc_id = disc_id
        gen = st.get("generation", 0)
        enricher = subprocess.Popen(
            [str(disc_view), "--home", str(home), "--enrich", "--disc-id", str(disc_id), "--generation", str(gen)],
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
settled = False
while proc.poll() is None:
    time.sleep(0.3)
    if not settled:
        settled = True
        regenerate()
    if enricher is not None and enricher.poll() is not None:
        enricher = None
        regenerate()
    newest = full_state_key()
    if newest!=key:
        key = newest
        regenerate()
        start_enrichment()
        if runtime:
            runtime.log(home, "ui", "OPTICAL_GENERATION_DEFERRED", flex_pid=proc.pid, action_type="STATE_UPDATE", source_page="ANY", destination_page="CURRENT", optical_generation=optical_state().get("generation", 0))

if runtime:
    runtime.record_flex_exit(home, proc.returncode, time.monotonic() - started)
    runtime.log(home, "ui", "FLEX_STOPPED", ui_instance_identity=f"flex-{proc.pid}", stop_reason="NORMAL_EXIT" if proc.returncode == 0 else "CRASH", caller_component="flex", caller_pid=proc.pid, returncode=proc.returncode)
raise SystemExit(proc.returncode)

