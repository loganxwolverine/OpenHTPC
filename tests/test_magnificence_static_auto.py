from __future__ import annotations

import importlib.util
import json
import pathlib
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
PAYLOAD = ROOT / "payload"


def load(name: str, path: pathlib.Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


cinema = load("magnificence_static_cinema", PAYLOAD / "openhtpc-cinema-auto.py")
video_profile = load("magnificence_static_profile", PAYLOAD / "openhtpc-video-profile.py")


def make_home(device_id: str = "67df", width: int = 3840, height: int = 2160):
    temp = tempfile.TemporaryDirectory()
    home = pathlib.Path(temp.name)
    runtime = home / ".config/openhtpc/runtime"
    runtime.mkdir(parents=True)
    caps = {
        "hardware": {"cpu": {"model": "Intel(R) Core(TM) i7-7700 CPU @ 3.60GHz"}},
        "graphics": {"devices": [{
            "active": True,
            "vendor_id": "1002",
            "device_id": device_id,
            "model": "AMD Radeon test GPU",
        }]},
        "display": {"active_output": {"current_mode": {
            "width": width,
            "height": height,
            "refresh_hz": 60.0,
        }}},
    }
    (runtime / "capabilities.json").write_text(json.dumps(caps), encoding="utf-8")
    return temp, home


def test_cinema_auto_uses_static_rx580_profile_without_performance_map():
    temp, home = make_home()
    try:
        assert not (home / ".local/state/openhtpc/performance_map.json").exists()
        decision = cinema.query("DVD_PAL_FILM", home=home)
        assert decision["selection_source"] == "STATIC_PROFILE_DB"
        assert decision["reason"] == "QUALIFIED_STATIC_PROFILE"
        assert decision["profile_id"] == "amd_rx580_1002_67df_sd_2160p"
        assert decision["recipe_id"] == "RECIPE_MAG_SD_FSRCNNX16_KRIG_SSIM_VIBRANCE_MILD"
        assert decision["map_status"] == "NOT_REQUIRED"
    finally:
        temp.cleanup()


def test_cinema_auto_unknown_gpu_falls_back_to_pure_without_calibration():
    temp, home = make_home(device_id="ffff")
    try:
        decision = cinema.query("DVD_PAL_FILM", home=home)
        assert decision["recipe_id"] == "RECIPE_0_PURE"
        assert decision["reason"] == "FALLBACK_NO_QUALIFIED_PROFILE"
        assert decision["selection_source"] == "STATIC_PROFILE_DB"
    finally:
        temp.cleanup()


def test_video_profile_status_reports_static_profile_ready_without_map():
    temp, home = make_home()
    try:
        status = video_profile.cinema_auto_status(home, PAYLOAD)
        assert status["selection_source"] == "STATIC_PROFILE_DB"
        assert status["profile_available"] is True
        assert status["profile_id"] == "amd_rx580_1002_67df_sd_2160p"
        assert status["selected_recipe"] == "RECIPE_MAG_SD_FSRCNNX16_KRIG_SSIM_VIBRANCE_MILD"
        assert status["can_activate"] is True
        assert status["map_present"] is True  # compatibility field, now profile availability
        assert not (home / ".local/state/openhtpc/performance_map.json").exists()
    finally:
        temp.cleanup()


def test_static_profile_is_resolution_scoped():
    temp, home = make_home(width=1920, height=1080)
    try:
        decision = cinema.query("DVD_PAL_FILM", home=home)
        assert decision["recipe_id"] == "RECIPE_0_PURE"
        assert decision["reason"] == "FALLBACK_NO_QUALIFIED_PROFILE"
    finally:
        temp.cleanup()
