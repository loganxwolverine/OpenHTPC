--- a/tests/test_plugin_framework_generic_system.py
+++ b/tests/test_plugin_framework_generic_system.py
@@ -346,6 +346,30 @@
         loader.exec_module(devctl)
         self.assertEqual(devctl._source_fingerprint(ROOT / "vendor/flex-launcher"), metadata["flex_source_fingerprint"])
 
+    def test_extensions_detail_lines_have_one_fixed_meaning_per_line(self):
+        """Garde d'ergonomie : « Prérequis » ne désigne que le prérequis système.
+
+        Les deux lignes de détail de la page EXTENSIONS doivent occuper la même position pour
+        toutes les extensions (pas de bifurcation par extension) et les dépendances déclarées
+        doivent porter leur propre libellé. Sans cette garde, le retour au libellé ambigu
+        (« Prérequis : capacité:… ») ne casserait aucun test.
+        """
+        source = (PAYLOAD / "openhtpc-ui.py").read_text(encoding="utf-8")
+        self.assertIn('elif page == "extensions":', source)
+        section = source.split('elif page == "extensions":', 1)[1].split('elif page == "processing":', 1)[0]
+        # Libellés : les dépendances déclarées ne s'appellent plus « Prérequis ».
+        self.assertIn("Dépendances : ", section)
+        self.assertNotIn('f"Prérequis : ', section)
+        self.assertIn('item.get("prerequisite_label") or "Aucun prérequis système"', section)
+        # Emplacements fixes, sans bifurcation par extension : chaque coin de la ligne 1 est
+        # écrit une fois, le coin droit de la ligne 2 en deux exemplaires mutuellement exclusifs
+        # (« Capacité système », ou le diagnostic quand un problème réel existe).
+        self.assertEqual(section.count("txt((118, yy + 38)"), 1)
+        self.assertEqual(section.count("txt((920, yy + 38)"), 1)
+        self.assertEqual(section.count("txt((118, yy + 66)"), 1)
+        self.assertEqual(section.count("txt((920, yy + 66)"), 2)
+        self.assertNotIn('if item.get("prerequisite_label"):', section)
+
 
 if __name__ == "__main__":
     unittest.main()
