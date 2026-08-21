#!/usr/bin/env python3
"""Generate the complete cinematic DVD composition without opening a window."""
from __future__ import annotations
import argparse, hashlib, importlib.util, json, os, pathlib, re, textwrap
from PIL import Image, ImageDraw, ImageFont, ImageOps

VERSION="cinematic-v2"
def load(path,name):
 spec=importlib.util.spec_from_file_location(name,path); m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m
def safe_text(value,default=""):
 return str(value).replace("\x00","").strip() if value not in (None,"",[],{}) else default
def duration_text(value):
 if value in (None,"",[],{}): return ""
 if isinstance(value,(int,float)):
  val=float(value)
  if val<=0: return ""
  minutes=round(val/60) if val>300 else int(val)
  return f"{minutes//60} h {minutes%60:02d}" if minutes>=60 else f"{minutes} min"
 s=str(value).strip()
 if re.match(r"^\d+\s*h(?:\s*\d+)?$",s,re.I): return s
 m=re.match(r"^(\d+):(\d+):(\d+(?:\.\d+)?)$",s)
 if m:
  h,mn,sec=m.groups(); minutes=round(int(h)*60+int(mn)+float(sec)/60)
  return f"{minutes//60} h {minutes%60:02d}" if minutes>=60 else f"{minutes} min"
 m=re.match(r"^(\d+):(\d+(?:\.\d+)?)$",s)
 if m:
  mn,sec=m.groups(); minutes=round(int(mn)+float(sec)/60)
  return f"{minutes//60} h {minutes%60:02d}" if minutes>=60 else f"{minutes} min"
 try:
  val=float(s)
  if val>0:
   minutes=round(val/60) if val>300 else int(val)
   return f"{minutes//60} h {minutes%60:02d}" if minutes>=60 else f"{minutes} min"
 except ValueError: pass
 return safe_text(s)
def wrapped(value,width,lines):
 return textwrap.wrap(safe_text(value),width=width,break_long_words=False,break_on_hyphens=False,max_lines=lines,placeholder="…")
def cache_identity(state,metadata):
 value={"renderer":VERSION,"disc":state.get("disc_id") or state.get("ui_state_hash") or state.get("generation"),"metadata":metadata}
 return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,default=str).encode()).hexdigest()[:20]
