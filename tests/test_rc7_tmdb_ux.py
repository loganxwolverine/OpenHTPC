# Copyright 2026 Steve Dehanne
# SPDX-License-Identifier: Apache-2.0
# Part of the OPENHTPC project. Original project by Steve Dehanne.
from __future__ import annotations

import importlib.util
import io
import json
import os
import pathlib
import tempfile
import unittest
import urllib.error
import urllib.parse
import urllib.request
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
PAYLOAD = ROOT / "payload"


def load_module(name: str, path: pathlib.Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


tmdb_mgmt = load_module("rc7_tmdb_mgmt", PAYLOAD / "openhtpc-tmdb-management.py")
tmdb_core = load_module("rc7_tmdb_core", PAYLOAD / "openhtpc-tmdb.py")
initial_setup = load_module("rc7_initial_setup", PAYLOAD / "openhtpc-initial-setup.py")
ui_module = load_module("rc7_ui", PAYLOAD / "openhtpc-ui.py")


class ResponseMock(io.BytesIO):
    def __init__(self, data=b'{"success":true}'):
        super().__init__(data)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


class Rc7TmdbUxTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = pathlib.Path(self.tmp.name)
        self.secrets_dir = self.home / ".config/openhtpc/secrets"
        self.token_file = self.secrets_dir / "tmdb-token"
        self.validation_file = self.home / ".config/openhtpc/tmdb-validation.json"
        self.config_file = self.home / ".config/openhtpc/user-config.json"

    def _seed_rc6_token(self, token_value: str = "32charv3apikey00000000000000000"):
        self.secrets_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.token_file.write_text(token_value.strip() + "\n", encoding="utf-8")
        self.token_file.chmod(0o600)
        self.config_file.parent.mkdir(parents=True, exist_ok=True)
        self.config_file.write_text(
            json.dumps({"schema": 1, "configuration_completed": True, "local_media_sources": [], "tmdb": {"configured": True}}),
            encoding="utf-8",
        )

    # 1. Nouveaux libellés exacts
    def test_01_exact_labels_in_tmdb_management_status(self):
        # Unconfigured state
        unconf_status = tmdb_mgmt.status(self.home)
        self.assertEqual(unconf_status["detail"], "Aucun accès API TMDb enregistré")
        self.assertEqual(unconf_status["state"], "NOT_CONFIGURED")

        # Configured but untested state
        self._seed_rc6_token("32charv3apikey00000000000000000")
        untested_status = tmdb_mgmt.status(self.home)
        self.assertEqual(untested_status["detail"], "Accès API TMDb enregistré, non testé")

    def test_02_exact_labels_in_tmdb_management_interactive_dialogs(self):
        # Input prompt in configure/modify
        dialog_calls = []

        def fake_dialog(args, capture=False):
            dialog_calls.append((args, capture))
            return mock.Mock(returncode=1, stdout="")

        with mock.patch.object(tmdb_mgmt, "_dialog", side_effect=fake_dialog):
            tmdb_mgmt.interactive(self.home, "configure")
            tmdb_mgmt.interactive(self.home, "modify")

        self.assertEqual(len(dialog_calls), 2)
        for args, capture in dialog_calls:
            self.assertIn("--password", args)
            self.assertIn("Clé API v3 ou jeton d'accès v4 TMDb :", args)

        # Deletion confirmation prompt
        delete_calls = []

        def fake_delete_dialog(args, capture=False):
            delete_calls.append(args)
            return mock.Mock(returncode=1, stdout="")

        self._seed_rc6_token()
        with mock.patch.object(tmdb_mgmt, "_dialog", side_effect=fake_delete_dialog):
            tmdb_mgmt.interactive(self.home, "delete")

        self.assertTrue(any("Supprimer l'accès API TMDb enregistré ?" in args for args in delete_calls))

    def test_03_exact_labels_in_initial_setup_prompts(self):
        source = (PAYLOAD / "openhtpc-initial-setup.py").read_text(encoding="utf-8")
        self.assertIn('"Clé API v3 ou jeton d\'accès v4 TMDb (facultatif) :"', source)
        self.assertIn('"Clé API v3 ou jeton d\'accès v4 TMDb (facultatif) : "', source)

    def test_04_exact_labels_in_system_ui_page(self):
        source = (PAYLOAD / "openhtpc-ui.py").read_text(encoding="utf-8")
        self.assertIn('("Accès API TMDb", tmdb["masked"], None)', source)
        self.assertIn('tmdb.get("detail", "Accès API TMDb enregistré, non testé")', source)

    def test_05_exact_label_for_rejected_credential(self):
        def rejected_opener(*a, **k):
            raise urllib.error.HTTPError("https://api.themoviedb.org/3/authentication", 401, "Unauthorized", {}, None)

        result = tmdb_mgmt.validate("invalid_key", opener=rejected_opener)
        self.assertEqual(result["state"], "AUTH_REJECTED")
        self.assertEqual(result["detail"], "Clé ou jeton API refusé par TMDb")

    # 2. Absence des anciens libellés ambigus
    def test_06_absence_of_ambiguous_legacy_labels(self):
        for script_name in ("openhtpc-tmdb-management.py", "openhtpc-initial-setup.py"):
            content = (PAYLOAD / script_name).read_text(encoding="utf-8")
            self.assertNotIn("Identifiant TMDb", content)
            self.assertNotIn("Clé TMDb privée (facultative) :", content)
            self.assertNotIn("Clé TMDb facultative (vide = plus tard) :", content)
            self.assertNotIn("Aucun identifiant TMDb enregistré", content)
            self.assertNotIn("Identifiant enregistré, non testé", content)
            self.assertNotIn("Identifiant refusé par TMDb", content)
            self.assertNotIn("Supprimer l’identifiant TMDb enregistré ?", content)
            self.assertNotIn("Supprimer l'identifiant TMDb enregistré ?", content)

        ui_content = (PAYLOAD / "openhtpc-ui.py").read_text(encoding="utf-8")
        tmdb_block = ui_content[ui_content.index('elif page == "tmdb":') : ui_content.index('elif page == "media_optical":')]
        self.assertNotIn('"Identifiant"', tmdb_block)
        self.assertNotIn("Identifiant enregistré", tmdb_block)

    # 3. Clé API v3 toujours acceptée
    def test_07_v3_api_key_accepted_and_validated(self):
        v3_key = "abcdef0123456789abcdef0123456789"
        recorded_requests = []

        def v3_opener(req, timeout=0):
            recorded_requests.append(req)
            return ResponseMock()

        result = tmdb_mgmt.validate(v3_key, opener=v3_opener)
        self.assertEqual(result["state"], "VALID")
        self.assertEqual(result["detail"], "Connexion à TMDb réussie")
        self.assertEqual(len(recorded_requests), 1)
        self.assertIn("api_key=" + v3_key, recorded_requests[0].full_url)
        self.assertNotIn("Authorization", recorded_requests[0].headers)

        # Persistence
        replace_result = tmdb_mgmt.replace(self.home, v3_key, opener=v3_opener)
        self.assertTrue(replace_result["committed"])
        self.assertEqual(tmdb_mgmt.credential(self.home), v3_key)
        self.assertEqual(self.token_file.read_text().strip(), v3_key)

    # 4. Jeton d'accès v4 toujours accepté
    def test_08_v4_access_token_accepted_and_validated(self):
        v4_token = "eyJhGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJhdWQiOiIxMjM0NTY3ODkwIiwic3ViIjoiZXhhbXBsZSJ9.signature"
        recorded_requests = []

        def v4_opener(req, timeout=0):
            recorded_requests.append(req)
            return ResponseMock()

        result = tmdb_mgmt.validate(v4_token, opener=v4_opener)
        self.assertEqual(result["state"], "VALID")
        self.assertEqual(result["detail"], "Connexion à TMDb réussie")
        self.assertEqual(len(recorded_requests), 1)
        self.assertNotIn("api_key=", recorded_requests[0].full_url)
        self.assertEqual(recorded_requests[0].headers.get("Authorization"), "Bearer " + v4_token)

        # Persistence
        replace_result = tmdb_mgmt.replace(self.home, v4_token, opener=v4_opener)
        self.assertTrue(replace_result["committed"])
        self.assertEqual(tmdb_mgmt.credential(self.home), v4_token)
        self.assertEqual(self.token_file.read_text().strip(), v4_token)

    # 5. Secret existant RC6 toujours relu sans migration ni réécriture
    def test_09_rc6_existing_secret_read_without_migration(self):
        rc6_token = "rc6_legacy_v3_key_0123456789abc"
        self._seed_rc6_token(rc6_token)
        token_stat_before = self.token_file.stat()

        # Read status and credential
        cred = tmdb_mgmt.credential(self.home)
        st = tmdb_mgmt.status(self.home)

        self.assertEqual(cred, rc6_token)
        self.assertEqual(st["masked"], "••••9abc")
        self.assertEqual(st["detail"], "Accès API TMDb enregistré, non testé")

        # Verify zero modification / no rewrite to the token file
        token_stat_after = self.token_file.stat()
        self.assertEqual(token_stat_before.st_mtime_ns, token_stat_after.st_mtime_ns)
        self.assertEqual(self.token_file.read_text().strip(), rc6_token)

    # 6. Stockage inchangé & 7. Permissions inchangées
    def test_10_storage_paths_and_strict_permissions(self):
        token_p, valid_p, config_p = tmdb_mgmt.paths(self.home)
        self.assertEqual(token_p, self.secrets_dir / "tmdb-token")
        self.assertEqual(valid_p, self.validation_file)
        self.assertEqual(config_p, self.config_file)

        # Test replace writes mode 0600 on file and 0700 on parent dir
        tmdb_mgmt.replace(self.home, "new_secret_key_12345", opener=lambda *a, **k: ResponseMock())
        self.assertEqual(self.secrets_dir.stat().st_mode & 0o777, 0o700)
        self.assertEqual(self.token_file.stat().st_mode & 0o777, 0o600)

        # Insecure permissions must be refused by credential()
        self.token_file.chmod(0o644)
        self.assertIsNone(tmdb_mgmt.credential(self.home))

    # 8. Aucun secret en clair dans l'UI ou les logs
    def test_11_no_cleartext_secret_leak_in_ui_or_status(self):
        secret = "super_secret_tmdb_token_xyz9999"
        tmdb_mgmt.replace(self.home, secret, opener=lambda *a, **k: ResponseMock())

        st = tmdb_mgmt.status(self.home)
        self.assertNotIn(secret, json.dumps(st))
        self.assertEqual(st["masked"], "••••9999")

        validation_data = json.loads(self.validation_file.read_text(encoding="utf-8"))
        self.assertNotIn(secret, json.dumps(validation_data))

        config_data = json.loads(self.config_file.read_text(encoding="utf-8"))
        self.assertNotIn(secret, json.dumps(config_data))

    # 9. Aucune modification du flux réseau TMDb
    def test_12_tmdb_network_flow_preserved(self):
        self._seed_rc6_token("32charv3apikey00000000000000000")
        sent_requests = []

        def tracking_opener(req, timeout=0):
            sent_requests.append((req, timeout))
            if "search/movie" in req.full_url:
                return ResponseMock(b'{"results":[{"id":42,"title":"Test Film","release_date":"2026-01-01"}]}')
            return ResponseMock(b'{"id":42,"title":"Test Film","release_date":"2026-01-01","overview":"Resume","credits":{}}')

        res = tmdb_core.lookup(self.home, "Test Film", opener=tracking_opener)
        self.assertEqual(res["status"], "PASS")
        self.assertEqual(len(sent_requests), 2)
        search_req, _ = sent_requests[0]
        self.assertIn("https://api.themoviedb.org/3/search/movie", search_req.full_url)
        self.assertIn("api_key=32charv3apikey00000000000000000", search_req.full_url)
        self.assertEqual(search_req.headers.get("Accept"), "application/json")

        details_req, _ = sent_requests[1]
        self.assertIn("https://api.themoviedb.org/3/movie/42", details_req.full_url)
        self.assertIn("api_key=32charv3apikey00000000000000000", details_req.full_url)


if __name__ == "__main__":
    unittest.main()
