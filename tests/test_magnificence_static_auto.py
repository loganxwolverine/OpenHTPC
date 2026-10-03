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
policy = load("magnificence_static_policy", PAYLOAD / "openhtpc-playback-policy.py")


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


def make_family_home(vendor_id: str, device_id: str, model: str, width: int = 3840, height: int = 2160):
    temp, home = make_home(device_id=device_id, width=width, height=height)
    caps_path = home / ".config/openhtpc/runtime/capabilities.json"
    caps = json.loads(caps_path.read_text(encoding="utf-8"))
    caps["graphics"] = {
        "devices": [{
            "active": True,
            "vendor_id": vendor_id,
            "device_id": device_id,
            "model": model,
            "video_decode": {"backends": {
                "vaapi": {"profiles": {"mpeg2": vendor_id != "10de"}},
                "nvdec": {"profiles": {"mpeg2": vendor_id == "10de"}},
            }},
        }],
        "vulkan": {"devices": [{"vendor_id": vendor_id, "device_id": device_id, "name": model}]},
    }
    caps_path.write_text(json.dumps(caps), encoding="utf-8")
    return temp, home


def test_hardware_passport_processing_gpu_wins_over_boot_igpu_active_flag():
    temp, home = make_home(device_id="1912", width=3840, height=2160)
    try:
        caps_path = home / ".config/openhtpc/runtime/capabilities.json"
        caps = json.loads(caps_path.read_text(encoding="utf-8"))
        caps["graphics"]["devices"] = [
            {"active": True, "pci_address": "0000:00:02.0", "vendor_id": "8086", "device_id": "1912", "model": "Intel HD Graphics 530"},
            {"active": None, "pci_address": "0000:03:00.0", "vendor_id": "8086", "device_id": "56a6", "model": "Intel Arc A310"},
        ]
        caps_path.write_text(json.dumps(caps), encoding="utf-8")
        (home / ".config/openhtpc/profile.json").write_text(json.dumps({
            "gpu_selection": {"gpu": {
                "pci_slot": "0000:03:00.0", "vendor_id": "8086", "device_id": "56a6", "model": "Intel Arc A310"
            }}
        }), encoding="utf-8")

        decision = cinema.query("DVD_PAL_FILM", home=home)
        assert decision["reason"] == "QUALIFIED_STATIC_PROFILE"
        assert decision["profile_id"] == "intel_arc_a310_8086_56a6_sd_2160p"
        assert decision["recipe_id"] == "RECIPE_MAG_SD_FSRCNNX16_KRIG_VIBRANCE_MILD"
    finally:
        temp.cleanup()


def test_gtx1660_reference_rule_does_not_override_capability_baseline():
    temp, home = make_family_home("10de", "2184", "NVIDIA GeForce GTX 1660")
    try:
        decision = cinema.query("DVD_PAL_FILM", home=home)
        assert decision["selection_source"] == "GPU_KNOWLEDGE_DB"
        assert decision["reason"] == "CAPABILITY_BASELINE_LIGHT"
        assert decision["classification_tier"] == "LIGHT"
        assert decision["recipe_id"] == "RECIPE_MAG_FAMILY_LIGHT_KRIG"
    finally:
        temp.cleanup()


def test_rx6750xt_reference_rule_does_not_override_capability_baseline():
    temp, home = make_family_home("1002", "73df", "AMD Radeon RX 6750 XT")
    try:
        decision = cinema.query("DVD_PAL_FILM", home=home)
        assert decision["selection_source"] == "GPU_KNOWLEDGE_DB"
        assert decision["reason"] == "CAPABILITY_BASELINE_LIGHT"
        assert decision["classification_tier"] == "LIGHT"
        assert decision["recipe_id"] == "RECIPE_MAG_FAMILY_LIGHT_KRIG"
    finally:
        temp.cleanup()


