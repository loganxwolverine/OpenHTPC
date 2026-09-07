# RC7 — T7.1 Audio discovery & resolution

Moteur autonome : `payload/openhtpc-audio.py`, bibliothèque standard Python.
Aucune intégration UI, installateur, MPV ou T5. Aucune écriture de configuration.
Le consommateur futur reste responsable de mémoriser le descripteur sélectionné.

## Architecture et contrat

- `discover_outputs()` : `pactl --format=json list sinks`, puis
  `pactl get-default-sink` uniquement si des sorties éligibles existent.
  Lecture seule, timeout de 1 seconde par commande (maximum deux commandes).
  Aucun fallback wpctl : pactl suffit pour les propriétés requises.
- `parse_sinks(raw, default_sink=None)` : normalisation pure. Exclusion RAOP,
  AirPlay, réseau, virtuel, ports explicitement indisponibles et sinks sans
  indice matériel. Les sinks SUSPENDED restent éligibles. Une disponibilité
  de port inconnue ne signifie pas déconnexion.
- `device_descriptor(output)` / `system_descriptor()` : objets JSON sans ID.
- `resolve_audio(configured, outputs)` : nom exact d'abord, puis égalité des
  deux champs non vides bus_path et edid_name, uniquement avec un résultat
  unique. Un nom exact ambigu échoue également. Aucun choix arbitraire.
- `recommend_output(outputs, interactive=False)` : SYSTEM en non interactif
  ou sans HDMI ; descripteur DEVICE suggéré si un seul HDMI ; `None` si plusieurs.
  Cette fonction ne change jamais CONFIGURED. Aucune règle de marque/canaux.

Sortie de résolution : `{CONFIGURED: descriptor, AVAILABLE: bool,
EFFECTIVE: descriptor}`. CONFIGURED conserve le choix fourni. DEVICE absent
ou ambigu donne AVAILABLE=false et EFFECTIVE=SYSTEM. En mode SYSTEM,
AVAILABLE=true signifie que l'option de politique existe, même sans serveur ;
ce n'est pas une preuve de fonctionnement audio. Aucun champ ACTIVE.
SYSTEM laisse Fedora choisir sa sortie, y compris réseau.

En cas de pactl absent, timeout, serveur inaccessible, JSON invalide ou racine
JSON incorrecte, discovery vaut `[]`. Une erreur de lecture du défaut conserve
les sorties découvertes avec is_default=false (défaut non confirmé).

## Schéma exact du descripteur

Six champs, aucun identifiant numérique PipeWire :

```json
{
  "mode": "DEVICE",
  "node_name": "alsa_output.pci-0000_04_00.0.hdmi-surround71",
  "bus_path": "pci-0000:04:00.0",
  "edid_name": "DENON-AVR",
  "display_label": "DENON-AVR",
  "device_type": "HDMI"
}
```

`mode`: SYSTEM | DEVICE. `device_type`: HDMI | ANALOG | USB | BLUETOOTH |
UNKNOWN. `node_name`, `bus_path`, `edid_name`: chaîne ou null ; node_name
est une chaîne non vide pour un DEVICE issu de discovery. display_label est
une chaîne. SYSTEM utilise node_name/bus_path/edid_name=null,
display_label="SYSTEM", device_type="UNKNOWN".

`edid_name` est un indice d'identité : priorité à edid.name,
device.product.name.edid, puis device.product.name du port sélectionné.
Pour HDMI, repli sur node.nick puis alsa.name. Il ne constitue donc pas une
preuve de lecture EDID directe. Les deux propriétés originales sont aussi
exposées dans discovery. Aucun rapprochement flou ni normalisation de marque.

## Observation réelle locale — 7 septembre 2026

Le serveur expose un HDMI physique, un RAOP Denon et un RAOP Volumio.
Résultat réel du moteur (les deux RAOP sont exclus) :

```json
[
  {
    "node_name": "alsa_output.pci-0000_04_00.0.hdmi-surround71",
    "display_label": "DENON-AVR",
    "device_type": "HDMI",
    "bus_path": "pci-0000:04:00.0",
    "edid_name": "DENON-AVR",
    "node.nick": "DENON-AVR",
    "alsa.name": "DENON-AVR",
    "is_network": false,
    "is_default": true
  }
]
```

Suggestion interactive : descripteur DEVICE ci-dessus. Non interactif :
SYSTEM. Dans le sandbox sans accès au serveur, pactl retourne une erreur de
connexion ; discovery est vide. Aucun téléviseur HDMI distinct observé :
ce cas est couvert par une fixture synthétique, pas présenté comme mesure réelle.
Aucune lecture MPV ni qualification de lecture sonore effectuée.

## Validation

`python3 -m pytest -q tests/test_rc7_audio_discovery.py` : **30 passed**.
Les 14 scénarios demandés sont couverts, plus USB/Bluetooth/UNKNOWN, défaut
Fedora réseau, panne de lecture du défaut, structures JSON malformées,
composite incomplet, priorité du nom exact, virtuel et port déconnecté.
Les appels subprocess sont vérifiés avec leur commande et leur timeout.
