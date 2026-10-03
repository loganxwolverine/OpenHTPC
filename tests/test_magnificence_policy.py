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


def test_720p_film_is_classified_but_falls_back_until_profile_exists():
    temp, home = make_home()
    try:
        probe = {"streams": [{
            "codec_type": "video", "codec_name": "h264",
            "width": 1280, "height": 536,
            "r_frame_rate": "24000/1001", "avg_frame_rate": "24000/1001",
            "field_order": "progressive",
        }]}
        assert policy._magnificence_source_scope("local", probe) == "HD_720P_FILM"
        decision = policy.resolve(home, kind="local", probe=probe, gpu_binding={"mpv_args": []})
        assert decision["presentation"]["resolved"] == "PURE"
        assert decision["presentation"]["reason"] == "no_qualified_magnificence_profile"
        assert not any(arg.startswith("--glsl-shaders=") for arg in decision["mpv_args"])
    finally:
        temp.cleanup()


def test_720p_high_frame_rate_is_not_folded_into_film_profile():
    temp, home = make_home()
    try:
        probe = {"streams": [{
            "codec_type": "video", "codec_name": "h264",
            "width": 1280, "height": 720,
            "r_frame_rate": "50/1", "avg_frame_rate": "50/1",
            "field_order": "progressive",
        }]}
        assert policy._magnificence_source_scope("local", probe) is None
        decision = policy.resolve(home, kind="local", probe=probe, gpu_binding={"mpv_args": []})
        assert decision["presentation"]["resolved"] == "PURE"
    finally:
        temp.cleanup()


def test_720p_interlaced_is_not_folded_into_film_profile():
    temp, home = make_home()
    try:
        probe = {"streams": [{
            "codec_type": "video", "codec_name": "h264",
            "width": 1280, "height": 720,
            "r_frame_rate": "25/1", "avg_frame_rate": "25/1",
            "field_order": "tt",
        }]}
        assert policy._magnificence_source_scope("local", probe) is None
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
    assert 'assets/magnificence_gpu_knowledge.json' in manifest
    assert 'assets/magnificence_gpu_knowledge.json' in installer
    assert '$INSTALL_DIR/assets/magnificence_gpu_knowledge.json' in installer


def test_all_profiles_use_static_hardware_tiers_without_runtime_benchmark_selection():
    profiles = json.loads((PAYLOAD / "assets/magnificence_profiles.json").read_text(encoding="utf-8"))
    expected = {
        "intel_n150_8086_46d4_sd_1080p": "LIGHT",
        "amd_picasso_15d8_vega3_sd_2160p": "LIGHT",
        "intel_arc_a310_8086_56a6_sd_2160p": "MEDIUM",
        "intel_hd630_8086_5912_sd_1080p": "MEDIUM",
        "nvidia_rtx3050_10de_2507_sd_2160p": "HIGH",
        "amd_rx580_1002_67df_sd_2160p": "STRONG",
        "amd_rx5700xt_1002_731f_sd_2160p": "HIGH",
    }
    assert set(profiles["profiles"]) == set(expected)
    for profile_id, tier in expected.items():
        profile = profiles["profiles"][profile_id]
        assert profile["gpu"]["hardware_class"] == tier
        assert profile["classification"]["gpu_tier"] == tier
        assert profile["classification"]["runtime_benchmark_required"] is False
        assert profile["magnificence"]["fallback_recipe"] == "RECIPE_0_PURE"


def test_all_selected_magnificence_shaders_are_cataloged_and_managed():
    profiles = json.loads((PAYLOAD / "assets/magnificence_profiles.json").read_text(encoding="utf-8"))
    catalog = json.loads((PAYLOAD / "assets/shaders/catalog.json").read_text(encoding="utf-8"))
    manifest = (PAYLOAD / "managed-files.txt").read_text(encoding="utf-8").splitlines()
    by_filename = {entry["filename"]: entry for entry in catalog["shaders"].values()}

    selected = {
        shader
        for profile in profiles["profiles"].values()
        for shader in profile.get("magnificence", {}).get("selected_shaders", [])
    }
    assert selected
    for shader in selected:
        assert (PAYLOAD / "assets/shaders" / shader).is_file(), shader
        assert shader in by_filename, shader
        assert by_filename[shader].get("redistributable") is True, shader
        assert by_filename[shader].get("license"), shader
        assert f"assets/shaders/{shader}" in manifest, shader


