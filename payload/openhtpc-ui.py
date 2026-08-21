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
    "diagnostics",
    "technical",
    "hardware",
    "display_video",
    "audio_media",
)


def generation_id(optical: dict) -> str:
    visible = {key: optical.get(key) for key in ("state", "disc_title", "volume_label", "device", "fingerprint")}
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
    "diagnostics": "DIAGNOSTIC",
    "technical": "INFORMATIONS TECHNIQUES",
    "hardware": "MATÉRIEL & GRAPHIQUES",
    "display_video": "AFFICHAGE & VIDÉO",
    "audio_media": "AUDIO & MÉDIAS",
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

    def card(box, title, rows):
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
        step = max(54, min(80, available / max(1, len(rows))))
        for index, (label, value, status) in enumerate(rows):
            yy = y + 74 + index * step
            txt((x + 28, yy), label, 18, "#93a9c2", False, w * 0.42)
            txt((x + w * 0.44, yy - 2), value, 22, status or "#f7fbff", False, w * 0.52)

    draw.rectangle((0, 0, width, height), fill="#020711")
    draw.rectangle((0, 0, width, xy(140)), fill="#041022")

    header_title = PAGE_TITLES.get(page, "SYSTÈME")
    txt((68, 36), "OPENHTPC", 26, "#f4f8ff", True)
    txt((68, 76), header_title, 36, "#22c7ff", True)

    product = model.get("product", {})
    health_color = "#78d9ae" if product.get("overall") == "READY" else "#ffad42"
    txt((1440, 42), f"ÉTAT : {product.get('health', 'PRÊT')}", 22, health_color, True, 410)
    txt((1440, 78), product.get("version") or "", 18, "#a9bdd1", False, 410)

    if not model.get("available"):
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
                ("Instantané", "À actualiser" if model.get("stale") else "À jour", None),
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
                ("Graphiques", f"{o['gpu']} • {o['graphics']}", None),
                ("Affichage", o["display"], None),
            ],
        )
        card(
            (70, 480, 860, 360),
            "ÉTAT OPENHTPC",
            [
                ("Santé globale", product.get("health", "PRÊT"), health_color),
                ("Instantané", "À actualiser" if model.get("stale") else "À jour", None),
                ("Généré le", model.get("generated_at"), None),
            ],
        )
        p = model["processing"]
        card(
            (960, 480, 890, 360),
            "TRAITEMENT VIDÉO",
            [
                ("Profil actuel", p["profile"], None),
                ("Sortie", p["output"], None),
                ("Benchmark de rendu", p["benchmark"], None),
                ("Recommandation", p["recommendation"], None),
            ],
        )
    elif page == "codecs":
        x, y, w, h = 70, 170, 1780, 680
        draw.rounded_rectangle(
            (xy(x), xy(y), xy(x + w), xy(y + h)),
            radius=xy(24),
            fill="#071426",
            outline="#168fbd",
            width=max(2, xy(2)),
        )
        txt((x + 28, y + 22), "COMPATIBILITÉ ET VALIDATION DES CODECS VIDÉO", 24, "#22c7ff", True)
        for pos, label in ((x + 480, "LOGICIEL"), (x + 780, "MATÉRIEL"), (x + 1120, "LECTURE VALIDÉE")):
            txt((pos, y + 70), label, 18, "#93a9c2", True)
        codec_list = model.get("codecs") or model.get("display", {}).get("codecs", [])
        for index, item in enumerate(codec_list):
            yy = y + 118 + index * 76
            txt((x + 28, yy), item["name"], 22, "#f7fbff", True, 420)
            txt((x + 480, yy), item["software"], 19, "#d8e5f1", False, 260)
            txt((x + 780, yy), item["hardware"], 19, "#d8e5f1", False, 300)
            val_color = "#78d9ae" if item["validated"] == "Validé" else "#a9bdd1"
            txt((x + 1120, yy), item["validated"], 19, val_color, True, 220)
            if item.get("detail"):
                txt((x + 1370, yy + 2), item["detail"], 16, "#829bb5", False, 380)
    elif page == "display":
        d = model["display"]
        card(
            (70, 170, 860, 680),
            "AFFICHAGE ACTIF",
            [
                ("Sortie active", d["connector"], None),
                ("Résolution", d["resolution"], None),
                ("Fréquence", d["refresh"], None),
                ("Échelle KDE", d["scale"], None),
                ("Profondeur de couleur", d["depth"], None),
            ],
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
                ("Gestionnaire de session", "Wayland (KWin)", None),
                ("Résolveur de capacités", "Phase A Canonical Resolver", None),
                ("Modes de rafraîchissement", "Prise en charge automatique", None),
            ],
        )
    elif page == "audio":
        a = model.get("audio_section") or model.get("audio_media") or {}
        card(
            (70, 170, 860, 680),
            "SORTIE AUDIO",
            [
                ("Sortie active", a.get("audio_output"), None),
                ("Serveur audio", a.get("audio_backend"), None),
                ("Type de connexion", a.get("connection"), None),
                ("Canaux actifs", a.get("channels"), None),
            ],
        )
        card(
            (960, 170, 890, 680),
            "PASSTHROUGH & CONFIGURATION",
            [
                ("Passthrough numérique", a.get("passthrough"), None),
                ("Contrôle du volume", "Géré par PipeWire", None),
                ("Gestionnaire de flux", "PipeWire / WirePlumber", None),
            ],
        )
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
        p = model.get("processing", {})
        vp = model.get("video_profile", {})
        active_vp = vp.get("active") or p.get("active_video_profile") or "PURE"
        map_present = vp.get("map_present") if "map_present" in vp else p.get("map_present", False)
        map_stale = vp.get("map_stale") if "map_stale" in vp else p.get("map_stale", False)
        decision = vp.get("decision") or p.get("decision") or "PURE"
        cal_ui_status = vp.get("cal_ui_status") or p.get("cal_ui_status")

        # Top card: PROFIL ACTIF
        profile_color = "#78d9ae" if active_vp == "PURE" else "#22c7ff"
        if active_vp == "PURE":
            badge_text = "PURE (Actif)"
            desc_text = "Image de référence directe, sans traitement vidéo additionnel."
        elif map_present and not map_stale:
            badge_text = "CINÉMA AUTO (Actif — Prêt)"
            desc_text = "OPENHTPC adapte automatiquement le rendu au matériel et au contenu."
        elif not map_present:
            badge_text = "CINÉMA AUTO (Configuration requise)"
            profile_color = "#ffad42"
            desc_text = "Une courte analyse locale du matériel est nécessaire pour activer ce mode."
        else:
            badge_text = "CINÉMA AUTO (Recalibration requise)"
            profile_color = "#ffad42"
            desc_text = "L'affichage ou le matériel a changé ; une recalibration est nécessaire."

        # Top card container (1780 wide x 270 high)
        draw.rounded_rectangle(
            (xy(70), xy(170), xy(1850), xy(440)),
            radius=xy(24),
            fill="#071426",
            outline="#168fbd",
            width=max(2, xy(2)),
        )
        txt((98, 192), "TRAITEMENT VIDÉO — PROFIL SÉLECTIONNÉ", 24, "#22c7ff", True)
        txt((98, 240), "Profil actif", 18, "#93a9c2", False)
        txt((240, 236), badge_text, 24, profile_color, True)
        txt((98, 288), "Description", 18, "#93a9c2", False)
        txt((240, 286), desc_text, 20, "#f4f8ff", False)

        # Decision line
        if map_present and not map_stale:
            scope_line = f"Périmètre DVD cinéma PAL (576p) : Rendu automatique — {decision}"
            scope_col = "#78d9ae" if decision == "PURE" else "#22c7ff"
        elif not map_present:
            scope_line = "Périmètre DVD cinéma PAL (576p) : Repli certifié PURE"
            scope_col = "#ffad42"
        else:
            scope_line = "Périmètre DVD cinéma PAL (576p) : Repli certifié PURE (recalibration requise)"
            scope_col = "#ffad42"
        txt((98, 336), "Résolution", 18, "#93a9c2", False)
        txt((240, 334), scope_line, 19, scope_col, False)

        txt((98, 384), "Fidélité", 18, "#93a9c2", False)
        txt((240, 382), "Mode PURE permanent en cas d'absence d'analyse ou d'instabilité.", 18, "#93a9c2", False)

        # Left bottom card: PROFILS (860 x 400)
        draw.rounded_rectangle(
            (xy(70), xy(470), xy(930), xy(870)),
            radius=xy(24),
            fill="#071426",
            outline="#168fbd",
            width=max(2, xy(2)),
        )
        txt((98, 492), "MODES DE RESTITUTION", 22, "#22c7ff", True)

        # PURE section
        txt((98, 540), "PURE (Mode de référence)", 20, "#78d9ae" if active_vp == "PURE" else "#f4f8ff", True)
        txt((98, 574), "Image directe sans shader ni artifice. Stabilité absolue.", 17, "#b8cce0", False)
        txt((98, 604), "Préservation intégrale du signal d'origine.", 16, "#8298b0", False)

        # Separator line
        draw.line((xy(98), xy(644), xy(900), xy(644)), fill="#12304d", width=1)

        # CINEMA AUTO section
        txt((98, 664), "CINÉMA AUTO (Mode adaptatif)", 20, "#22c7ff" if active_vp == "CINEMA_AUTO" else "#f4f8ff", True)
        txt((98, 698), "Choisit automatiquement le rendu le plus qualifié et stable.", 17, "#b8cce0", False)
        txt((98, 728), "Analyse 100% locale, sans terminal ni compte requis.", 16, "#8298b0", False)

        # Right bottom card: ETAT & ACTIONS (890 x 400)
        draw.rounded_rectangle(
            (xy(960), xy(470), xy(1850), xy(870)),
            radius=xy(24),
            fill="#071426",
            outline="#168fbd",
            width=max(2, xy(2)),
        )
        txt((988, 492), "ACTIONS & NAVIGATION", 22, "#22c7ff", True)

        if not map_present:
            if cal_ui_status == "FAILED":
                txt((988, 542), "Dernière analyse", 18, "#93a9c2", False)
                txt((1220, 540), "Interrompue ou incomplète", 20, "#ffad42", True)
                txt((988, 592), "État système", 18, "#93a9c2", False)
                txt((1220, 590), "PURE reste actif en sécurité", 20, "#78d9ae", False)
                txt((988, 642), "Action", 18, "#93a9c2", False)
                txt((1220, 640), "RÉESSAYER L'ANALYSE ci-dessous", 20, "#22c7ff", True)
            else:
                txt((988, 542), "Analyse matérielle", 18, "#93a9c2", False)
                txt((1220, 540), "Non effectuée", 20, "#ffad42", True)
                txt((988, 592), "Action requise", 18, "#93a9c2", False)
                txt((1220, 590), "CONFIGURER CINÉMA AUTO", 20, "#22c7ff", True)
                txt((988, 642), "Durée estimée", 18, "#93a9c2", False)
                txt((1220, 640), "Quelques dizaines de secondes", 19, "#f4f8ff", False)
        elif map_stale:
            txt((988, 542), "Analyse matérielle", 18, "#93a9c2", False)
            txt((1220, 540), "Obsolète (affichage modifié)", 20, "#ffad42", True)
            txt((988, 592), "Action requise", 18, "#93a9c2", False)
            txt((1220, 590), "RECALIBRER ci-dessous", 20, "#22c7ff", True)
            txt((988, 642), "Sécurité", 18, "#93a9c2", False)
            txt((1220, 640), "Repli PURE appliqué automatiquement", 19, "#78d9ae", False)
        else:
            txt((988, 542), "Analyse matérielle", 18, "#93a9c2", False)
            txt((1220, 540), "À jour et opérationnelle", 20, "#78d9ae", True)
            txt((988, 592), "Choix DVD PAL", 18, "#93a9c2", False)
            txt((1220, 590), f"Rendu {decision}", 20, "#22c7ff", True)
            txt((988, 642), "Changer de profil", 18, "#93a9c2", False)
            next_action = "UTILISER PURE" if active_vp == "CINEMA_AUTO" else "UTILISER CINÉMA AUTO"
            txt((1220, 640), f"{next_action} ci-dessous", 19, "#f4f8ff", False)

        # Navigation row
        draw.line((xy(988), xy(710), xy(1820), xy(710)), fill="#12304d", width=1)
        txt((988, 730), "Navigation", 18, "#93a9c2", False)
        txt((1220, 728), "Entrée : Valider  |  Échap : Retour", 19, "#93a9c2", False)
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
        for pos, label in ((x + 440, "LOGICIEL"), (x + 675, "MATÉRIEL"), (x + 930, "LECTURE")):
            txt((pos, y + 70), label, 17, "#93a9c2", True)
        for index, item in enumerate(d.get("codecs", [])):
            yy = y + 116 + index * 72
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
                ("Pilote Vulkan", t["vulkan_driver"], None),
                ("Pilote VA-API", t["vaapi_driver"], None),
                ("Version MPV", t["mpv"], None),
                ("Version FFmpeg", t["ffmpeg"], None),
            ],
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