def test_unknown_capable_gpu_gets_light_baseline_instead_of_pure():
    temp, home = make_family_home("1234", "5678", "Future GPU Unknown Model")
    try:
        decision = cinema.query("DVD_PAL_FILM", home=home)
        assert decision["selection_source"] == "GPU_KNOWLEDGE_DB"
        assert decision["reason"] == "CAPABILITY_BASELINE_LIGHT"
        assert decision["classification_tier"] == "LIGHT"
        assert decision["recipe_id"] == "RECIPE_MAG_FAMILY_LIGHT_KRIG"
    finally:
        temp.cleanup()


def test_gtx1660_choice_loads_only_light_shader_chain():
    temp, home = make_family_home("10de", "2184", "NVIDIA GeForce GTX 1660")
    try:
        choice = policy._magnificence_choice(home, "dvd", None)
        assert choice["classification_tier"] == "LIGHT"
        assert [pathlib.Path(p).name for p in choice["shader_files"]] == ["KrigBilateral.glsl"]
    finally:
        temp.cleanup()


def test_rx6750xt_choice_stays_on_light_baseline_while_reference_only():
    temp, home = make_family_home("1002", "73df", "AMD Radeon RX 6750 XT")
    try:
        choice = policy._magnificence_choice(home, "dvd", None)
        names = [pathlib.Path(p).name for p in choice["shader_files"]]
        assert choice["classification_method"] == "CAPABILITY_BASELINE_LIGHT"
        assert choice["classification_tier"] == "LIGHT"
        assert names == ["KrigBilateral.glsl"]
    finally:
        temp.cleanup()


def test_generation_regex_rules_match_real_model_names():
    knowledge = json.loads((PAYLOAD / "assets/magnificence_gpu_knowledge.json").read_text(encoding="utf-8"))
    cases = [
        ("10de", "NVIDIA GeForce RTX 4090", "HIGH"),
        ("10de", "NVIDIA GeForce RTX 5090", "HIGH"),
        ("10de", "NVIDIA GeForce RTX 2060", "MEDIUM"),
        ("10de", "NVIDIA GeForce GTX 980", "LIGHT"),
        ("1002", "AMD Radeon RX 9070 XT", "HIGH"),
    ]
    for vendor_id, model, expected_tier in cases:
        rule = policy._magnificence_family_rule({"vendor_id": vendor_id, "model": model}, knowledge, include_reference=True)
        assert rule is not None, model
        assert rule["tier"] == expected_tier, model


def test_malformed_passport_json_fails_closed_without_crash():
    temp, home = make_family_home("1234", "5678", "Future GPU Unknown Model")
    try:
        (home / ".config/openhtpc/profile.json").write_text("[]", encoding="utf-8")
        choice = policy._magnificence_choice(home, "dvd", None)
        assert choice is not None
        assert choice["classification_tier"] == "LIGHT"
    finally:
        temp.cleanup()


def test_ambiguous_multigpu_without_pci_identity_falls_back_to_pure():
    temp, home = make_home(device_id="1912", width=3840, height=2160)
    try:
        caps_path = home / ".config/openhtpc/runtime/capabilities.json"
        caps = json.loads(caps_path.read_text(encoding="utf-8"))
        caps["graphics"]["devices"] = [
            {"active": None, "pci_address": "0000:01:00.0", "vendor_id": "10de", "device_id": "2184", "model": "NVIDIA GeForce GTX 1660"},
            {"active": None, "pci_address": "0000:02:00.0", "vendor_id": "10de", "device_id": "2184", "model": "NVIDIA GeForce GTX 1660"},
        ]
        caps["graphics"]["vulkan"] = {"devices": [
            {"vendor_id": "10de", "device_id": "2184", "name": "NVIDIA GeForce GTX 1660"},
            {"vendor_id": "10de", "device_id": "2184", "name": "NVIDIA GeForce GTX 1660"},
        ]}
        caps_path.write_text(json.dumps(caps), encoding="utf-8")
        (home / ".config/openhtpc/profile.json").write_text("[]", encoding="utf-8")
        decision = cinema.query("DVD_PAL_FILM", home=home)
        assert decision["recipe_id"] == "RECIPE_0_PURE"
        assert decision["reason"] == "FALLBACK_NO_QUALIFIED_PROFILE"
    finally:
        temp.cleanup()