def test_evolving_gpu_knowledge_is_limited_to_frozen_magnificence_shader_set():
    knowledge = json.loads((PAYLOAD / "assets/magnificence_gpu_knowledge.json").read_text(encoding="utf-8"))
    allowed = {
        "KrigBilateral.glsl",
        "FSRCNNX_x2_8-0-4-1.glsl",
        "FSRCNNX_x2_16-0-4-1.glsl",
        "FSRCNN_x2_r2_32-0-2.glsl",
        "SSimSuperRes.glsl",
        "OpenHTPC_Vibrance_Mild.glsl",
    }
    assert set(knowledge["shader_allowlist"]) == allowed
    used = {
        shader
        for recipe in knowledge["family_recipes"].values()
        for shader in recipe.get("shaders", [])
    }
    assert used <= allowed
    assert not any(name.startswith(("RAVU", "ArtCNN", "CfL")) for name in used)
    assert knowledge["policy"]["runtime_benchmark_required"] is False


def make_vega_home(cpu_model: str) -> tuple[tempfile.TemporaryDirectory, pathlib.Path]:
    temp = tempfile.TemporaryDirectory()
    home = pathlib.Path(temp.name)
    runtime = home / ".config/openhtpc/runtime"
    runtime.mkdir(parents=True)
    caps = {
        "hardware": {"cpu": {"model": cpu_model}},
        "graphics": {"devices": [{
            "active": True, "vendor_id": "1002", "device_id": "15d8",
            "model": "AMD Picasso/Raven 2",
        }]},
        "display": {"active_output": {
            "current_mode": {"width": 3840, "height": 2160, "refresh_hz": 60.0}
        }},
    }
    (runtime / "capabilities.json").write_text(json.dumps(caps), encoding="utf-8")
    policy.write_preference(home, "presentation_mode", "CINEMA_AUTO")
    return temp, home


def test_vega3_3200ge_4k_resolves_krig():
    temp, home = make_vega_home("AMD Ryzen 3 PRO 3200GE w/ Radeon Vega Graphics")
    try:
        decision = policy.resolve(home, kind="dvd", gpu_binding={"mpv_args": []})
        assert decision["presentation"]["resolved"] == "RECIPE_C2_DVD_KRIG_BILATERAL"
        assert decision["presentation"]["profile_id"] == "amd_picasso_15d8_vega3_sd_2160p"
        assert any("KrigBilateral.glsl" in arg for arg in decision["mpv_args"])
    finally:
        temp.cleanup()


def test_same_15d8_on_other_cpu_does_not_match_vega3_profile():
    temp, home = make_vega_home("AMD Ryzen 5 3500U with Radeon Vega Mobile Gfx")
    try:
        decision = policy.resolve(home, kind="dvd", gpu_binding={"mpv_args": []})
        assert decision["presentation"]["resolved"] == "PURE"
        assert decision["presentation"]["reason"] == "no_qualified_magnificence_profile"
        assert not any(arg.startswith("--glsl-shaders=") for arg in decision["mpv_args"])
    finally:
        temp.cleanup()

def test_playback_refresh_uses_cached_magnificence_model():
    source = (PAYLOAD / "openhtpc-system-action").read_text(encoding="utf-8")
    assert 'model={"available":True,"playback_policy":policy.read_preferences(home)}' in source
    assert 'magnificence_from_capabilities(caps,install)' in source


