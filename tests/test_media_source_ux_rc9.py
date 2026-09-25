from __future__ import annotations

import importlib.machinery
import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PAYLOAD = ROOT / "payload"


def load(name: str, filename: str):
    path = PAYLOAD / filename
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


picker = load("rc9_media_picker", "openhtpc-media-picker")
session = load("rc9_media_session", "openhtpc-session-engine.py")


def mountinfo(tmp_path: Path) -> Path:
    path = tmp_path / "mountinfo"
    path.write_text(
        "36 25 0:32 / /home/steve/MediaNAS rw,relatime - cifs //192.168.1.10/Media rw,vers=3.0\n"
        "37 25 0:33 / /mnt/archive rw,relatime - nfs4 nas:/archive rw\n"
        "38 25 8:1 / / rw,relatime - ext4 /dev/sda1 rw\n",
        encoding="utf-8",
    )
    return path


def test_picker_exposes_mounted_network_filesystems(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    media_nas = tmp_path / "MediaNAS"
    archive = tmp_path / "archive"
    media_nas.mkdir()
    archive.mkdir()

    info = tmp_path / "mountinfo"
    info.write_text(
        f"36 25 0:32 / {media_nas} rw,relatime - cifs //nas/Media rw\n"
        f"37 25 0:33 / {archive} rw,relatime - nfs4 nas:/archive rw\n",
        encoding="utf-8",
    )
    roots = picker.get_network_mount_roots(info)
    assert roots == [
        (f"NAS / RÉSEAU — {archive.name}", archive),
        (f"NAS / RÉSEAU — {media_nas.name}", media_nas),
    ]


def test_picker_network_root_wins_over_generic_movies_label(tmp_path):
    home = tmp_path / "home"
    movies = home / "Movies"
    movies.mkdir(parents=True)
    info = tmp_path / "mountinfo"
    info.write_text(
        f"36 25 0:32 / {movies} rw,relatime - cifs //nas/Movies rw\n",
        encoding="utf-8",
    )
    roots = picker.get_roots(home, info)
    matching = [(label, path) for label, path in roots if path.resolve() == movies.resolve()]
    assert matching == [("NAS / RÉSEAU — Movies", movies)]


def test_source_kind_uses_longest_mount_and_recognizes_network(tmp_path):
    root = tmp_path / "root"
    network = root / "network"
    movie = network / "Movies" / "Film.mkv"
    movie.parent.mkdir(parents=True)
    info = tmp_path / "mountinfo"
    info.write_text(
        f"1 0 8:1 / {root} rw - ext4 /dev/sda1 rw\n"
        f"2 1 0:54 / {network} rw - autofs systemd-1 rw\n"
        f"3 2 0:32 / {network} rw - cifs //nas/Media rw\n",
        encoding="utf-8",
    )
    assert session._source_filesystem_type(movie, info) == "cifs"


def test_available_source_has_kind_without_repeated_remove_context(tmp_path, monkeypatch):
    home = tmp_path / "home"
    source = home / "Movies"
    source.mkdir(parents=True)
    icon = tmp_path / "media.png"
    icon.write_bytes(b"x")
    monkeypatch.setattr(session, "_source_kind_label", lambda _path: "NAS / RÉSEAU")
    _root, content = session.media_menu_sections(home, [source], icon, "rc9-source-test")
    root_section = content.split("[MEDIA_ROOT]\n", 1)[1].split("\n\n", 1)[0]
    assert "Movies  ·  NAS / RÉSEAU" in root_section
    assert "RETIRER LA SOURCE" not in root_section
    assert "RETIRER CETTE SOURCE D'OPENHTPC" in content


def test_unavailable_source_remains_removable_from_root(tmp_path):
    home = tmp_path / "home"
    source = home / "MissingNAS"
    icon = tmp_path / "media.png"
    icon.write_bytes(b"x")
    _root, content = session.media_menu_sections(home, [source], icon, "rc9-missing-test")
    root_section = content.split("[MEDIA_ROOT]\n", 1)[1].split("\n\n", 1)[0]
    assert "MissingNAS  ·  INDISPONIBLE" in root_section
    assert "RETIRER LA SOURCE" in root_section
