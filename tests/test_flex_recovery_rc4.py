from pathlib import Path

PAYLOAD = Path(__file__).resolve().parents[1] / "payload"


def _recovery_block() -> str:
    source = (PAYLOAD / "openhtpc-home.py").read_text(encoding="utf-8")
    start = source.index("# In appliance mode, a vanished Flex window")
    end = source.index("raise SystemExit(0 if stop_requested else", start)
    return source[start:end]


def test_unrequested_flex_exit_requests_bounded_recovery():
    block = _recovery_block()
    assert "if not stop_requested:" in block
    assert 'runtime.crash_loop_state(home)["blocked"]' in block
    assert '"FLEX_RECOVERY_REQUESTED"' in block
    assert "os.execv(sys.executable" in block


def test_recovery_is_not_conditioned_on_zero_or_nonzero_returncode():
    block = _recovery_block()
    assert "proc.returncode == 0" not in block
    assert "proc.returncode != 0" not in block


def test_explicit_stop_intent_remains_authoritative():
    source = (PAYLOAD / "openhtpc-home.py").read_text(encoding="utf-8")
    signal_guard = source.index("stop_requested = False")
    loop_guard = source.index("while proc.poll() is None and not stop_requested:")
    recovery_guard = source.index("if not stop_requested:", loop_guard)
    final_exit = source.index("raise SystemExit(0 if stop_requested else", recovery_guard)
    assert signal_guard < loop_guard < recovery_guard < final_exit


def test_controller_signal_stop_is_not_recorded_as_flex_crash():
    source = (PAYLOAD / "openhtpc-home.py").read_text(encoding="utf-8")
    assert '"HOME_STOP_SIGNAL_RECEIVED"' in source
    assert 'stop_reason="SIGNAL_STOP"' in source
    assert "if stop_requested and proc.poll() is None:" in source
    assert "proc.terminate()" in source
    signal_branch = source.index("if stop_requested:", source.index("activity_publisher.close()"))
    crash_record = source.index("runtime.record_flex_exit", signal_branch)
    else_branch = source.rfind("else:", signal_branch, crash_record)
    assert signal_branch < else_branch < crash_record


def test_runtime_accepts_signal_stop_reason():
    source = (PAYLOAD / "openhtpc-runtime.py").read_text(encoding="utf-8")
    assert '"SIGNAL_STOP"' in source.split("STOP_REASONS", 1)[1].split("\n", 1)[0]


def test_session_cleanup_stops_controller_before_flex_watchdog_target():
    source = (PAYLOAD / "openhtpc-runtime.py").read_text(encoding="utf-8")
    cleanup = source[source.index("def cleanup_legacy"):source.index("def stop_session")]
    stop = source[source.index("def stop_session"):source.index("def status")]
    expected_order = 'for kind in ("controllers", "ui", "monitor"):'
    assert expected_order in cleanup
    assert expected_order in stop