def make_arc_home() -> tuple[tempfile.TemporaryDirectory, pathlib.Path]:
    temp = tempfile.TemporaryDirectory()
    home = pathlib.Path(temp.name)
    runtime = home / ".config/openhtpc/runtime"
    runtime.mkdir(parents=True)
    caps = {
        "hardware": {"cpu": {"model": "Intel(R) Core(TM) i5-6500 CPU @ 3.20GHz"}},
        "graphics": {"devices": [{
            "active": True, "vendor_id": "8086", "device_id": "56a6",
            "model": "Intel Corporation DG2 [Arc A310]",
        }]},
        "display": {"active_output": {
            "current_mode": {"width": 3840, "height": 2160, "refresh_hz": 60.0}
        }},
    }
    (runtime / "capabilities.json").write_text(json.dumps(caps), encoding="utf-8")
    policy.write_preference(home, "presentation_mode", "CINEMA_AUTO")
    return temp, home


def test_arc_a310_4k_resolves_fsrcnnx16_krig_vibrance():
    temp, home = make_arc_home()
    try:
        decision = policy.resolve(home, kind="dvd", gpu_binding={"mpv_args": []})
        assert decision["presentation"]["resolved"] == "RECIPE_MAG_SD_FSRCNNX16_KRIG_VIBRANCE_MILD"
        assert decision["presentation"]["profile_id"] == "intel_arc_a310_8086_56a6_sd_2160p"
        shader_args = [arg for arg in decision["mpv_args"] if arg.startswith("--glsl-shaders=")]
        assert len(shader_args) == 1
        assert "FSRCNNX_x2_16-0-4-1.glsl" in shader_args[0]
        assert "KrigBilateral.glsl" in shader_args[0]
        assert "OpenHTPC_Vibrance_Mild.glsl" in shader_args[0]
        assert shader_args[0].index("FSRCNNX_x2_16-0-4-1.glsl") < shader_args[0].index("KrigBilateral.glsl")
        assert shader_args[0].index("KrigBilateral.glsl") < shader_args[0].index("OpenHTPC_Vibrance_Mild.glsl")
    finally:
        temp.cleanup()


def test_arc_a310_1080p_has_no_4k_profile():
    temp, home = make_arc_home()
    try:
        caps_path = home / ".config/openhtpc/runtime/capabilities.json"
        caps = json.loads(caps_path.read_text(encoding="utf-8"))
        caps["display"]["active_output"]["current_mode"]["width"] = 1920
        caps["display"]["active_output"]["current_mode"]["height"] = 1080
        caps_path.write_text(json.dumps(caps), encoding="utf-8")
        decision = policy.resolve(home, kind="dvd", gpu_binding={"mpv_args": []})
        assert decision["presentation"]["resolved"] == "PURE"
    finally:
        temp.cleanup()

def make_rtx3050_home() -> tuple[tempfile.TemporaryDirectory, pathlib.Path]:
    temp = tempfile.TemporaryDirectory()
    home = pathlib.Path(temp.name)
    runtime = home / ".config/openhtpc/runtime"
    runtime.mkdir(parents=True)
    caps = {
        "hardware": {"cpu": {"model": "Intel(R) Core(TM) i7-7700 CPU @ 3.60GHz"}},
        "graphics": {"devices": [
            {
                "active": False, "vendor_id": "8086", "device_id": "5912",
                "model": "Intel Corporation Kaby Lake-S GT2 [HD Graphics 630]",
            },
            {
                "active": True, "vendor_id": "10de", "device_id": "2507",
                "model": "NVIDIA Corporation GA106 [GeForce RTX 3050]",
            },
        ]},
        "display": {"active_output": {
            "current_mode": {"width": 3840, "height": 2160, "refresh_hz": 60.0}
        }},
    }
    (runtime / "capabilities.json").write_text(json.dumps(caps), encoding="utf-8")
    policy.write_preference(home, "presentation_mode", "CINEMA_AUTO")
    return temp, home


