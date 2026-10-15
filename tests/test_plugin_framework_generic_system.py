# Copyright 2026 Steve Dehanne
# SPDX-License-Identifier: Apache-2.0
#
# Part of the OPENHTPC project.
# Original project by Steve Dehanne.
"""Hermetic coverage for the generic plugin inventory in System."""
from __future__ import annotations

import importlib.util
import importlib.machinery
import hashlib
import json
import pathlib
import shutil
import tempfile
import unittest
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[1]
PAYLOAD = ROOT / "payload"


def load(name: str, path: pathlib.Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


REGISTRY = load("generic_system_registry", PAYLOAD / "openhtpc-plugin-registry.py")
CORE = load("generic_system_core", PAYLOAD / "openhtpc-core.py")
MODEL = load("generic_system_model", PAYLOAD / "openhtpc-system-model.py")
UI = load("generic_system_ui", PAYLOAD / "openhtpc-ui.py")
ENGINE = load("generic_system_engine", PAYLOAD / "openhtpc-session-engine.py")


class GenericPluginSystemInventory(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        root = pathlib.Path(self.temporary.name)
        self.home = root / "home"
        self.install = root / "install"
        self.install.mkdir()
        (self.install / "VERSION").write_text("1.3.1\n", encoding="utf-8")
        shutil.copy2(PAYLOAD / "openhtpc-plugin-registry.py", self.install / "openhtpc-plugin-registry.py")
        shutil.copytree(
            PAYLOAD / "plugins/available/plugin.bluray",
            self.install / "plugins/available/plugin.bluray",
        )
        self.facts = {
            "schema": "openhtpc-plugin-dependency-facts-v1",
            "capabilities": {
                "protected-optical-state": {"status": "AVAILABLE", "source": "test"},
                "sample-ready": {"status": "AVAILABLE", "source": "test"},
            },
            "system": {"sample-runtime": {"status": "AVAILABLE", "source": "test"}},
        }
        self.write_facts(self.facts)

    def write_facts(self, facts):
        target = self.home / ".config/openhtpc/runtime/capabilities.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps({"plugin_dependency_facts": facts}), encoding="utf-8")

    def registry(self):
        return CORE.plugin_status(self.home, self.install)

    def inventory(self):
        return MODEL._plugin_inventory(self.registry())

    def add_minimal_user_plugin(
        self,
        plugin_id="plugin.sample",
        *,
        plugin_dependencies=None,
        capability_dependencies=None,
        system_dependencies=None,
    ):
        target = self.home / f".local/share/openhtpc/plugins/available/{plugin_id}"
        target.mkdir(parents=True)
        manifest = {
            "schema": "openhtpc-plugin-v2",
            "id": plugin_id,
            "name": plugin_id.removeprefix("plugin.").replace("-", " ").title(),
            "version": "0.1.0",
            "plugin_api": 2,
            "openhtpc": {"minimum": "1.3.1", "maximum": None},
            "category": "media",
            "entrypoint": None,
            "capabilities": ["doctor"],
            "dependencies": {
                "plugins": plugin_dependencies or [],
                "capabilities": ["sample-ready"] if capability_dependencies is None else capability_dependencies,
            },
            "system_dependencies": ["sample-runtime"] if system_dependencies is None else system_dependencies,
            "enabled_by_default": False,
            "doctor": {"label": "Sample Plugin", "capability": "sample-ready"},
            "resources": {},
        }
        (target / "plugin.json").write_text(json.dumps(manifest), encoding="utf-8")
        return target

    def enable(self, plugin_id):
        REGISTRY.set_enabled(self.home, self.install, plugin_id, True, self.facts)

    def test_real_registry_drives_disabled_then_available_inventory(self):
        disabled = self.inventory()
        self.assertEqual(disabled["registry"], "Disponible")
        self.assertEqual(disabled["provided"], 1)
        self.assertEqual(disabled["local"], 0)
        self.assertEqual(disabled["disabled"], 1)
        self.assertEqual(disabled["entries"][0]["id"], "plugin.bluray")
        self.assertEqual(disabled["entries"][0]["state_label"], "Désactivé")
        self.assertEqual(disabled["entries"][0]["provenance_label"], "Fournie par OPENHTPC")
        self.assertEqual(disabled["entries"][0]["activation_label"], "Détection automatique")
        self.assertEqual(disabled["entries"][0]["external_prerequisite"], "DETECTED")
        self.assertEqual(disabled["entries"][0]["readiness_label"], "Prêt à tenter la lecture")

        self.enable("plugin.bluray")
        available = self.inventory()
        self.assertEqual(available["available"], 1)
        self.assertEqual(available["disabled"], 0)
        self.assertEqual(available["entries"][0]["state_label"], "Disponible")
        self.assertEqual(available["entries"][0]["activation_label"], "Détection automatique")

    def test_invalid_user_plugin_is_isolated_and_visible(self):
        target = self.home / ".local/share/openhtpc/plugins/available/plugin.invalid"
        target.mkdir(parents=True)
        (target / "plugin.json").write_text(json.dumps({"schema": "wrong"}), encoding="utf-8")
        inventory = self.inventory()
        invalid = next(entry for entry in inventory["entries"] if entry["id"] == "plugin.invalid")
        self.assertEqual(invalid["state"], "BROKEN")
        self.assertEqual(invalid["diagnostic"], "PLUGIN_SCHEMA_INVALID")
        self.assertEqual(inventory["broken"], 1)

    def test_minimal_user_plugin_can_be_detected_enabled_and_displayed(self):
        self.add_minimal_user_plugin()
        before = self.inventory()
        sample = next(entry for entry in before["entries"] if entry["id"] == "plugin.sample")
        self.assertEqual(sample["state"], "DISABLED")
        self.assertEqual(sample["origin"], "Utilisateur")
        self.assertEqual(sample["provenance_label"], "Ajoutée localement")
        self.assertIn("système:sample-runtime", sample["dependencies"])

        self.enable("plugin.sample")
        after = self.inventory()
        sample = next(entry for entry in after["entries"] if entry["id"] == "plugin.sample")
        self.assertEqual(sample["state"], "AVAILABLE")
        self.assertEqual(sample["state_label"], "Disponible")

    def test_inventory_does_not_execute_plugin_entrypoint(self):
        target = self.add_minimal_user_plugin()
        manifest = json.loads((target / "plugin.json").read_text(encoding="utf-8"))
        manifest["entrypoint"] = "entry.py"
        (target / "plugin.json").write_text(json.dumps(manifest), encoding="utf-8")
        marker = self.home / "entrypoint-executed"
        (target / "entry.py").write_text(f"open({str(marker)!r}, 'w').write('bad')\n", encoding="utf-8")
        inventory = self.inventory()
        self.assertTrue(any(entry["id"] == "plugin.sample" for entry in inventory["entries"]))
        self.assertFalse(marker.exists())

    def test_satisfied_missing_and_unknown_facts_are_distinct(self):
        self.add_minimal_user_plugin()
        self.enable("plugin.sample")
        satisfied = next(entry for entry in self.inventory()["entries"] if entry["id"] == "plugin.sample")
        self.assertEqual((satisfied["state"], satisfied["dependency_status"], satisfied["diagnostic"]), ("AVAILABLE", "SATISFIED", "PASS"))

        missing = json.loads(json.dumps(self.facts))
        missing["system"]["sample-runtime"]["status"] = "NOT_AVAILABLE"
        self.write_facts(missing)
        missing_entry = next(entry for entry in self.inventory()["entries"] if entry["id"] == "plugin.sample")
        self.assertEqual((missing_entry["state"], missing_entry["diagnostic"]), ("DEPENDENCY_MISSING", "SYSTEM_DEPENDENCY_MISSING"))

        unknown = json.loads(json.dumps(self.facts))
        unknown["capabilities"].pop("sample-ready")
        self.write_facts(unknown)
        unknown_entry = next(entry for entry in self.inventory()["entries"] if entry["id"] == "plugin.sample")
        self.assertEqual((unknown_entry["state"], unknown_entry["diagnostic"]), ("DEPENDENCY_UNKNOWN", "CAPABILITY_DEPENDENCY_UNKNOWN"))

    def test_unknown_plugin_reference_is_missing(self):
        self.add_minimal_user_plugin(
            plugin_dependencies=["plugin.absent"],
            capability_dependencies=[],
            system_dependencies=[],
        )
        self.enable("plugin.sample")
        item = next(entry for entry in self.registry()["plugins"] if entry["id"] == "plugin.sample")
        self.assertEqual((item["state"], item["dependency_resolution"]["reason"]), ("DEPENDENCY_MISSING", "PLUGIN_DEPENDENCY_NOT_INSTALLED"))

    def test_invalid_dependency_target_is_isolated_and_invalid(self):
        invalid = self.home / ".local/share/openhtpc/plugins/available/plugin.invalid"
        invalid.mkdir(parents=True)
        (invalid / "plugin.json").write_text(json.dumps({"schema": "wrong"}), encoding="utf-8")
        self.add_minimal_user_plugin(
            plugin_dependencies=["plugin.invalid"],
            capability_dependencies=[],
            system_dependencies=[],
        )
        self.enable("plugin.sample")
        registry = self.registry()
        sample = next(item for item in registry["plugins"] if item["id"] == "plugin.sample")
        self.assertEqual((sample["state"], sample["dependency_resolution"]["reason"]), ("DEPENDENCY_INVALID", "PLUGIN_DEPENDENCY_INVALID"))
        self.assertEqual(next(item for item in registry["errors"] if item["id"] == "plugin.invalid")["reason"], "PLUGIN_SCHEMA_INVALID")

    def test_plugin_dependency_cycle_fails_closed(self):
        self.add_minimal_user_plugin("plugin.alpha", plugin_dependencies=["plugin.beta"], capability_dependencies=[], system_dependencies=[])
        self.add_minimal_user_plugin("plugin.beta", plugin_dependencies=["plugin.alpha"], capability_dependencies=[], system_dependencies=[])
        self.enable("plugin.alpha")
        self.enable("plugin.beta")
        plugins = {item["id"]: item for item in self.registry()["plugins"]}
        self.assertEqual(plugins["plugin.alpha"]["state"], "DEPENDENCY_CYCLE")
        self.assertEqual(plugins["plugin.beta"]["dependency_resolution"]["reason"], "PLUGIN_DEPENDENCY_CYCLE")

    def test_malformed_fact_schema_fails_closed(self):
        self.enable("plugin.bluray")
        self.write_facts({"schema": 1, "capabilities": [], "system": {}})
        item = next(entry for entry in self.registry()["plugins"] if entry["id"] == "plugin.bluray")
        self.assertEqual((item["state"], item["dependency_resolution"]["reason"]), ("DEPENDENCY_INVALID", "DEPENDENCY_FACTS_SCHEMA_INVALID"))

    def test_unhashable_fact_status_fails_closed(self):
        self.enable("plugin.bluray")
        malformed = json.loads(json.dumps(self.facts))
        malformed["capabilities"]["protected-optical-state"]["status"] = []
        self.write_facts(malformed)
        item = next(entry for entry in self.registry()["plugins"] if entry["id"] == "plugin.bluray")
        self.assertEqual((item["state"], item["dependency_resolution"]["reason"]), ("DEPENDENCY_INVALID", "DEPENDENCY_FACT_INVALID"))

    def test_pathological_dependency_graph_fails_closed(self):
        self.enable("plugin.bluray")
        with mock.patch.object(REGISTRY, "resolve_dependencies", side_effect=RecursionError):
            item = REGISTRY.registry(self.home, self.install, self.facts)["plugins"][0]
        self.assertEqual((item["state"], item["dependency_resolution"]["reason"]), ("DEPENDENCY_INVALID", "PLUGIN_DEPENDENCY_GRAPH_INVALID"))

    def test_core_adapter_preserves_unknown_and_unavailable_truth(self):
        target = self.home / ".config/openhtpc/runtime/capabilities.json"
        for source_status, fact_status in (
            ("AVAILABLE", "AVAILABLE"),
            ("DETECTED", "AVAILABLE"),
            ("UNKNOWN", "UNKNOWN"),
            ("BLOCKED", "UNKNOWN"),
            ("UNAVAILABLE", "NOT_AVAILABLE"),
            ("NOT_AVAILABLE", "NOT_AVAILABLE"),
            ("NOT_CONFIGURED", "NOT_AVAILABLE"),
        ):
            target.write_text(json.dumps({"optical": {"protected_media": {"status": source_status}}}), encoding="utf-8")
            fact = CORE.plugin_dependency_facts(self.home)["capabilities"]["protected-optical-state"]
            self.assertEqual(fact["status"], fact_status)

    def test_advanced_optical_support_reports_external_prerequisite_without_install_claim(self):
        missing = json.loads(json.dumps(self.facts))
        missing["capabilities"]["protected-optical-state"]["status"] = "NOT_AVAILABLE"
        self.write_facts(missing)
        entry = next(item for item in self.inventory()["entries"] if item["id"] == "plugin.bluray")
        self.assertEqual(entry["name"], "Support optique avancé")
        self.assertEqual(entry["external_prerequisite"], "ABSENT")
        self.assertEqual(entry["prerequisite_label"], "Prérequis externe absent")
        self.assertEqual(entry["readiness_label"], "Non disponible")

        self.write_facts(self.facts)
        entry = next(item for item in self.inventory()["entries"] if item["id"] == "plugin.bluray")
        self.assertEqual(entry["external_prerequisite"], "DETECTED")
        self.assertEqual(entry["prerequisite_label"], "Prérequis externe détecté")
        self.assertEqual(entry["readiness_label"], "Prêt à tenter la lecture")

    def test_extensions_presentation_contains_no_external_acquisition_mechanism(self):
        source = (PAYLOAD / "openhtpc-ui.py").read_text(encoding="utf-8")
        extensions_source = source.split('elif page == "extensions":', 1)[1].split('elif page == "processing":', 1)[0]
        manifest = (PAYLOAD / "plugins/available/plugin.bluray/plugin.json").read_text(encoding="utf-8")
        self.assertNotIn("installée(s)", extensions_source)
        self.assertNotIn("EXTENSIONS DÉTECTÉES", extensions_source)
        self.assertNotIn("Blu-ray UHD", manifest)
        for marker in ("KEYDB", "http://", "https://", "curl ", "wget "):
            self.assertNotIn(marker, extensions_source)

    def test_doctor_and_extensions_share_state_and_reason(self):
        self.enable("plugin.bluray")
        facts = json.loads(json.dumps(self.facts))
        facts["capabilities"]["protected-optical-state"]["status"] = "NOT_AVAILABLE"
        self.write_facts(facts)
        registry = self.registry()
        doctor = next(item for item in CORE.optional_plugin_states(registry) if item["label"] == "Support optique avancé")
        extension = next(item for item in MODEL._plugin_inventory(registry)["entries"] if item["id"] == "plugin.bluray")
        self.assertEqual((doctor["status"], doctor["reason"]), (extension["state"], extension["diagnostic"]))

    def test_extensions_projection_performs_no_discovery_or_collection(self):
        registry = self.registry()
        with mock.patch.object(MODEL.importlib.util, "spec_from_file_location", side_effect=AssertionError("implicit load")):
            inventory = MODEL._plugin_inventory(registry)
        self.assertEqual(inventory["registry"], "Disponible")

    def test_missing_registry_is_nonblocking(self):
        (self.install / "openhtpc-plugin-registry.py").unlink()
        inventory = self.inventory()
        self.assertEqual(inventory["registry"], "Indisponible")
        self.assertEqual(inventory["entries"], [])

    def test_duplicate_plugin_is_listed_once_with_its_diagnostic(self):
        shutil.copytree(
            self.install / "plugins/available/plugin.bluray",
            self.home / ".local/share/openhtpc/plugins/available/plugin.bluray",
        )
        inventory = self.inventory()
        bluray = [entry for entry in inventory["entries"] if entry["id"] == "plugin.bluray"]
        self.assertEqual(len(bluray), 1)
        self.assertEqual(bluray[0]["state"], "BROKEN")
        self.assertEqual(bluray[0]["diagnostic"], "PLUGIN_DUPLICATE")

    def test_extensions_page_is_a_canonical_system_page(self):
        self.assertIn("extensions", UI.SYSTEM_PAGES)
        self.assertIn("extensions", ENGINE.SYSTEM_PAGE_KEYS)
        model = {
            "available": True,
            "product": {"overall": "READY", "health": "PRÊT", "version": "1.3.1"},
            "extensions": self.inventory(),
        }
        target = self.home / "extensions.png"
        target.parent.mkdir(parents=True, exist_ok=True)
        UI.system_page_png(model, target, PAYLOAD / "flex/assets/fonts/OpenSans-Regular.ttf", "extensions")
        self.assertTrue(target.is_file())
        self.assertGreater(target.stat().st_size, 500)

    def test_system_root_keeps_all_categories_on_one_compact_page(self):
        engine = (PAYLOAD / "openhtpc-session-engine.py").read_text(encoding="utf-8")
        launcher = (ROOT / "vendor/flex-launcher/src/launcher.c").read_text(encoding="utf-8")
        system_section = engine.split("[SYSTEME]", 1)[1].split("[SYSTEM_OVERVIEW]", 1)[0]
        entries = [line for line in system_section.splitlines() if line.startswith("Entry")]
        self.assertEqual(len(entries), 11)
        self.assertIn("Entry2=VIDÉO;", system_section)
        self.assertIn("Entry6=MÉDIAS & DISQUES;", system_section)
        self.assertIn("Entry8=EXTENSIONS;", system_section)
        self.assertIn("Entry11=RETOUR;", system_section)
        self.assertIn('strcmp(menu->name, "SYSTEME") == 0', launcher)
        self.assertIn("return menu->num_entries;", launcher)
        self.assertIn("int row_height = (geo.screen_height * 64) / 1000;", launcher)
        self.assertIn("int text_height = (geo.screen_height * 32) / 1000;", launcher)

    def test_distributed_flex_matches_compact_system_source(self):
        metadata = json.loads((PAYLOAD / "flex/BUILD-METADATA.json").read_text(encoding="utf-8"))
        binary = PAYLOAD / "flex/bin/flex-launcher"
        self.assertEqual(hashlib.sha256(binary.read_bytes()).hexdigest(), metadata["binary_sha256"])
        loader = importlib.machinery.SourceFileLoader("generic_system_devctl", str(ROOT / "tools/openhtpc-devctl"))
        spec = importlib.util.spec_from_loader("generic_system_devctl", loader)
        devctl = importlib.util.module_from_spec(spec)
        loader.exec_module(devctl)
        self.assertEqual(devctl._source_fingerprint(ROOT / "vendor/flex-launcher"), metadata["flex_source_fingerprint"])


if __name__ == "__main__":
    unittest.main()
