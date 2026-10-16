--- a/payload/openhtpc-ui.py
+++ b/payload/openhtpc-ui.py
@@ -564,15 +564,18 @@
             txt((98, yy), f"{item.get('name', item.get('id', 'Extension'))}  ·  {item.get('version', 'N/A')}", 21, "#f7fbff", True, 780)
             txt((920, yy), item.get("activation_label", "Indéterminée"), 20, "#78d9ae" if item.get("activation_label") == "Activée" else "#a9bdd1", True, 300)
             txt((1240, yy + 2), item.get("provenance_label", "Provenance indéterminée"), 17, "#829bb5", False, 500)
-            if item.get("prerequisite_label"):
-                prerequisite_color = "#78d9ae" if item.get("external_prerequisite") == "DETECTED" else "#ffad42"
-                txt((118, yy + 38), item["prerequisite_label"], 17, prerequisite_color, True, 760)
-                txt((920, yy + 38), f"Capacité système : {item.get('readiness_label', 'Indéterminée')}", 17, prerequisite_color, False, 800)
-            else:
-                txt((118, yy + 38), f"Fonctions : {item.get('hooks', 'Aucune')}", 16, "#93a9c2", False, 760)
-                txt((920, yy + 38), f"Prérequis : {item.get('dependencies', 'Aucun')}", 16, "#93a9c2", False, 800)
+            # Deux lignes de détail à position et à sens FIXES pour toutes les extensions :
+            # ligne 1, ce que l'extension DÉCLARE ; ligne 2, ce que le SYSTÈME constate.
+            # « Prérequis » ne désigne donc plus qu'une seule chose : le prérequis système.
+            txt((118, yy + 38), f"Dépendances : {item.get('dependencies', 'Aucune')}", 16, "#93a9c2", False, 760)
+            txt((920, yy + 38), f"Fonctions : {item.get('hooks', 'Aucune')}", 16, "#93a9c2", False, 800)
+            prerequisite = item.get("external_prerequisite")
+            prerequisite_color = "#78d9ae" if prerequisite == "DETECTED" else "#ffad42" if prerequisite else "#93a9c2"
+            txt((118, yy + 66), item.get("prerequisite_label") or "Aucun prérequis système", 17, prerequisite_color, True, 760)
             if item.get("diagnostic") not in {"PASS", "CAPABILITY_DEPENDENCY_MISSING"}:
-                txt((118, yy + 66), f"Diagnostic : {item.get('diagnostic')}", 15, "#ffad42", False, 1600)
+                txt((920, yy + 66), f"Diagnostic : {item.get('diagnostic')}", 16, "#ffad42", False, 800)
+            else:
+                txt((920, yy + 66), f"Capacité système : {item.get('readiness_label') or 'Sans objet'}", 17, prerequisite_color, False, 800)
         if len(entries) > 4:
             txt((98, 812), f"+ {len(entries) - 4} extension(s) supplémentaire(s)", 16, "#93a9c2")
         txt((90, 900), "État issu du dernier relevé de capacités. « Prêt à tenter » ne garantit pas la lecture de chaque support.", 18, "#93a9c2", False, 1720)