def test_rtx3050_4k_resolves_hq_krig_ssim_vibrance():
    temp, home = make_rtx3050_home()
    try:
        decision = policy.resolve(home, kind="dvd", gpu_binding={"mpv_args": []})
        assert decision["presentation"]["resolved"] == "RECIPE_MAG_SD_FSRCNN_HQ32_KRIG_SSIM_VIBRANCE_MILD"
        assert decision["presentation"]["profile_id"] == "nvidia_rtx3050_10de_2507_sd_2160p"
        shader_args = [arg for arg in decision["mpv_args"] if arg.startswith("--glsl-shaders=")]
        assert len(shader_args) == 1
        chain = shader_args[0]
        assert "FSRCNN_x2_r2_32-0-2.glsl" in chain
        assert "KrigBilateral.glsl" in chain
        assert "SSimSuperRes.glsl" in chain
        assert "OpenHTPC_Vibrance_Mild.glsl" in chain
        assert chain.index("FSRCNN_x2_r2_32-0-2.glsl") < chain.index("KrigBilateral.glsl")
        assert chain.index("KrigBilateral.glsl") < chain.index("SSimSuperRes.glsl")
        assert chain.index("SSimSuperRes.glsl") < chain.index("OpenHTPC_Vibrance_Mild.glsl")
        assert "--fbo-format=rgba16hf" in decision["mpv_args"]
        assert "--vf=bwdif_cuda=mode=send_frame:parity=auto:deint=interlaced" in decision["mpv_args"]
        assert "--scale=ewa_lanczossharp" in decision["mpv_args"]
        assert "--dscale=mitchell" in decision["mpv_args"]
        assert "--sigmoid-upscaling=yes" in decision["mpv_args"]
    finally:
        temp.cleanup()


def test_rtx3050_1080p_does_not_use_4k_profile():
    temp, home = make_rtx3050_home()
    try:
        caps_path = home / ".config/openhtpc/runtime/capabilities.json"
        caps = json.loads(caps_path.read_text(encoding="utf-8"))
        caps["display"]["active_output"]["current_mode"]["width"] = 1920
        caps["display"]["active_output"]["current_mode"]["height"] = 1080
        caps_path.write_text(json.dumps(caps), encoding="utf-8")
        decision = policy.resolve(home, kind="dvd", gpu_binding={"mpv_args": []})
        assert decision["presentation"]["resolved"] == "PURE"
    finally:
        temp.cleanup()


def make_hd630_home() -> tuple[tempfile.TemporaryDirectory, pathlib.Path]:
    temp = tempfile.TemporaryDirectory()
    home = pathlib.Path(temp.name)
    runtime = home / ".config/openhtpc/runtime"
    runtime.mkdir(parents=True)
    caps = {
        "hardware": {"cpu": {"model": "Intel(R) Core(TM) i7-7700 CPU @ 3.60GHz"}},
        "graphics": {"devices": [{
            "active": True, "vendor_id": "8086", "device_id": "5912",
            "model": "Intel Corporation Kaby Lake-S GT2 [HD Graphics 630]",
        }]},
        "display": {"active_output": {
            "current_mode": {"width": 1920, "height": 1080, "refresh_hz": 60.0}
        }},
    }
    (runtime / "capabilities.json").write_text(json.dumps(caps), encoding="utf-8")
    policy.write_preference(home, "presentation_mode", "CINEMA_AUTO")
    return temp, home


def test_hd630_1080p_resolves_fsrcnnx8_krig():
    temp, home = make_hd630_home()
    try:
        decision = policy.resolve(home, kind="dvd", gpu_binding={"mpv_args": []})
        assert decision["presentation"]["resolved"] == "RECIPE_MAG_SD_FSRCNNX8_KRIG"
        assert decision["presentation"]["profile_id"] == "intel_hd630_8086_5912_sd_1080p"
        shader_args = [arg for arg in decision["mpv_args"] if arg.startswith("--glsl-shaders=")]
        assert len(shader_args) == 1
        chain = shader_args[0]
        assert "FSRCNNX_x2_8-0-4-1.glsl" in chain
        assert "KrigBilateral.glsl" in chain
        assert chain.index("FSRCNNX_x2_8-0-4-1.glsl") < chain.index("KrigBilateral.glsl")
        assert "--vf=lavfi=[bwdif=mode=send_frame:parity=auto:deint=interlaced]" in decision["mpv_args"]
    finally:
        temp.cleanup()