def placeholder(size,font_path,title="DVD"):
 image=Image.new("RGB",size,"#071426"); d=ImageDraw.Draw(image); f=ImageFont.truetype(str(font_path),54)
 d.rounded_rectangle((4,4,size[0]-5,size[1]-5),radius=28,outline="#20c8ff",width=5)
 d.ellipse((size[0]//2-82,size[1]//2-125,size[0]//2+82,size[1]//2+39),outline="#8ee7ff",width=8)
 d.polygon(((size[0]//2-18,size[1]//2-88),(size[0]//2+53,size[1]//2-43),(size[0]//2-18,size[1]//2+2)),fill="#ff9f1c")
 box=d.textbbox((0,0),title,font=f); d.text(((size[0]-box[2])/2,size[1]-115),title,font=f,fill="#f4f8ff")
 return image
def poster_image(path,size,font_path,allowed_roots=()):
 try:
  if not path: raise ValueError
  candidate=pathlib.Path(path).resolve()
  if allowed_roots and not any(candidate.is_relative_to(root.resolve()) for root in allowed_roots): raise ValueError
  with Image.open(candidate) as image:
   image.load()
   if image.width<50 or image.height<80: raise ValueError
   return ImageOps.fit(image.convert("RGB"),size,method=Image.Resampling.LANCZOS,centering=(.5,.5))
 except (OSError,ValueError,TypeError): return placeholder(size,font_path)

# Media-type profiles — logo key: physical-media logo asset for poster overlay.
# None = fall back to textual pill badge. Future Blu-ray/UHD logos drop in here.
MEDIA_PROFILES = {
    "DVD":    {"badge": "DVD VIDÉO",       "icon": "assets/ui/optical-dvd.png",    "logo": "assets/ui/logodvd.png", "label": "DVD"},
    "BLURAY": {"badge": "BLU-RAY",         "icon": "assets/ui/optical-bluray.png", "logo": None,                    "label": "Blu-ray"},
    "UHD":    {"badge": "4K UHD BLU-RAY",  "icon": "assets/ui/optical-uhd.png",   "logo": None,                    "label": "UHD Blu-ray"},
}

# ─── Task A: Physical-media logo overlay — top-right corner of poster ────────
#
# Poster geometry: origin (90,185) size 430×645
#   right edge: x=520  top edge: y=185
# Logo: scaled to LOGO_W wide, anchored to top-right corner with a slight
# outward bleed so it visually clings to the frame corner.
_LOGO_W   = 115                   # width in px — smaller than previous version
_LOGO_AR  = 1299 / 709            # source aspect ratio (1299×709)
_LOGO_H   = round(_LOGO_W / _LOGO_AR)   # ≈ 63 px
_LOGO_PAD = 7
# Top-right: right edge bleeds 18 px outside poster, top edge 10 px above poster
_LOGO_X   = 520 - _LOGO_W + 18   # = 423
_LOGO_Y   = 185 - 10             # = 175

def _draw_logo_overlay(base, install, media_prof):
    """Composite the physical-media logo onto the TOP-RIGHT of the poster frame.
    Returns updated RGBA base on success, False to trigger textual fallback."""
    logo_rel = media_prof.get("logo")
    if not logo_rel:
        return False
    logo_path = install / logo_rel
    if not logo_path.is_file():
        return False
    try:
        with Image.open(logo_path) as src:
            src.load()
            # Source is black-on-transparent RGBA.
            # Invert RGB channels → white logo; preserve original alpha.
            logo_rgba = src.convert("RGBA")
            r, g, b, a = logo_rgba.split()
            inv = r.point(lambda v: 255 - v)
            logo_white = Image.merge("RGBA", (inv, inv, inv, a))
            logo_scaled = logo_white.resize((_LOGO_W, _LOGO_H), Image.Resampling.LANCZOS)

        # 1. Soft drop shadow (+4/+4 offset, rounded)
        shadow = Image.new("RGBA", base.size, (0, 0, 0, 0))
        ImageDraw.Draw(shadow, "RGBA").rounded_rectangle(
            (_LOGO_X - _LOGO_PAD + 4, _LOGO_Y - _LOGO_PAD + 4,
             _LOGO_X + _LOGO_W + _LOGO_PAD + 4, _LOGO_Y + _LOGO_H + _LOGO_PAD + 4),
            radius=12, fill=(0, 0, 0, 145))
        base = Image.alpha_composite(base, shadow)

        # 2. Dark glass backing panel
        ImageDraw.Draw(base, "RGBA").rounded_rectangle(
            (_LOGO_X - _LOGO_PAD, _LOGO_Y - _LOGO_PAD,
             _LOGO_X + _LOGO_W + _LOGO_PAD, _LOGO_Y + _LOGO_H + _LOGO_PAD),
            radius=12, fill=(2, 12, 28, 218), outline=(34, 199, 255, 70), width=1)

        # 3. Paste white logo with its own alpha mask
        base.paste(logo_scaled, (_LOGO_X, _LOGO_Y), logo_scaled)
        return base
    except Exception:
        return False

# ─── Task B: Physical edition block helpers ───────────────────────────────────

def _render_physical_edition(d, phys, font, y_start, x=585, max_y=858):
    """Draw the ÉDITION PHYSIQUE block into the draw context.
    Space-aware: stops gracefully when max_y is reached.
    Returns next y position."""
    if not phys or not phys.get("lsdvd_ok"):
        return y_start
    y = y_start
    if y + 50 > max_y:   # minimum space check (header + 1 line)
        return y_start

    # Subtle horizontal rule
    d.line([(x, y), (x + 860, y)], fill=(34, 199, 255, 55), width=1)
    y += 10

    d.text((x, y), "ÉDITION PHYSIQUE", font=font(20), fill="#22c7ff")
    y += 28

    # Video spec line: DVD-VIDEO · PAL · 720×576 · 25 fps · MPEG-2 · 16/9
    vid = phys.get("video", {})
    vparts = ["DVD-VIDEO"]
    if vid.get("format"):
        vparts.append(vid["format"])
    if vid.get("width") and vid.get("height"):
        vparts.append(f"{vid['width']}×{vid['height']}")
    if vid.get("fps"):
        fps_str = str(vid["fps"]).rstrip("0").rstrip(".") if "." in str(vid["fps"]) else str(vid["fps"])
        vparts.append(f"{fps_str} fps")
    if vid.get("codec"):
        vparts.append(vid["codec"])
    elif vid:
        vparts.append("MPEG-2")
    if vid.get("aspect"):
        vparts.append(vid["aspect"])
    if y + 24 <= max_y:
        d.text((x, y), "  ·  ".join(vparts), font=font(20), fill="#b8d8ee")
        y += 26

    # Audio tracks
    for track in (phys.get("audio") or [])[:3]:
        if y + 22 > max_y: break
        lang  = track.get("display_lang", "")
        codec = track.get("display_codec", "")
        ch    = track.get("display_channels", "")
        line  = "   ".join(p for p in (lang, codec, ch) if p)
        if line:
            d.text((x + 16, y), line, font=font(20), fill="#dceaf5")
            y += 24

    # Subtitle languages (single compact row)
    subs = phys.get("subtitles") or []
    sub_langs = [s.get("display_lang", "") for s in subs[:6] if s.get("display_lang")]
    if sub_langs and y + 22 <= max_y:
        d.text((x, y), "SOUS-TITRES   " + "   /   ".join(sub_langs), font=font(20), fill="#dceaf5")
        y += 24

    # Chapters and title duration
    chapters = phys.get("chapters")
    dur = phys.get("duration")
    dur_str = duration_text(dur) if dur else ""
    bits = []
    if chapters:
        bits.append(f"CHAPITRES   {chapters}")
    if dur_str:
        bits.append(f"DURÉE DU TITRE   {dur_str}")
    if bits and y + 22 <= max_y:
        d.text((x, y), "   •   ".join(bits), font=font(20), fill="#dceaf5")
        y += 24

    return y

# ─── Main render ─────────────────────────────────────────────────────────────

def render(home,install,state,metadata,target):
 font_path=install/"flex/assets/fonts/OpenSans-Regular.ttf"
 def font(n): return ImageFont.truetype(str(font_path),n)
 wallpaper=install/"assets/branding/openhtpc-wallpaper.png"
 try:
  with Image.open(wallpaper) as source: base=ImageOps.fit(source.convert("RGB"),(1920,1080),method=Image.Resampling.LANCZOS)
 except OSError: base=Image.new("RGB",(1920,1080),"#020711")
 shade=Image.new("RGBA",base.size,(0,5,14,178)); base=Image.alpha_composite(base.convert("RGBA"),shade); d=ImageDraw.Draw(base,"RGBA")
 status=metadata.get("status")
 is_committed=(status=="PASS")
 if status=="AMBIGUOUS":
  title=safe_text(state.get("disc_title") or state.get("volume_label") or metadata.get("query"),"DVD identifié")
 else:
  title=safe_text(metadata.get("title") or state.get("tmdb_title") or state.get("disc_title") or state.get("volume_label") or metadata.get("query"),"DVD identifié")
 # Poster: (90,185) 430×645; frame outline. Never show uncommitted candidate poster.
 poster_path=metadata.get("poster_file") if is_committed else None
 poster=poster_image(poster_path,(430,645),font_path,(home/".cache/openhtpc/tmdb",home/".local/share/openhtpc/media-cache"))
 base.paste(poster,(90,185)); d.rounded_rectangle((84,179,526,836),radius=22,outline="#22c7ff",width=4)
 media_type = state.get("state","DVD")
 media_prof = MEDIA_PROFILES.get(media_type, MEDIA_PROFILES["DVD"])
 # Physical-media logo overlay — top-right corner of poster
 result=_draw_logo_overlay(base,install,media_prof)
 logo_drawn=False
 if result is not False:
  base=result; d=ImageDraw.Draw(base,"RGBA"); logo_drawn=True
 d.text((82,55),"OPENHTPC",font=font(36),fill="#f5f8ff")
 title_size=68 if len(title)<=30 else 56 if len(title)<=52 else 46
 title_lines=wrapped(title,34 if title_size>55 else 44,2)
 for i,line in enumerate(title_lines): d.text((585,150+i*(title_size+5)),line,font=font(title_size),fill="#ffffff")
 y=150+len(title_lines)*(title_size+5)+12
 # Textual fallback badge (only when logo asset is unavailable)
 if not logo_drawn:
  badge_text=media_prof["badge"]; badge_font=font(20); bbox=d.textbbox((0,0),badge_text,font=badge_font)
  text_w=bbox[2]-bbox[0]; badge_w=40+text_w+16
  d.rounded_rectangle((585,y,585+badge_w,y+36),radius=8,fill=(1,18,38,220),outline="#22c7ff",width=2)
  badge_ico=install/media_prof["icon"]
  if badge_ico.is_file():
   try:
    with Image.open(badge_ico) as bi:
     bir=ImageOps.fit(bi.convert("RGBA"),(24,24),method=Image.Resampling.LANCZOS)
     base.paste(bir,(593,y+6),bir)
   except Exception: pass
  d.text((625,y+6),badge_text,font=badge_font,fill="#82dfff")
 # Year • Duration row
 bits=[]
 year=safe_text(metadata.get("year") or safe_text(metadata.get("release_date"))[:4]) if is_committed else ""
 local_duration=duration_text(state.get("duration") or metadata.get("local_duration"))
 tmdb_duration=duration_text(metadata.get("runtime")) if is_committed else ""
 if year: bits.append(year)
 if local_duration or tmdb_duration: bits.append(local_duration or tmdb_duration)
 if bits: d.text((585,y+3),"  •  ".join(bits),font=font(27),fill="#8ee7ff")
 y+=50; genres=(metadata.get("genres") or []) if is_committed else []
 if genres: d.text((585,y)," • ".join(map(str,genres[:4])),font=font(26),fill="#dceaf5"); y+=46
 tagline=safe_text(metadata.get("tagline")) if is_committed else ""
 if tagline: d.text((585,y),tagline,font=font(26),fill="#ffba69"); y+=54
 overview=safe_text(metadata.get("overview")) if is_committed else ""
 has_token=(home/".config/openhtpc/secrets/tmdb-token").is_file()
 if overview:
  section="SYNOPSIS"
 elif status=="AMBIGUOUS":
  section="PLUSIEURS FILMS CORRESPONDENT"
  overview="Plusieurs films correspondent à ce titre. Choisissez votre version avec ▲ ▼ et confirmez avec Entrée :"
 elif status=="PENDING":
  section="RECHERCHE TMDb"
  overview="Recherche des métadonnées TMDb en cours… La lecture locale reste disponible."
 elif status=="AUTH_FAILED":
  section="SERVICE TMDb"
  overview="Authentification TMDb refusée. Vérifiez votre clé ou jeton TMDb dans les paramètres. La lecture locale reste disponible."
 elif status in {"NETWORK_FAILED","QUERY_FAILED","UNAVAILABLE"}:
  section="SERVICE TMDb"
  overview="Service TMDb momentanément indisponible. La lecture locale reste disponible."
 elif status in {"NO_RESULT","NO_CONFIDENT_MATCH"}:
  section="INFORMATIONS TMDb"
  overview="Aucun résultat trouvé sur TMDb pour ce titre. La lecture locale reste disponible."
 else:
  section="ENRICHIR CETTE FICHE"
  overview=("Connectez OPENHTPC à TMDb pour récupérer automatiquement l’affiche, le synopsis, l’année, les genres et les principaux acteurs. TMDb est facultatif : vous pouvez lire vos DVD sans ce service." if not has_token else
            "Recherche des métadonnées TMDb en cours… La lecture locale reste disponible.")
 d.text((585,y),section,font=font(24),fill="#22c7ff"); y+=36
 if status=="AMBIGUOUS":
  d.text((585,y),overview,font=font(20),fill="#dceaf5"); y+=32
 else:
  for line in wrapped(overview,72,5): d.text((585,y),line,font=font(25),fill="#edf4fa"); y+=34
 y=max(y+16,630)
 credits=[("RÉALISATION",metadata.get("director")),("SCÉNARIO",", ".join(metadata.get("writers") or [])),("AVEC",", ".join((metadata.get("cast") or [])[:4]))] if is_committed else []
 for label,value in credits:
  if value and y+34<=790: d.text((585,y),label,font=font(19),fill="#84dfff"); d.text((760,y),safe_text(value),font=font(21),fill="#f0f5fa"); y+=34
 # Physical edition block — rendered from lsdvd data embedded in optical state
 phys=state.get("physical_edition")
 y=_render_physical_edition(d,phys,font,y+10,x=585,max_y=858)
 d.rounded_rectangle((55,905,1865,1045),radius=30,fill=(1,8,19,205),outline="#178fbd",width=3)
 d.text((90,858),"ENTRÉE : sélectionner   •   ÉCHAP / RETOUR ARRIÈRE : accueil",font=font(19),fill="#9fb6c8")
 target.parent.mkdir(parents=True,exist_ok=True); temp=target.with_suffix(".tmp.png"); base.convert("RGB").save(temp,"PNG",optimize=True); os.chmod(temp,0o600); os.replace(temp,target)
 return {"title":title,"cache_identity":cache_identity(state,metadata),"target":str(target),"metadata_status":metadata.get("status","NOT_CONFIGURED")}
def metadata_for(home,install,state,enrich=False):
 title=safe_text(state.get("tmdb_title") or state.get("disc_title") or state.get("volume_label"),"DVD")
 tmdb=load(install/"openhtpc-tmdb.py","disc_tmdb")
 data=tmdb.disc_metadata(home,state,title,enrich=enrich); poster=tmdb.poster(home,data) if data.get("status")=="PASS" else None
 if poster: data["poster_file"]=str(poster)
 return data
def main():
    p = argparse.ArgumentParser()
    p.add_argument("--home", type=pathlib.Path)
    p.add_argument("--enrich", action="store_true")
    p.add_argument("--disc-id", type=str)
    p.add_argument("--generation", type=int)
    a = p.parse_args()
    home = a.home or pathlib.Path(os.environ.get("OPENHTPC_HOME", pathlib.Path.home()))
    install = pathlib.Path(os.environ.get("OPENHTPC_INSTALL_DIR", home / ".local/lib/openhtpc"))
    try:
        state = json.loads((home / ".local/state/openhtpc/optical-current.json").read_text())
    except (OSError, json.JSONDecodeError):
        state = {"state": "EMPTY", "generation": 0}

    # If launched for a specific disc_id or generation, verify state still matches before doing work
    if a.disc_id and str(state.get("disc_id") or "") != a.disc_id:
        return 0
    if a.generation is not None and int(state.get("generation", 0) or 0) != a.generation:
        return 0

    meta = metadata_for(home, install, state, a.enrich)

    # Re-verify latest optical state hasn't changed before writing disc-sheet.png
    try:
        latest = json.loads((home / ".local/state/openhtpc/optical-current.json").read_text())
        if a.disc_id and str(latest.get("disc_id") or "") != a.disc_id:
            return 0
        if a.generation is not None and int(latest.get("generation", 0) or 0) != a.generation:
            return 0
    except (OSError, json.JSONDecodeError):
        pass

    target = home / ".cache/openhtpc/disc-sheet.png"
    print(json.dumps(render(home, install, state, meta, target), ensure_ascii=False))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
