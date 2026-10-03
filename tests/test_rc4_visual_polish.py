from __future__ import annotations

import importlib.machinery
import importlib.util
import pathlib
import tempfile

from PIL import Image

ROOT = pathlib.Path(__file__).resolve().parents[1]
PAYLOAD = ROOT / "payload"


def load(name: str, path: pathlib.Path):
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


session = load("rc4_visual_session", PAYLOAD / "openhtpc-session-engine.py")


def test_movie_detail_bokeh_is_local_bounded_and_section_scoped():
    with tempfile.TemporaryDirectory() as value:
        home = pathlib.Path(value)
        poster = home / "poster.jpg"
        Image.new("RGB", (500, 750), (180, 50, 30)).save(poster)
        background = session._movie_bokeh_background(home, "MEDIA_D12345678", poster)
        assert background is not None and background.is_file()
        assert background.name.endswith("-b44-a105.jpg")
        with Image.open(background) as image:
            assert image.size == (1920, 1080)
        section = session._build_movie_detail_section(
            section_id="MEDIA_D12345678", token="token", stem="Film", ext=".mkv",
            ident={"work_id": 1, "identification_state": "USER_MATCHED"},
            pres_info={"display_title": "Film"}, item_icon=poster,
            entry_icon=poster, res_menu="MEDIA_R12345678", background_image=background,
        )
        assert f"BackgroundImage={background}" in section


def test_media_root_uses_distinct_semantic_icons():
    source = (PAYLOAD / "openhtpc-session-engine.py").read_text(encoding="utf-8")
    assert 'update_icon = media_ui / "system-processing.png"' in source
    assert 'library_icon = media_ui / "media.png"' in source
    assert 'add_icon = media_ui / "folder.png"' in source
    assert 'review_icon = media_ui / "diagnostic.png"' in source
    assert 'back_icon = media_ui / "system-back.png"' in source
    assert 'roots = [(update_label, update_icon' in source
    assert 'review_icon, ":submenu MEDIA_UNMATCHED"' in source
    assert '("RETOUR À OPENHTPC", back_icon, ":back")' in source


def test_movie_detail_bokeh_recipe_is_exact_and_generalized():
    source = (PAYLOAD / "openhtpc-session-engine.py").read_text(encoding="utf-8")
    assert "GaussianBlur(radius=44)" in source
    assert 'Image.new("RGBA", base.size, (0, 0, 0, 105))' in source
    assert 'centering=(0.5, 0.5)' in source
    assert 'detail_background = _movie_bokeh_background(home, detail_menu, item_icon) if work_id is not None else None' not in source
    assert 'unmatched_background = _movie_bokeh_background' in source
    assert source.count('technical_info=technical_map.get((source_id, relative.as_posix()))') >= 2


def test_home_menu_recognizes_canonical_openhtpc_section():
    source = (ROOT / "vendor/flex-launcher/src/launcher.c").read_text(encoding="utf-8")
    assert 'strcmp(current_menu->name, "OPENHTPC") == 0' in source
    assert 'strcmp(current_menu->name, "Accueil") == 0' in source


def test_home_icon_uses_true_drop_shadow_without_cards_or_coloured_halo():
    source = (ROOT / "vendor/flex-launcher/src/launcher.c").read_text(encoding="utf-8")
    assert "icon != NULL && is_home_menu()" in source
    assert "Plaques de contraste propres à l'accueil" not in source
    assert "SDL_SetTextureAlphaMod(icon, 22)" in source
    assert "SDL_SetTextureColorMod(icon, 40, 190, 255)" not in source
    assert "SDL_SetTextureColorMod(icon, old_r, old_g, old_b)" in source
    assert "SDL_SetTextureAlphaMod(icon, old_a)" in source


def test_home_selection_uses_thin_cyan_underline_without_cards():
    source = (ROOT / "vendor/flex-launcher/src/launcher.c").read_text(encoding="utf-8")
    assert "Minimal home selection marker: a thin cyan underline only." in source
    assert "entry == current_entry" in source
    assert "SDL_Color){34, 199, 255, 185}" in source
    assert "Plaques de contraste propres à l'accueil" not in source


def test_public_system_ui_has_no_obsolete_benchmark_or_duplicate_playback_entries():
    ui = (PAYLOAD / "openhtpc-ui.py").read_text(encoding="utf-8")
    engine = (PAYLOAD / "openhtpc-session-engine.py").read_text(encoding="utf-8")
    assert "Benchmark de rendu" not in ui
    assert "Recommandation" not in ui
    assert "Réglages mémorisés" in ui
    assert "Informations système" in ui
    start = engine.index("def _playback_policy_sections")
    end = engine.index("\ndef ", start + 10)
    playback_section = engine[start:end]
    assert "ÉTAT AUDIO" not in playback_section
    assert "À PROPOS" not in playback_section
    assert "TRAITEMENT VIDÉO" in playback_section


def test_optical_movie_sheet_uses_same_validated_bokeh_recipe():
    source = (PAYLOAD / "openhtpc-disc-view.py").read_text(encoding="utf-8")
    assert "GaussianBlur(radius=44)" in source
    assert 'Image.new("RGBA",image.size,(0,0,0,105))' in source
    assert 'centering=(.5,.5)' in source
    assert "base=bokeh_background(poster_path,wallpaper,allowed_artwork)" in source
