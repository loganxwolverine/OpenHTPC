from __future__ import annotations

import importlib.util
import json
import pathlib
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
PAYLOAD = ROOT / "payload"
SPEC = importlib.util.spec_from_file_location(
    "magnificence_policy_test", PAYLOAD / "openhtpc-playback-policy.py"
)
policy = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(policy)


def make_home() -> tuple[tempfile.TemporaryDirectory, pathlib.Path]:
    temp = tempfile.TemporaryDirectory()
    home = pathlib.Path(temp.name)
    runtime = home / ".config/openhtpc/runtime"
    runtime.mkdir(parents=True)
    caps = {
        "graphics": {"devices": [{
            "active": True, "vendor_id": "8086", "device_id": "46d4",
            "model": "Intel Corporation Alder Lake-N [Intel Graphics]",
        }]},
        "display": {"active_output": {
            "current_mode": {"width": 1920, "height": 1080, "refresh_hz": 60.0}
        }},
    }
    (runtime / "capabilities.json").write_text(json.dumps(caps), encoding="utf-8")
    policy.write_preference(home, "presentation_mode", "CINEMA_AUTO")
    return temp, home


def test_n150_dvd_resolves_krig():
    temp, home = make_home()
    try:
        decision = policy.resolve(home, kind="dvd", gpu_binding={"mpv_args": []})
        assert decision["presentation"]["resolved"] == "RECIPE_C2_DVD_KRIG_BILATERAL"
        assert decision["presentation"]["reason"] == "magnificence_profile"
        assert decision["presentation"]["profile_id"] == "intel_n150_8086_46d4_sd_1080p"
        assert any(
            arg.startswith("--glsl-shaders=") and "KrigBilateral.glsl" in arg
            for arg in decision["mpv_args"]
        )
    finally:
        temp.cleanup()


def test_n150_local_576p_uses_same_profile():
    temp, home = make_home()
    try:
        probe = {"streams": [{
            "codec_type": "video", "codec_name": "mpeg2video",
            "width": 720, "height": 576, "r_frame_rate": "25/1",
        }]}
        decision = policy.resolve(home, kind="local", probe=probe, gpu_binding={"mpv_args": []})
        assert decision["presentation"]["resolved"] == "RECIPE_C2_DVD_KRIG_BILATERAL"
    finally:
        temp.cleanup()


def test_1080p_local_falls_back_to_pure():
    temp, home = make_home()
    try:
        probe = {"streams": [{
            "codec_type": "video", "codec_name": "h264",
            "width": 1920, "height": 1080, "r_frame_rate": "24/1",
        }]}
        decision = policy.resolve(home, kind="local", probe=probe, gpu_binding={"mpv_args": []})
        assert decision["presentation"]["resolved"] == "PURE"
        assert not any(arg.startswith("--glsl-shaders=") for arg in decision["mpv_args"])
    finally:
        temp.cleanup()


def test_pure_never_adds_magnificence_shader():
    temp, home = make_home()
    try:
        policy.write_preference(home, "presentation_mode", "PURE")
        decision = policy.resolve(home, kind="dvd", gpu_binding={"mpv_args": []})
        assert decision["presentation"]["resolved"] == "PURE"
        assert decision["presentation"]["reason"] == "requested_pure"
        assert not any(arg.startswith("--glsl-shaders=") for arg in decision["mpv_args"])
    finally:
        temp.cleanup()


def test_magnificence_database_is_installed():
    installer = (PAYLOAD / "install-openhtpc-fedora.sh").read_text(encoding="utf-8")
    manifest = (PAYLOAD / "managed-files.txt").read_text(encoding="utf-8")
    assert 'assets/magnificence_profiles.json' in manifest
    assert 'assets/magnificence_profiles.json' in installer
    assert '$INSTALL_DIR/assets/magnificence_profiles.json' in installer