def test_hd630_4k_has_no_1080p_profile():
    temp, home = make_hd630_home()
    try:
        caps_path = home / ".config/openhtpc/runtime/capabilities.json"
        caps = json.loads(caps_path.read_text(encoding="utf-8"))
        caps["display"]["active_output"]["current_mode"]["width"] = 3840
        caps["display"]["active_output"]["current_mode"]["height"] = 2160
        caps_path.write_text(json.dumps(caps), encoding="utf-8")
        decision = policy.resolve(home, kind="dvd", gpu_binding={"mpv_args": []})
        assert decision["presentation"]["resolved"] == "PURE"
    finally:
        temp.cleanup()


def make_amd_4k_home(device_id: str, model: str) -> tuple[tempfile.TemporaryDirectory, pathlib.Path]:
    temp = tempfile.TemporaryDirectory()
    home = pathlib.Path(temp.name)
    runtime = home / ".config/openhtpc/runtime"
    runtime.mkdir(parents=True)
    caps = {
        "hardware": {"cpu": {"model": "Intel(R) Core(TM) i7-7700 CPU @ 3.60GHz"}},
        "graphics": {"devices": [{
            "active": True, "vendor_id": "1002", "device_id": device_id,
            "model": model,
        }]},
        "display": {"active_output": {
            "current_mode": {"width": 3840, "height": 2160, "refresh_hz": 60.0}
        }},
    }
    (runtime / "capabilities.json").write_text(json.dumps(caps), encoding="utf-8")
    policy.write_preference(home, "presentation_mode", "CINEMA_AUTO")
    return temp, home


def test_rx580_4k_resolves_strong_chain():
    temp, home = make_amd_4k_home("67df", "AMD Radeon RX 580")
    try:
        decision = policy.resolve(home, kind="dvd", gpu_binding={"mpv_args": []})
        assert decision["presentation"]["resolved"] == "RECIPE_MAG_SD_FSRCNNX16_KRIG_SSIM_VIBRANCE_MILD"
        assert decision["presentation"]["profile_id"] == "amd_rx580_1002_67df_sd_2160p"
        shader_args = [arg for arg in decision["mpv_args"] if arg.startswith("--glsl-shaders=")]
        assert len(shader_args) == 1
        chain = shader_args[0]
        for shader in ("FSRCNNX_x2_16-0-4-1.glsl", "KrigBilateral.glsl", "SSimSuperRes.glsl", "OpenHTPC_Vibrance_Mild.glsl"):
            assert shader in chain
        assert "--vf=lavfi=[bwdif=mode=send_frame:parity=auto:deint=interlaced]" in decision["mpv_args"]
        assert "--fbo-format=rgba16hf" in decision["mpv_args"]
    finally:
        temp.cleanup()


def test_rx5700xt_4k_resolves_high_chain():
    temp, home = make_amd_4k_home("731f", "AMD Radeon RX 5700 XT")
    try:
        decision = policy.resolve(home, kind="dvd", gpu_binding={"mpv_args": []})
        assert decision["presentation"]["resolved"] == "RECIPE_MAG_SD_FSRCNN_HQ32_KRIG_SSIM_VIBRANCE_MILD"
        assert decision["presentation"]["profile_id"] == "amd_rx5700xt_1002_731f_sd_2160p"
        shader_args = [arg for arg in decision["mpv_args"] if arg.startswith("--glsl-shaders=")]
        assert len(shader_args) == 1
        chain = shader_args[0]
        for shader in ("FSRCNN_x2_r2_32-0-2.glsl", "KrigBilateral.glsl", "SSimSuperRes.glsl", "OpenHTPC_Vibrance_Mild.glsl"):
            assert shader in chain
        assert "--vf=lavfi=[bwdif=mode=send_frame:parity=auto:deint=interlaced]" in decision["mpv_args"]
        assert "--fbo-format=rgba16hf" in decision["mpv_args"]
    finally:
        temp.cleanup()


