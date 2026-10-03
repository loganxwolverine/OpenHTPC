#!/usr/bin/env python3
"""Canonical OPENHTPC UI generation, validation and dashboard rendering."""
from __future__ import annotations

import configparser
import hashlib
import html
import json
import os
import pathlib
import tempfile
import textwrap

HOME_ACTIONS = ("LECTEUR", "ÉJECTER", "MÉDIA", "SYSTÈME", "ÉTEINDRE")
POWER_ACTIONS = ("QUITTER OPENHTPC", "ÉTEINDRE LE PC", "RETOUR")
SYSTEM_PAGES = (
    "root",
    "menu",
    "overview",
    "codecs",
    "display",
    "audio",
    "media_optical",
    "processing",
    "playback",
    "diagnostics",
    "technical",
    "about",
    "hardware",
    "display_video",
    "audio_media",
    "metadata",
    "tmdb",
)


def generation_id(optical: dict) -> str:
    visible = {key: optical.get(key) for key in ("state", "canonical_state", "disc_title", "volume_label", "device", "fingerprint", "playable", "playback_status", "uhd_status")}
    return "ui-" + hashlib.sha256(json.dumps(visible, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:16]


def validate_config_text(content: str) -> dict:
    parser = configparser.ConfigParser(interpolation=None, strict=True)
    parser.optionxform = str
    parser.read_string(content)
    required = {
        "OPENHTPC": HOME_ACTIONS,
        "SYSTEME": ("RETOUR",),
        "ALIMENTATION": POWER_ACTIONS,
    }
    result = {}
    for section, labels in required.items():
        if section not in parser:
            raise ValueError(f"UI_SECTION_MISSING:{section}")
        entries = [value.split(";", 1)[0] for key, value in parser[section].items() if key.startswith("Entry")]
        if len(entries) != len(set(entries)):
            raise ValueError(f"UI_DUPLICATE_ENTRY:{section}")
        for label in labels:
            if section == "OPENHTPC" and label == "LECTEUR":
                if any(value.split(";", 2)[-1].strip() == ":submenu DISQUE" for key, value in parser[section].items() if key.startswith("Entry")):
                    continue
            aliases = (label, "DVD -", "Blu-ray -", "UHD Blu-ray -") if label == "LECTEUR" else (label,)
            if not any(entry == alias or entry.startswith(alias + " ·") or entry.startswith(alias) for entry in entries for alias in aliases):
                raise ValueError(f"UI_ACTION_MISSING:{section}:{label}")
        for key, value in parser[section].items():
            fields = value.split(";", 2)
            if key.startswith("Entry") and (len(fields) != 3 or not fields[2].strip()):
                raise ValueError(f"UI_ACTION_INVALID:{section}:{key}")
        result[section] = entries
    return result


def atomic_text(target: pathlib.Path, content: str, mode: int = 0o600) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=target.name + ".", dir=target.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, target)
        directory = os.open(target.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def dashboard_svg(model: dict) -> str:
    model = {
        "runtime": "Prêt",
        "appliance": "En cours",
        "session": "N/A",
        "ui_instances": "1",
        "last_crash": "Aucun récent",
        "media_state": "Aucun disque",
        **model,
    }

    def esc(value):
        value = "N/A" if value in (None, "", [], {}) else str(value)
        return html.escape(value, quote=True)

    def wrap_lines(value, width=40):
        value = "N/A" if value in (None, "", [], {}) else str(value)
        return textwrap.wrap(value, width=width, break_long_words=True, break_on_hyphens=False, max_lines=2, placeholder="") or ["N/A"]

    panels = [
        ("ÉTAT OPENHTPC", [
            ("Core", model["services"]),
            ("Runtime MPV", model["runtime"]),
            ("Interface", model["appliance"]),
            ("Session", model["session"]),
            ("Instances UI", model["ui_instances"]),
            ("Dernier crash Flex", model["last_crash"]),
        ]),
        ("HARDWARE PASSPORT", [
            ("CPU", model["cpu"]),
            ("GPU", model["gpu"]),
            ("RAM", model["ram"]),
            ("Audio", model.get("audio_sink") or model.get("audio")),
            ("Lecteur optique", model["optical"]),
            ("Média", model["media_state"]),
            ("Vulkan", model["vulkan"]),
            ("VA-API", model["vaapi"]),
        ]),
        ("MODULES & LECTURE", [
            ("DVD", model["dvd"]),
            ("Média", model["media_module"]),
            ("TMDb", model["tmdb"]),
            ("Disc Monitor", model["disc_monitor"]),
        ] + [(name.capitalize(), value) for name, value in model.get("optional", {}).items()]),
    ]
    blocks = []
    for index, (title, rows) in enumerate(panels):
        x = 70 + index * 600
        lines = [
            f'<rect x="{x}" y="185" width="550" height="700" rx="28" fill="#071426" fill-opacity=".90" stroke="#19bff5" stroke-width="3"/>',
            f'<text x="{x+34}" y="245" font-family="sans-serif" font-size="25" font-weight="700" fill="#22c7ff">{esc(title)}</text>',
        ]
        for row, (label, value) in enumerate(rows):
            y = 300 + row * 64
            value_lines = wrap_lines(value)
            lines += [
                f'<text x="{x+34}" y="{y}" font-family="sans-serif" font-size="18" font-weight="600" fill="#93a9c2">{esc(label)}</text>',
                f'<text x="{x+34}" y="{y+27}" font-family="sans-serif" font-size="22" fill="#f7fbff">{esc(value_lines[0])}</text>',
            ]
            if len(value_lines) > 1:
                lines.append(f'<text x="{x+34}" y="{y+51}" font-family="sans-serif" font-size="19" fill="#d8e5f1">{esc(value_lines[1])}</text>')
        blocks.extend(lines)
    status = "#31d17c" if model.get("overall") == "READY" else "#ff9f1c"
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="1920" height="1080" viewBox="0 0 1920 1080">
<defs><linearGradient id="bg" x2="1" y2="1"><stop stop-color="#020711"/><stop offset="1" stop-color="#071c34"/></linearGradient></defs>
<rect width="1920" height="1080" fill="url(#bg)"/><circle cx="105" cy="90" r="42" fill="none" stroke="#20c8ff" stroke-width="8"/><path d="M96 67 L128 90 L96 113Z" fill="#ff9f1c"/>
<text x="170" y="105" font-family="sans-serif" font-size="38" font-weight="700" fill="#f4f8ff">OPENHTPC</text><text x="70" y="160" font-family="sans-serif" font-size="46" font-weight="700" fill="#22c7ff">SYSTÈME</text>
<circle cx="1600" cy="92" r="10" fill="{status}"/><text x="1620" y="102" font-family="sans-serif" font-size="23" font-weight="600" fill="#f4f8ff">{esc(model.get('health', 'PRÊT'))}</text>
{''.join(blocks)}
<text x="70" y="1015" font-family="sans-serif" font-size="22" fill="#a9bdd1">Échap / Retour arrière / Entrée — RETOUR À L’ACCUEIL</text></svg>"""


def dashboard_png(model: dict, target: pathlib.Path, font_path: pathlib.Path) -> None:
    model = {
        "runtime": "Prêt",
        "appliance": "En cours",
        "session": "N/A",
        "ui_instances": "1",
        "last_crash": "Aucun récent",
        "media_state": "Aucun disque",
        **model,
    }
    from PIL import Image, ImageDraw, ImageFont

    image = Image.new("RGB", (1920, 1080), "#020711")
    draw = ImageDraw.Draw(image)

    def font(size):
        return ImageFont.truetype(str(font_path), size)

    def fit(value, limit=40):
        value = "N/A" if value in (None, "", [], {}) else str(value)
        return textwrap.wrap(value, width=limit, break_long_words=True, break_on_hyphens=False, max_lines=2, placeholder="") or ["N/A"]

    draw.ellipse((63, 48, 147, 132), outline="#20c8ff", width=8)
    draw.polygon(((96, 67), (128, 90), (96, 113)), fill="#ff9f1c")
    draw.text((170, 60), "OPENHTPC", font=font(38), fill="#f4f8ff")
    draw.text((70, 120), "SYSTÈME", font=font(46), fill="#22c7ff")
    health_color = "#31d17c" if model.get("overall") == "READY" else "#ff9f1c"
    draw.ellipse((1590, 82, 1610, 102), fill=health_color)
    draw.text((1620, 70), fit(model.get("health", "PRÊT"), 28)[0], font=font(23), fill="#f4f8ff")
    panels = [
        ("ÉTAT OPENHTPC", [
            ("Core", model["services"]),
            ("Runtime MPV", model["runtime"]),
            ("Interface", model["appliance"]),
            ("Session", model["session"]),
            ("Instances UI", model["ui_instances"]),
            ("Dernier crash Flex", model["last_crash"]),
        ]),
        ("HARDWARE PASSPORT", [
            ("CPU", model["cpu"]),
            ("GPU", model["gpu"]),
            ("RAM", model["ram"]),
            ("Audio", model.get("audio_sink") or model.get("audio")),
            ("Lecteur optique", model["optical"]),
            ("Média", model["media_state"]),
            ("Vulkan", model["vulkan"]),
            ("VA-API", model["vaapi"]),
        ]),
        ("MODULES & LECTURE", [
            ("DVD", model["dvd"]),
            ("Média", model["media_module"]),
            ("TMDb", model["tmdb"]),
            ("Disc Monitor", model["disc_monitor"]),
        ] + [(k.capitalize(), v) for k, v in model.get("optional", {}).items()]),
    ]
    for index, (title, rows) in enumerate(panels):
        x = 70 + index * 600
        draw.rounded_rectangle((x, 185, x + 550, 885), 28, fill="#071426", outline="#19bff5", width=3)
        draw.text((x + 34, 210), title, font=font(25), fill="#22c7ff")
        for row, (label, value) in enumerate(rows):
            y = 268 + row * 64
            value_lines = fit(value)
            draw.text((x + 34, y), str(label), font=font(18), fill="#93a9c2")
            draw.text((x + 34, y + 24), value_lines[0], font=font(22), fill="#f7fbff")
            if len(value_lines) > 1:
                draw.text((x + 34, y + 47), value_lines[1], font=font(18), fill="#d8e5f1")
    draw.text((70, 985), "Échap / Retour arrière / Entrée — RETOUR À L’ACCUEIL", font=font(22), fill="#a9bdd1")
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=target.name + ".", dir=target.parent)
    os.close(fd)
    try:
        image.save(tmp, "PNG", optimize=True)
        os.chmod(tmp, 0o600)
        os.replace(tmp, target)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


PAGE_TITLES = {
    "root": "SYSTÈME",
    "menu": "SYSTÈME",
    "overview": "VUE D’ENSEMBLE",
    "codecs": "COMPATIBILITÉ VIDÉO",
    "display": "AFFICHAGE",
    "audio": "AUDIO",
    "media_optical": "MÉDIAS & OPTIQUE",
    "processing": "TRAITEMENT VIDÉO",
    "playback": "LECTURE",
    "diagnostics": "DIAGNOSTIC",
    "technical": "INFORMATIONS TECHNIQUES",
    "about": "À PROPOS",
    "hardware": "MATÉRIEL & GRAPHIQUES",
    "display_video": "AFFICHAGE & VIDÉO",
    "audio_media": "AUDIO & MÉDIAS",
    "metadata": "MÉTADONNÉES",
    "tmdb": "TMDb",
}


def system_page_png(
    model: dict,
    target: pathlib.Path,
    font_path: pathlib.Path,
    page: str = "overview",
    size: tuple[int, int] = (1920, 1080),
) -> None:
    """Render a couch-first canonical capability page; no probing is performed here."""
    if page not in SYSTEM_PAGES:
        raise ValueError(f"SYSTEM_PAGE_UNKNOWN:{page}")
    from PIL import Image, ImageDraw, ImageFont

    width, height = size
    scale = width / 1920
    image = Image.new("RGB", size, "#020711")
    draw = ImageDraw.Draw(image)

    def xy(v):
        return int(v * scale)

    def font(n, bold=False):
        candidate = font_path.with_name("OpenSans-Semibold.ttf") if bold else font_path
        return ImageFont.truetype(str(candidate if candidate.is_file() else font_path), xy(n))

    def txt(pos, value, n=24, color="#f4f8ff", bold=False, max_width=None):
        value = "Indéterminé" if value in (None, "", [], {}) else str(value)
        if max_width:
            while draw.textlength(value, font=font(n, bold)) > xy(max_width) and len(value) > 4:
                value = value[:-2].rstrip() + "…"
        draw.text((xy(pos[0]), xy(pos[1])), value, font=font(n, bold), fill=color)

    def card(box, title, rows, label_ratio=0.42, step=None):
        x, y, w, h = box
        draw.rounded_rectangle(
            (xy(x), xy(y), xy(x + w), xy(y + h)),
            radius=xy(24),
            fill="#071426",
            outline="#168fbd",
            width=max(2, xy(2)),
        )
        txt((x + 28, y + 22), title, 24, "#22c7ff", True, w - 56)
        available = h - 76
        row_step = step if step is not None else max(54, min(80, available / max(1, len(rows))))
        val_offset = label_ratio + 0.02
        val_ratio = 1.0 - val_offset - 0.04
        for index, (label, value, status) in enumerate(rows):
            yy = y + 74 + index * row_step
            txt((x + 28, yy), label, 18, "#93a9c2", False, w * label_ratio)
            txt((x + w * val_offset, yy - 2), value, 22, status or "#f7fbff", False, w * val_ratio)

    draw.rectangle((0, 0, width, height), fill="#020711")
    draw.rectangle((0, 0, width, xy(140)), fill="#041022")

    header_title = PAGE_TITLES.get(page, "SYSTÈME")
    txt((68, 36), "OPENHTPC", 26, "#f4f8ff", True)
    txt((68, 76), header_title, 36, "#22c7ff", True)

    product = model.get("product", {})
    health_color = "#78d9ae" if product.get("overall") == "READY" else "#ffad42"
    txt((1440, 42), f"ÉTAT : {product.get('health', 'PRÊT')}", 22, health_color, True, 410)
    txt((1440, 78), product.get("version") or "", 18, "#a9bdd1", False, 410)

    if not model.get("available") and page != "playback":
        card(
            (70, 170, 1780, 680),
            "INFORMATIONS SYSTÈME",
            [
                ("État", "Informations système temporairement indisponibles", "#ffad42"),
                ("Action", "Actualiser les capacités", "#f7fbff"),
            ],
        )
    elif page in ("root", "menu"):
        o = model.get("overview", {})
        p = model.get("processing", {})
        d = model.get("display", {})
        a = model.get("audio_section") or model.get("audio_media") or {}
        card(
            (960, 160, 890, 700),
            "ÉTAT DU SYSTÈME",
            [
                ("Machine", o.get("machine"), None),
                ("Configuration", f"{o.get('cpu')} • {o.get('ram')}", None),
                ("Graphiques", f"{o.get('gpu')}", None),
                ("Affichage", o.get("display") or d.get("summary") or d.get("resolution"), None),
                ("Audio", a.get("audio_output"), None),
                ("Moteur vidéo", p.get("profile"), None),
                ("Santé globale", product.get("health", "PRÊT"), health_color),
                ("Informations système", "À actualiser" if model.get("stale") else "À jour", None),
            ],
        )
        draw.rounded_rectangle(
            (xy(960), xy(880), xy(1850), xy(970)),
            radius=xy(16),
            fill="#051224",
            outline="#168fbd",
            width=max(2, xy(2)),
        )
        txt((988, 912), "▲ / ▼ : Naviguer   •   Entrée : Ouvrir   •   Échap : Retour", 20, "#93a9c2", True, 840)
    elif page == "overview":
        o = model["overview"]
        card(
            (70, 170, 1780, 290),
            "VUE D’ENSEMBLE",
            [
                ("Machine", o["machine"], None),
                ("Configuration", f"{o['cpu']} • {o['ram']}", None),
                ("Graphiques", o.get("gpu"), None),
                ("Accélération vidéo", o.get("video_accel") or o.get("graphics") or "Non déterminé", None),
                ("Affichage", o["display"], None),
            ],
            step=42,
        )
        card(
            (70, 480, 860, 360),
            "ÉTAT OPENHTPC",
            [
                ("Santé globale", product.get("health", "PRÊT"), health_color),
                ("Informations système", "À actualiser" if model.get("stale") else "À jour", None),
                ("Généré le", model.get("generated_at"), None),
            ],
        )
        p = model["processing"]
        mag = model.get("magnificence", {})
        mode_is_mag = p.get("profile") == "MAGNIFICENCE"
        source_label = {
            "STATIC_PROFILE_DB": "Profil OPENHTPC qualifié",
            "GPU_KNOWLEDGE_DB": "Base GPU évolutive",
        }.get(mag.get("selection_source"), "Non déterminée")
        recipe_label = mag.get("selected_label") if mode_is_mag and mag.get("status") != "NO_PROFILE" else "PURE"
        card(
            (960, 480, 890, 360),
            "TRAITEMENT VIDÉO",
            [
                ("Mode", p["profile"], "#22c7ff" if mode_is_mag else "#78d9ae"),
                ("Sortie", p["output"], None),
                ("Recette", recipe_label, None),
                ("Sélection", source_label if mode_is_mag else "Référence directe", None),
            ],
        )
    elif page == "codecs":
        x, y, w, h = 250, 170, 1420, 680
        draw.rounded_rectangle(
            (xy(x), xy(y), xy(x + w), xy(y + h)),
            radius=xy(24),
            fill="#071426",
            outline="#168fbd",
            width=max(2, xy(2)),
        )
        txt((x + 34, y + 26), "CAPACITÉS DE LECTURE MATÉRIELLE", 26, "#22c7ff", True)
        subtitle = model.get("codecs_subtitle") or model.get("display", {}).get("codecs_subtitle") or "GPU de rendu : Indéterminé"
        accel = model.get("overview", {}).get("video_accel")
        if accel and accel != "Non déterminé":
            subtitle = f"{subtitle} • Accélération : {accel}"
        txt((x + 34, y + 64), subtitle, 17, "#93a9c2", False, 1320)
        txt((x + 34, y + 108), "FORMAT", 18, "#93a9c2", True)
        txt((x + 760, y + 108), "DÉCODAGE MATÉRIEL", 18, "#93a9c2", True)
        codec_list = model.get("codecs") or model.get("display", {}).get("codecs", [])
        for index, item in enumerate(codec_list):
            yy = y + 154 + index * 66
            txt((x + 34, yy), item["name"], 23, "#f7fbff", True, 650)
            status = item.get("hardware") or "Non déterminé"
            status_color = "#78d9ae" if status == "Pris en charge" else "#ffad42" if status == "Non pris en charge" else "#a9bdd1"
            txt((x + 760, yy), status, 21, status_color, True, 360)
            backend = item.get("backend")
            if backend and backend != "Indéterminé":
                txt((x + 1140, yy + 2), backend, 17, "#829bb5", False, 220)
    elif page == "display":
        d = model["display"]
        display_rows = [
            ("Sortie active", d["connector"], None),
            ("Résolution", d["resolution"], None),
            ("Fréquence", d["refresh"], None),
            ("Échelle KDE", d["scale"], None),
        ]
        if d.get("depth"):
            display_rows.append(("Profondeur de couleur", d["depth"], None))
        card(
            (70, 170, 860, 680),
            "AFFICHAGE ACTIF",
            display_rows,
        )
        card(
            (960, 170, 890, 320),
            "CAPACITÉS HDR",
            [
                ("Mode HDR actuel", d["hdr_current"], None),
                ("Écran compatible HDR", d["hdr_capable"], None),
                ("Pipeline HDR validé", d["hdr_pipeline"], None),
            ],
        )
        card(
            (960, 510, 890, 340),
            "ENVIRONNEMENT D'AFFICHAGE",
            [
                ("Gestionnaire de session", d.get("session", "Non déterminé"), None),
                ("Résolveur de capacités", d.get("resolver", "Non déterminé"), None),
                ("Mode de rafraîchissement", d.get("auto_refresh") if d.get("auto_refresh") in ("Automatique", "Désactivé") else "Non déterminé", None),
            ],
        )
    elif page == "audio":
        a = model.get("audio_section") or model.get("audio_media") or {}
        configured_label = a.get("configured_label") or a.get("audio_output") or "Sortie système — Fedora"
        state_label = a.get("state_label", "Disponible")
        state_color = "#78d9ae" if state_label == "Disponible" else "#ffad42"
        effective_label = a.get("effective_label") or configured_label
        rows_output = [
            ("Sortie configurée", configured_label, None),
            ("État", state_label, state_color),
        ]
        if a.get("is_fallback"):
            rows_output.append(("Cible effective", effective_label, "#ffad42"))
        else:
            rows_output.append(("Cible effective", effective_label, None))
        rows_output.extend([
            ("Serveur audio", a.get("audio_backend") or "PipeWire", None),
            ("Type de connexion", a.get("connection") or "Indéterminé", None),
        ])
        card(
            (70, 170, 860, 680),
            "SORTIE AUDIO",
            rows_output,
        )
        card(
            (960, 170, 890, 680),
            "MODE AUDIO & CONFIGURATION",
            [
                ("Mode audio", a.get("requested_mode", "PCM"), None),
                ("Passthrough numérique", a.get("passthrough", "Inactif"), None),
                ("Récepteur", a.get("receiver"), None),
                ("Contrôle du volume", "Géré par PipeWire", None),
                ("Gestionnaire de flux", "PipeWire / WirePlumber", None),
            ],
        )
    elif page == "metadata":
        card(
            (70, 170, 1780, 680),
            "MÉTADONNÉES",
            [
                ("TMDb", model.get("tmdb_management", {}).get("label", "NON CONFIGURÉ"), None),
                ("Rôle", "Enrichissement facultatif des fiches de films", None),
                ("Lecture", "Indépendante de TMDb", None),
            ],
        )
    elif page == "tmdb":
        tmdb = model.get("tmdb_management", {})
        rows = [("État", tmdb.get("label", "NON CONFIGURÉ"), "#78d9ae" if tmdb.get("state") == "VALID" else None)]
        if tmdb.get("masked"):
            rows.append(("Accès API TMDb", tmdb["masked"], None))
            rows.append(("Dernier test", tmdb.get("detail", "Accès API TMDb enregistré, non testé"), None))
        else:
            rows.extend((("Service", "TMDb permet d’afficher affiches et informations des films", None),
                         ("Lecture", "TMDb est facultatif", None)))
        card((70, 170, 1780, 680), "GESTION TMDb", rows)
    elif page == "media_optical":
        m = model.get("media_optical") or model.get("audio_media", {})
        card(
            (70, 170, 860, 680),
            "SOURCES MÉDIAS",
            [
                ("Sources configurées", m.get("configured"), None),
                ("Sources accessibles", m.get("accessible"), "#ffad42" if m.get("configured") and not m.get("accessible") else None),
                ("Types de stockage", m.get("source_types"), None),
                ("Moteur de lecture", m.get("playback"), None),
            ],
        )
        card(
            (960, 170, 890, 680),
            "SUPPORTS OPTIQUES",
            [
                ("Lecteurs détectés", m.get("drives"), None),
                ("Support DVD Vidéo", m.get("dvd"), None),
                ("Déchiffrement CSS", m.get("css"), None),
                ("Extension Blu-ray", m.get("bluray"), None),
                ("Extension UHD Blu-ray", m.get("uhd"), None),
            ],
        )
    elif page == "processing":
        p = model.get("playback_policy", {})
        mag = model.get("magnificence", {})
        enabled = p.get("presentation_mode") == "CINEMA_AUTO"
        available = mag.get("status") != "NO_PROFILE"

        if not enabled:
            mode_label = "PURE"
            mode_color = "#78d9ae"
            summary = "Image de référence directe, sans traitement vidéo additionnel."
        elif available:
            mode_label = "MAGNIFICENCE"
            mode_color = "#22c7ff"
            summary = "OPENHTPC sélectionne automatiquement une recette adaptée au matériel et à l'affichage."
        else:
            mode_label = "MAGNIFICENCE — REPLI PURE"
            mode_color = "#ffad42"
            summary = "Aucune recette qualifiée n'est disponible pour cette combinaison ; PURE reste actif en sécurité."

        source_labels = {
            "STATIC_PROFILE_DB": "Profil OPENHTPC qualifié",
            "GPU_KNOWLEDGE_DB": "Base GPU évolutive",
        }
        confidence_labels = {
            "OPENHTPC_PHYSICAL_QUALIFICATION": "Validation physique OPENHTPC",
            "COMMUNITY_DERIVED": "Référence communautaire prudente",
            "CONSERVATIVE_CAPABILITY_BASELINE": "Base de capacités prudente",
        }
        selection_source = source_labels.get(mag.get("selection_source"), "Non déterminée")
        confidence_key = mag.get("classification_confidence")
        confidence = confidence_labels.get(confidence_key, confidence_key or "Non déterminée")
        if confidence_key == "OPENHTPC_PHYSICAL_QUALIFICATION":
            validation_label = "Qualifiée sur ce matériel"
        elif mag.get("status") == "FAMILY_CLASSIFIED":
            validation_label = "Famille validée OPENHTPC"
        elif mag.get("status") == "CAPABILITY_BASELINE":
            validation_label = "Base de capacités prudente"
        else:
            validation_label = "Sélection automatique"
        recipe = mag.get("selected_label") or mag.get("selected_recipe") or "PURE"
        scope_labels = {"DVD_PAL_FILM": "DVD PAL / SD"}
        scope_label = scope_labels.get(mag.get("source_class"), mag.get("source_class") or "DVD PAL / SD")

        draw.rounded_rectangle(
            (xy(70), xy(170), xy(1850), xy(430)), radius=xy(24),
            fill="#071426", outline="#168fbd", width=max(2, xy(2)),
        )
        txt((98, 194), "MAGNIFICENCE — ÉTAT DU TRAITEMENT VIDÉO", 24, "#22c7ff", True)
        txt((98, 246), "Mode actif", 18, "#93a9c2", False)
        txt((280, 242), mode_label, 28, mode_color, True, 1480)
        txt((98, 304), "Comportement", 18, "#93a9c2", False)
        txt((280, 302), summary, 20, "#f4f8ff", False, 1480)
        txt((98, 362), "Sélection", 18, "#93a9c2", False)
        txt((280, 360), "Automatique selon le matériel, l'affichage et le média, sans réglage manuel.", 18, "#93a9c2", False, 1480)

        card((70, 460, 860, 390), "RECETTE SÉLECTIONNÉE", [
            ("GPU", mag.get("gpu") or "Non déterminé", None),
            ("Affichage", mag.get("display") or "Non déterminé", None),
            ("Recette", recipe if enabled and available else "PURE", "#22c7ff" if enabled and available else "#78d9ae"),
            ("Validation", validation_label if enabled and available else "Référence directe", None),
        ], label_ratio=0.28, step=66)
        card((960, 460, 890, 390), "ORIGINE DE LA DÉCISION", [
            ("Source", selection_source if enabled and available else "Mode PURE", None),
            ("Confiance", confidence if enabled and available else "Référence directe", None),
            ("Périmètre", scope_label, None),
            ("Sécurité", "PURE automatique si les prérequis sont absents", "#78d9ae"),
        ], label_ratio=0.30, step=66)
        txt((90, 900), "PURE et MAGNIFICENCE se choisissent dans LECTURE / MODE VIDÉO. Cette page explique la décision appliquée.", 18, "#93a9c2", False, 1720)
    elif page == "playback":
        p = model.get("playback_policy", {})
        mag = model.get("magnificence", {})
        presentation = "MAGNIFICENCE" if p.get("presentation_mode") == "CINEMA_AUTO" else "PURE"
        audio = {"AUTO":"Auto","FR":"Français","DEFAULT":"Piste par défaut"}.get(p.get("audio_language_policy"), "Auto")
        subtitle = {"AUTO":"Auto","OFF":"Désactivés","FR_FORCED":"Français forcés","FR_FULL":"Français complets"}.get(p.get("subtitle_policy"), "Auto")
        if presentation == "MAGNIFICENCE":
            shaders = mag.get("selected_label") or "PURE"
            no_profile = mag.get("status") == "NO_PROFILE"
            if no_profile:
                shaders = "Aucun (repli PURE)"
            rows = [
                ("Mode vidéo", presentation, "#22c7ff"),
                ("Traitement", "Repli de sécurité" if no_profile else "Renforcé", "#78d9ae" if no_profile else "#22c7ff"),
                ("Shaders", shaders, "#78d9ae" if no_profile else "#22c7ff"),
                ("Langue audio", audio, None),
                ("Sous-titres", subtitle, None),
                ("Application", "À la prochaine lecture", None),
                ("Réglages mémorisés", "Oui", None),
            ]
        else:
            rows = [
                ("Mode vidéo", "PURE", "#78d9ae"),
                ("Traitement", "Aucun", None),
                ("Shaders", "Aucun", None),
                ("Langue audio", audio, None),
                ("Sous-titres", subtitle, None),
                ("Application", "À la prochaine lecture", None),
                ("Réglages mémorisés", "Oui", None),
            ]
        card((70, 170, 1780, 500), "LECTURE — PRÉFÉRENCES ACTIVES", rows)
        txt((90, 715), "ACTIONS", 20, "#22c7ff", True)
        txt((90, 755), "PURE ou MAGNIFICENCE se règle uniquement ici — OPENHTPC adapte ensuite le traitement automatiquement.", 18, "#93a9c2", False)
    elif page == "about":
        version = model.get("technical", {}).get("version", "1.1.2-dev1")
        card(
            (70, 170, 730, 680),
            "PROJET",
            [
                ("Projet", "OPENHTPC", "#22c7ff"),
                ("Version", version, None),
                ("Origine", "Projet créé par Steve Dehanne", None),
            ],
            label_ratio=0.28,
        )
        card(
            (1120, 170, 730, 680),
            "LICENCE & DÉPÔT",
            [
                ("Copyright", "Copyright 2026 Steve Dehanne", None),
                ("Licence", "Apache 2.0", None),
                ("Dépôt officiel", "github.com/loganxwolverine/OpenHTPC", None),
            ],
            label_ratio=0.28,
        )
    elif page == "diagnostics":
        d = model["diagnostics"]
        allowed_checks = {
            "OPENHTPC Core", "Cœur système OPENHTPC",
            "Hardware Passport", "Passeport matériel",
            "Generated Runtime", "Environnement généré",
            "Flex Launcher", "Lanceur d'interface (Flex)", "Lanceur d'interface",
            "Media Browser", "Explorateur de médias",
            "DVD", "Prise en charge DVD",
            "Capability snapshot", "Instantané des capacités",
        }
        rows = [
            (item["label"], item["status"], None)
            for item in d.get("checks", [])
            if item.get("label") in allowed_checks
        ]
        card((70, 170, 1050, 680), "DIAGNOSTIC SANTÉ OPENHTPC", rows or [("État global", d["overall"], None)])
        card(
            (1150, 170, 700, 680),
            "ACTIONS & MAINTENANCE",
            [
                ("État global", d["overall"], health_color),
                ("Instantané capacités", d["snapshot"], None),
                ("Dernière action", d["last_action"], None),
                ("Génération rapport", "Prêt", None),
            ],
        )
        txt((1150 + 28, 170 + 440), "CONFIDENTIALITÉ", 20, "#22c7ff", True, 644)
        txt((1150 + 28, 170 + 480), "Le rapport d'assistance rassemble uniquement la configuration", 18, "#93a9c2", False, 644)
        txt((1150 + 28, 170 + 514), "technique de cet appareil pour faciliter le diagnostic.", 18, "#93a9c2", False, 644)
        txt((1150 + 28, 170 + 548), "Vérifiez son contenu avant de le partager.", 18, "#93a9c2", False, 644)
    elif page == "hardware":
        h = model["hardware"]
        card(
            (70, 170, 720, 680),
            "MATÉRIEL",
            [
                ("Machine", h["machine"], None),
                ("Fabricant", h["manufacturer"], None),
                ("Processeur", h["cpu"], None),
                ("Architecture", h["architecture"], None),
                ("Threads", h["logical_cores"], None),
                ("Mémoire", h["ram"], None),
            ],
        )
        gpu_rows = []
        for gpu in h.get("gpus", []):
            gpu_rows.extend([(gpu["role"], gpu["name"], None), ("Pilote", gpu["driver"], None), ("Mémoire", gpu["memory"], None)])
        gpu_rows.extend([("Vulkan", h.get("vulkan"), None), ("VA-API", h.get("vaapi"), None)])
        card((820, 170, 1030, 680), "GRAPHIQUES", gpu_rows[:9] or [("GPU", "Indéterminé", None)])
    elif page == "display_video":
        d = model["display"]
        card(
            (70, 170, 570, 680),
            "AFFICHAGE",
            [
                ("Sortie active", d["connector"], None),
                ("Résolution", d["resolution"], None),
                ("Fréquence", d["refresh"], None),
                ("Échelle", d["scale"], None),
                ("Profondeur", d["depth"], None),
                ("HDR actuel", d["hdr_current"], None),
                ("Écran HDR", d["hdr_capable"], None),
                ("Pipeline HDR", d["hdr_pipeline"], None),
            ],
        )
        x, y, w, h = 670, 170, 1180, 680
        draw.rounded_rectangle((xy(x), xy(y), xy(x + w), xy(y + h)), radius=xy(24), fill="#071426", outline="#168fbd", width=max(2, xy(2)))
        txt((x + 28, y + 24), "COMPATIBILITÉ VIDÉO", 24, "#22c7ff", True)
        subtitle = model.get("codecs_subtitle") or model.get("display", {}).get("codecs_subtitle") or "GPU de rendu : Indéterminé"
        txt((x + 28, y + 54), subtitle, 16, "#93a9c2", False, 400)
        for pos, label in ((x + 440, "LOGICIEL"), (x + 675, "CAPACITÉ GPU"), (x + 930, "LECTURE")):
            txt((pos, y + 78), label, 17, "#93a9c2", True)
        for index, item in enumerate(d.get("codecs", [])):
            yy = y + 116 + index * 68
            txt((x + 28, yy), item["name"], 21, "#f7fbff", True, 370)
            txt((x + 440, yy), item["software"], 18, "#d8e5f1", False, 210)
            txt((x + 675, yy), item["hardware"], 18, "#d8e5f1", False, 230)
            color = "#78d9ae" if item["validated"] == "Validé" else "#c5d1dd"
            txt((x + 930, yy), item["validated"], 18, color, True, 220)
    elif page == "audio_media":
        a = model.get("audio_media", {})
        card(
            (70, 170, 560, 680),
            "AUDIO",
            [
                ("Sortie", a.get("audio_output"), None),
                ("Serveur", a.get("audio_backend"), None),
                ("Connexion", a.get("connection"), None),
                ("Canaux actifs", a.get("channels"), None),
                ("Passthrough", a.get("passthrough"), None),
            ],
        )
        card(
            (660, 170, 560, 680),
            "MÉDIAS",
            [
                ("Sources configurées", a.get("configured"), None),
                ("Sources accessibles", a.get("accessible"), "#ffad42" if a.get("configured") and not a.get("accessible") else None),
                ("Types", a.get("source_types"), None),
                ("Lecteur", a.get("playback"), None),
            ],
        )
        card(
            (1250, 170, 600, 680),
            "SUPPORTS OPTIQUES",
            [
                ("Lecteurs", a.get("drives"), None),
                ("DVD", a.get("dvd"), None),
                ("CSS DVD", a.get("css"), None),
                ("Blu-ray OPENHTPC", a.get("bluray"), None),
                ("UHD OPENHTPC", a.get("uhd"), None),
            ],
        )
    else:
        t = model["technical"]
        card(
            (70, 170, 1780, 680),
            "INFORMATIONS TECHNIQUES DÉTAILLÉES",
            [
                ("Version OPENHTPC", t["version"], None),
                ("Identifiant de build", t["build"], None),
                ("Schéma de capacités", t["schema"], None),
                ("Version des sondes", t["probe"], None),
                ("Instantané généré le", t["generated"], None),
                ("Connecteur d'affichage", t["connector"], None),
                ("GPU de rendu", t.get("render_gpu", "Indéterminé"), None),
                ("Liaison Vulkan", t.get("vulkan_binding", "Non déterminé"), None),
                ("Décodage configuré", t.get("configured_hwdec", "Non déterminé"), None),
                ("GPU physique de décodage", "Non déterminé", None),
                ("Pilote Vulkan", t["vulkan_driver"], None),
                ("Pilote VA-API", t["vaapi_driver"], None),
                ("Version MPV", t["mpv"], None),
                ("Version FFmpeg", t["ffmpeg"], None),
            ],
            step=43,
        )

    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=target.name + ".", dir=target.parent)
    os.close(fd)
    try:
        image.save(tmp, "PNG", optimize=True)
        os.chmod(tmp, 0o600)
        os.replace(tmp, target)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
