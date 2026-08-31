#!/usr/bin/env python3
"""Stable, side-effect-free Core facts offered to bounded P2 observers."""
from __future__ import annotations
from typing import Any

PROTECTED_OPTICAL_FIELDS=("media_family","exact_type","protection","protection_mechanism",
                          "classification_source","provider_state","playback_state","last_attempt")

def protected_optical_observation(optical:dict[str,Any]|None,capability:dict[str,Any]|None,
                                  last_attempt:dict[str,Any]|None,playback:dict[str,Any]|None)->dict[str,str]:
 optical=optical if isinstance(optical,dict) else {};capability=capability if isinstance(capability,dict) else {}
 canonical=optical.get("canonical_state","UNKNOWN")
 family="BLURAY" if canonical in {"BLURAY_VIDEO","UHD_BLURAY_VIDEO","BLURAY_FAMILY"} else "DVD" if canonical=="DVD_VIDEO" else "NONE"
 exact={"BLURAY_VIDEO":"BLURAY","UHD_BLURAY_VIDEO":"UHD_BLURAY"}.get(canonical,"UNKNOWN")
 mechanisms=optical.get("protection_mechanisms") if isinstance(optical.get("protection_mechanisms"),list) else []
 provider=capability.get("status","NOT_AVAILABLE");playback=playback if isinstance(playback,dict) else {}
 return {"media_family":family,"exact_type":exact,"protection":optical.get("protection","UNKNOWN") if family=="BLURAY" else "UNKNOWN",
         "protection_mechanism":"+".join(mechanisms) if mechanisms else "UNKNOWN",
         "classification_source":optical.get("classification_source","UNKNOWN") if family=="BLURAY" else "UNKNOWN",
         "provider_state":provider,"playback_state":playback.get("playback_action","UNKNOWN"),
         "last_attempt":last_attempt.get("status","UNKNOWN") if isinstance(last_attempt,dict) else "UNKNOWN"}
