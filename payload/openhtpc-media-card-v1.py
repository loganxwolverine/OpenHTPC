# Copyright 2026 Steve Dehanne
# SPDX-License-Identifier: Apache-2.0
"""Safe cached movie card projection. No network, filesystem, DB or playback side effects.

Provenance:
  - genres, credits, rating: the *identified film* (TMDb movie snapshot).
  - video/color/audio: this particular *local resource* (ffprobe/DB).
Never convert a movie's theatrical mastering into a claim about the MKV.
"""
from __future__ import annotations
import json
import math
import re
from typing import Any

MAX_FACT_UTF8 = 176
MAX_CAST = 3

def _text(value: Any, max_length: int = 100) -> str:
    if not isinstance(value,str):
        return ""
    clean=" ".join(value.replace(";", ",").split())
    clean="".join(c for c in clean if c.isprintable() and c not in "=\r\n")
    return clean[:max_length].strip()

def _bounded(name: str, text: str) -> str:
    if not text:
        return ""
    result=_text(text,200)
    while len(f"{name}={result}".encode("utf-8"))>MAX_FACT_UTF8 and result:
        result=result[:-1].rstrip()
    return f"{name}={result}" if result else ""

def cached_details(presentation: dict | None) -> dict:
    """Only consume the authenticated snapshot already belonging to identified work."""
    if not isinstance(presentation,dict):
        return {}
    raw=presentation.get("payload_json")
    if not isinstance(raw,str) or len(raw)>300_000:
        return {}
    try:
        obj=json.loads(raw)
    except (ValueError,TypeError):
        return {}
    if not isinstance(obj,dict):
        return {}
    return obj

def film_facts(presentation: dict | None) -> list[str]:
    """Exactly four stable fields. Absences are honest and unambiguous."""
    payload=cached_details(presentation)
    if not payload:
        return []
    source_genres=payload.get("genres")
    genres=[]
    if isinstance(source_genres,list):
        for g in source_genres[:12]:
            name=_text(g.get("name"),28) if isinstance(g,dict) else _text(g,28)
            if name and name.casefold() not in {n.casefold() for n in genres}:
                genres.append(name)
    genre=" · ".join(genres[:4]) if genres else "Non renseigné"

    rating=payload.get("vote_average")
    votes=payload.get("vote_count")
    if isinstance(rating,(float,int)) and not isinstance(rating,bool) and math.isfinite(rating) and 0<=rating<=10 and isinstance(votes,int) and not isinstance(votes,bool) and votes>0:
        score=f"{rating:.1f}/10"
    else:
        score="Non renseignée"
    credits=payload.get("credits")
    directors=[]
    cast=[]
    if isinstance(credits,dict):
        crew=credits.get("crew")
        if isinstance(crew,list):
            for person in crew[:300]:
                if not isinstance(person,dict) or person.get("job")!="Director":
                    continue
                name=_text(person.get("name"),70)
                if name and name not in directors:directors.append(name)
        members=credits.get("cast")
        if isinstance(members,list):
            eligible=[x for x in members[:300] if isinstance(x,dict)]
            eligible.sort(key=lambda p:p.get("order") if type(p.get("order")) is int and p.get("order")>=0 else 999999)
            for person in eligible:
                name=_text(person.get("name"),70)
                if name and name not in cast:cast.append(name)
                if len(cast)==MAX_CAST:break
    return [
        _bounded("Fact1","GENRES  "+" · ".join(genres[:4]) if genres else "GENRES  Non renseignés"),
        _bounded("Fact2","NOTE TMDB  "+score),
        _bounded("Fact3","RÉALISATION  "+(" · ".join(directors[:2]) if directors else "Non renseignée")),
        _bounded("Fact4","CASTING  "+(" · ".join(cast) if cast else "Non renseigné")),
    ]

def source_color(technical:dict|None) -> str:
    if not isinstance(technical,dict):
        return "Indéterminée"
    fmt=_text(technical.get("hdr_format"),50).casefold()
    transfer=_text(technical.get("color_transfer"),50).casefold()
    primaries=_text(technical.get("color_primaries"),50).casefold()
    if fmt=="dolby vision":
        profile=technical.get("dolby_vision_profile")
        suffix=f" · Profil {profile}" if type(profile) is int and 1<=profile<=15 else ""
        return "Dolby Vision"+suffix
    if fmt=="hdr10+":return "HDR10+"
    if fmt=="hdr10":return "HDR10"
    if fmt=="hlg" or transfer=="arib-std-b67":return "HLG"
    if transfer=="smpte2084":
        return "HDR10" if primaries=="bt2020" else "HDR (PQ, profil non précisé)"
    if transfer in ("bt709","smpte170m","bt470bg","iec61966-2-1"):
        return "SDR"
    return "Indéterminée"

def source_facts(technical:dict|None) -> list[str]:
    """Source format != monitor output/tone mapping. No HDR efficacy claim."""
    technical=technical if isinstance(technical,dict) else {}
    width,height=technical.get("width"),technical.get("height")
    resolution=f"{width}×{height}" if type(width) is int and type(height) is int and 0<width<=16384 and 0<height<=16384 else ""
    codec=_text(technical.get("video_codec"),25).upper()
    fps=technical.get("fps")
    rate=f"{fps:g} fps" if isinstance(fps,(float,int)) and not isinstance(fps,bool) and math.isfinite(fps) and 1<=fps<=240 else ""
    video=" · ".join(p for p in (resolution,codec) if p) or "Non renseignée"
    # Main card shows compact signal information at sofa distance.
    # Exact frame rate remains in the technical DB and existing fallback;
    # the primary card is not the full technical diagnostics panel.
    return [_bounded("Fact5","VIDÉO  "+video),
            _bounded("Fact6","COLORIMÉTRIE  "+source_color(technical))]

def all_facts(presentation:dict|None,technical:dict|None)->list[str]:
    return [line for line in film_facts(presentation)+source_facts(technical) if line]
