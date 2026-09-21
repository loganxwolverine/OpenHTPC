# Copyright 2026 Steve Dehanne
# SPDX-License-Identifier: Apache-2.0
#
# Part of the OPENHTPC project.
# Original project by Steve Dehanne.
"""Hermetic checks for the synchronous media library update command."""

from __future__ import annotations

import importlib.machinery
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest


COMMAND = Path(__file__).resolve().parents[1] / "payload/openhtpc-media-library-update"
loader = importlib.machinery.SourceFileLoader("media_library_update_test", str(COMMAND))
spec = importlib.util.spec_from_loader(loader.name, loader)
library_update = importlib.util.module_from_spec(spec)
loader.exec_module(library_update)


def _environment(tmp_path, monkeypatch, *, scan_results=None, enrich_results=None):
    home = tmp_path / "home"
    first = tmp_path / "a-movies"
    second = tmp_path / "b-movies"
    first.mkdir()
    second.mkdir()
    config = home / ".config/openhtpc/user-config.json"
    config.parent.mkdir(parents=True)
    config.write_text(json.dumps({"local_media_sources": [str(second), str(first)]}))
    events = []
    scan_results = scan_results or {}
    enrich_results = enrich_results or {}

    def configured_sources(given_home):
        assert given_home == home
        return [
            {"canonical_path": path, "source_id": path.name, "configured_path": str(path), "exists": True}
            for path in (second, first)
        ]

    def scan_source(*, source_id, db_path, home):
        events.append(("scan", source_id, db_path, home))
        return scan_results.get(source_id, {
            "ok": True, "outcome": "COMPLETE", "enumerated": 2,
            "new": 1, "unchanged": 1, "changed": 0, "restored": 0,
            "missing": 0, "failed": 0,
        })

    def run_batch_enrichment(*, source_id, home, db_path):
        events.append(("enrich", source_id, db_path, home))
        return enrich_results.get(source_id, {
            "ok": True, "outcome": "COMPLETE", "auto_matched": 1,
            "unresolved": 0, "presentation_refreshed": 1,
            "posters_cache_hit": 1, "posters_cached": 0,
            "provider_failed": 0, "presentation_failed": 0, "poster_failed": 0,
        })

    def publish(path, given_home, sources, install):
        events.append(("publish", path, given_home, sources, install))
        return True

    components = {
        "openhtpc-media-scan.py": SimpleNamespace(
            get_configured_sources=configured_sources,
            detect_overlapping_sources=lambda sources: [],
            scan_source=scan_source,
        ),
        "openhtpc-media-enrich.py": SimpleNamespace(run_batch_enrichment=run_batch_enrichment),
        "openhtpc-session-engine.py": SimpleNamespace(
            canonical_flex_config_path=lambda given_home: given_home / ".config/openhtpc/flex-v1.ini",
            publish_flex_config=publish,
        ),
    }
    monkeypatch.setattr(library_update, "_load_component", components.__getitem__)
    return home, first, second, events


def test_all_sources_scan_then_enrich_and_publish_once(tmp_path, monkeypatch):
    home, first, second, events = _environment(tmp_path, monkeypatch)
    db = tmp_path / "media.db"
    install = tmp_path / "install"
    result = library_update.update_library(home, db, install)

    assert result["ok"] is True
    assert [(event[0], event[1]) for event in events[:-1]] == [
        ("scan", first.name), ("enrich", first.name),
        ("scan", second.name), ("enrich", second.name),
    ]
    assert events[-1] == (
        "publish", home / ".config/openhtpc/flex-v1.ini", home, [first, second], install,
    )
    assert len([event for event in events if event[0] == "publish"]) == 1
    assert all(event[2:] == (db, home) for event in events[:-1])
    assert result["sources_processed"] == 2
    assert result["files_discovered"] == 4
    assert result["new"] == 2 and result["unchanged"] == 2
    assert result["auto_matched"] == 2 and result["enriched"] == 2
    assert result["poster_cache_hits"] == 2


def test_source_failure_is_reported_and_other_source_continues(tmp_path, monkeypatch):
    failed = {"ok": False, "outcome": "SOURCE_UNAVAILABLE", "error": "SOURCE_UNAVAILABLE"}
    home, first, second, events = _environment(
        tmp_path, monkeypatch, scan_results={"a-movies": failed},
    )
    result = library_update.update_library(home)

    assert result["ok"] is False
    assert result["failures"] == 1
    assert result["source_failures"] == [{
        "source_id": first.name, "path": str(first), "stage": "scan",
        "error": "SOURCE_UNAVAILABLE",
    }]
    assert [event[0:2] for event in events[:-1]] == [
        ("scan", first.name), ("scan", second.name), ("enrich", second.name),
    ]
    assert events[-1][0] == "publish"


def test_item_failure_preserves_batch_continuation_and_nonzero_result(tmp_path, monkeypatch, capsys):
    partial = {
        "ok": True, "outcome": "PARTIAL", "enumerated": 2, "new": 1,
        "unchanged": 0, "changed": 0, "restored": 0, "missing": 0, "failed": 1,
    }
    home, first, second, events = _environment(
        tmp_path, monkeypatch, scan_results={"a-movies": partial},
    )
    assert library_update.main(["--home", str(home)]) == 1
    summary = json.loads(capsys.readouterr().out)
    assert summary["sources_processed"] == 2
    assert summary["failures"] == 1
    assert summary["source_failures"][0]["error"] == "PARTIAL"
    assert [(event[0], event[1]) for event in events[:-1]] == [
        ("scan", first.name), ("enrich", first.name),
        ("scan", second.name), ("enrich", second.name),
    ]
    assert events[-1][0] == "publish"


def test_publish_failure_reports_incomplete_update(tmp_path, monkeypatch):
    home, _first, _second, events = _environment(tmp_path, monkeypatch)
    session = library_update._load_component("openhtpc-session-engine.py")
    session.publish_flex_config = lambda *args: events.append(("publish_failed",)) or False

    result = library_update.update_library(home)
    assert result["ok"] is False
    assert result["flex_published"] is False
    assert result["source_failures"] == [{
        "stage": "publish", "error": "FLEX_PUBLICATION_FAILED",
    }]
    assert [event[0] for event in events].count("publish_failed") == 1


@pytest.mark.parametrize("sources", [["relative/path"], [42], "bad"])
def test_invalid_config_fails_before_processing(tmp_path, monkeypatch, sources):
    home, _first, _second, events = _environment(tmp_path, monkeypatch)
    config = home / ".config/openhtpc/user-config.json"
    config.write_text(json.dumps({"local_media_sources": sources}))
    result = library_update.update_library(home)
    assert result["ok"] is False
    assert result["source_failures"][0]["stage"] == "configuration"
    assert events == []