def test_missing_selected_shader_falls_back_to_pure(monkeypatch):
    temp, home = make_amd_4k_home("731f", "AMD Radeon RX 5700 XT")
    real_is_file = pathlib.Path.is_file

    def fake_is_file(path):
        if path.name == "SSimSuperRes.glsl":
            return False
        return real_is_file(path)

    monkeypatch.setattr(pathlib.Path, "is_file", fake_is_file)
    try:
        decision = policy.resolve(home, kind="dvd", gpu_binding={"mpv_args": []})
        assert decision["presentation"]["resolved"] == "PURE"
        assert decision["presentation"]["reason"] == "no_qualified_magnificence_profile"
        assert not any(arg.startswith("--glsl-shaders=") for arg in decision["mpv_args"])
    finally:
        temp.cleanup()


def test_qualified_amd_4k_profiles_do_not_apply_at_1080p():
    for device_id, model in (("67df", "AMD Radeon RX 580"), ("731f", "AMD Radeon RX 5700 XT")):
        temp, home = make_amd_4k_home(device_id, model)
        try:
            caps_path = home / ".config/openhtpc/runtime/capabilities.json"
            caps = json.loads(caps_path.read_text(encoding="utf-8"))
            caps["display"]["active_output"]["current_mode"]["width"] = 1920
            caps["display"]["active_output"]["current_mode"]["height"] = 1080
            caps_path.write_text(json.dumps(caps), encoding="utf-8")
            decision = policy.resolve(home, kind="dvd", gpu_binding={"mpv_args": []})
            assert decision["presentation"]["resolved"] == "PURE"
            assert decision["presentation"]["reason"] == "no_qualified_magnificence_profile"
        finally:
            temp.cleanup()


def test_community_gpu_tiers_are_reference_only_until_openhtpc_promotion():
    knowledge = json.loads((PAYLOAD / "assets/magnificence_gpu_knowledge.json").read_text(encoding="utf-8"))
    assert knowledge["policy"]["community_reference_rules_active"] is False
    community = [
        rule for rule in knowledge["family_rules"]
        if rule.get("confidence") == "COMMUNITY_DERIVED"
    ]
    assert community
    assert all(rule.get("selection_status") == "REFERENCE_ONLY" for rule in community)


def test_public_magnificence_ui_does_not_expose_internal_tiers_or_retired_calibration():
    ui_source = (PAYLOAD / "openhtpc-ui.py").read_text(encoding="utf-8")
    session_source = (PAYLOAD / "openhtpc-session-engine.py").read_text(encoding="utf-8")
    public_source = ui_source + session_source
    for stale in ("CONFIGURER MAGNIFICENCE", "RECALIBRER", "RÉESSAYER L'ANALYSE", "performance_map"):
        assert stale not in public_source
    processing = ui_source[ui_source.index('elif page == "processing":'):ui_source.index('elif page == "playback":')]
    for internal_tier in ("LIGHT", "MEDIUM", "STRONG", "HIGH"):
        assert internal_tier not in processing


def test_capabilities_summary_uses_current_magnificence_contract():
    source = (PAYLOAD / "openhtpc-capabilities.py").read_text(encoding="utf-8")
    assert '"MAGNIFICENCE"' in source
    assert "Benchmark runtime : non utilisé pour choisir la recette" in source
    summary_block = source[source.index("def summary("):source.index("def main()", source.index("def summary("))]
    assert "Profil adaptatif" not in summary_block
    assert "Benchmark :" not in summary_block
