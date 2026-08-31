#!/usr/bin/env python3
"""Read-only protected-optical P2 shadow adapter."""
from __future__ import annotations
from typing import Any

PLUGIN_ID="plugin.bluray"
CLAIMED_FIELDS=("media_family","exact_type","protection","protection_mechanism",
                "classification_source","provider_state","playback_state","last_attempt")
DECLARED_MEDIA_CAPABILITIES=("bluray","uhd_bluray","protected_optical")

def observe(core_observation:dict[str,Any])->dict[str,Any]:
 if not isinstance(core_observation,dict) or set(core_observation)!=set(CLAIMED_FIELDS):raise ValueError("SHADOW_INPUT_INVALID")
 if any(not isinstance(core_observation[field],str) for field in CLAIMED_FIELDS):raise ValueError("SHADOW_INPUT_INVALID")
 return {"plugin_id":PLUGIN_ID,"plugin_state":"SHADOW",
         **{"observed_"+field:core_observation[field] for field in CLAIMED_FIELDS}}

def equivalent(core_observation:dict[str,Any],shadow_observation:dict[str,Any])->bool:
 return all(shadow_observation.get("observed_"+field)==core_observation.get(field) for field in CLAIMED_FIELDS)

def doctor_rows(inputs:dict[str,Any])->list[dict[str,Any]]:
 protected=inputs.get("protected") if isinstance(inputs.get("protected"),dict) else {}
 dependencies=protected.get("dependencies") if isinstance(protected.get("dependencies"),dict) else {}
 key_database=protected.get("external_key_database") if isinstance(protected.get("external_key_database"),dict) else {}
 rows=[
  {"label":"Protected optical media","status":protected.get("status","NOT_CONFIGURED"),"blocking":protected.get("status")=="BLOCKED"},
  {"label":"libbluray","status":(dependencies.get("libbluray") or {}).get("status","NOT_AVAILABLE"),"blocking":False},
  {"label":"libaacs","status":(dependencies.get("libaacs") or {}).get("status","NOT_AVAILABLE"),"blocking":False},
  {"label":"libbdplus","status":(dependencies.get("libbdplus") or {}).get("status","NOT_AVAILABLE"),"blocking":False},
  {"label":"External key database","status":key_database.get("status","NOT_CONFIGURED"),"blocking":False},
  {"label":"Protected optical playback","status":"ENABLED" if protected.get("status")=="AVAILABLE" else "DISABLED","blocking":False},
 ]
 optical=inputs.get("optical") if isinstance(inputs.get("optical"),dict) else {};canonical=optical.get("canonical_state","UNKNOWN")
 if canonical in {"BLURAY_VIDEO","UHD_BLURAY_VIDEO","BLURAY_FAMILY"}:
  rows.extend([
   {"label":"Optical media family","status":"BLURAY","blocking":False},
   {"label":"Optical exact type","status":{"BLURAY_VIDEO":"BLURAY","UHD_BLURAY_VIDEO":"UHD_BLURAY"}.get(canonical,"UNKNOWN"),"blocking":False},
   {"label":"Optical protection","status":optical.get("protection","UNKNOWN"),"blocking":False},
   {"label":"Protection mechanism","status":"+".join(optical.get("protection_mechanisms") or ["UNKNOWN"]),"blocking":False},
   {"label":"Classification source","status":optical.get("classification_source","UNKNOWN"),"blocking":False},
  ])
 attempt=inputs.get("last_attempt")
 if isinstance(attempt,dict):rows.append({"label":"Last protected disc attempt","status":attempt.get("status","UNKNOWN"),"blocking":False})
 return rows

def presentation_descriptor(optical:dict[str,Any])->dict[str,Any]:
 canonical=optical.get("canonical_state","UNKNOWN") if isinstance(optical,dict) else "UNKNOWN"
 if canonical=="BLURAY_VIDEO":return {"owned":True,"presentation_key":"BLURAY","badge_key":"BLURAY","display_label":"BLU-RAY","media_kind":"BLURAY"}
 if canonical=="BLURAY_FAMILY":return {"owned":True,"presentation_key":"BLURAY_FAMILY","badge_key":"BLURAY","display_label":"BLU-RAY / UHD","media_kind":"BLURAY"}
 if canonical=="UHD_BLURAY_VIDEO":return {"owned":True,"presentation_key":"UHD_BLURAY","badge_key":"UHD_BLURAY","display_label":"ULTRA HD BLU-RAY 4K","media_kind":"BLURAY"}
 return {"owned":False,"presentation_key":"NONE","badge_key":"NONE","display_label":"","media_kind":"NONE"}

def capability_contribution(snapshot:dict[str,Any])->dict[str,Any]:
 snapshot=snapshot if isinstance(snapshot,dict) else {};raw=snapshot.get("status");states={"AVAILABLE","NOT_CONFIGURED","NOT_AVAILABLE","BLOCKED"}
 status="NOT_AVAILABLE" if not snapshot else raw if raw in states else "BLOCKED"
 dependencies=snapshot.get("dependencies") if isinstance(snapshot.get("dependencies"),dict) else {}
 dependency_states={name:(dependencies.get(name) or {}).get("status","NOT_AVAILABLE") for name in ("libbluray","libaacs","libbdplus")}
 key_database=snapshot.get("external_key_database") if isinstance(snapshot.get("external_key_database"),dict) else {};ready=status=="AVAILABLE"
 return {"capability_id":"PROTECTED_OPTICAL_SUPPORT","availability_state":status,"provider_state":status,
         "playback_capability_state":status,"available":ready,"ready_to_attempt":ready,
         "supported_media_kinds":["BLURAY","UHD_BLURAY"],"dependency_states":dependency_states,
         "external_key_database_state":key_database.get("status","NOT_CONFIGURED"),"blocking":status=="BLOCKED"}

def playback_decision(optical:dict[str,Any],snapshot:dict[str,Any])->dict[str,Any]:
 optical=optical if isinstance(optical,dict) else {};canonical=optical.get("canonical_state")
 if not canonical:canonical={"DVD":"DVD_VIDEO","BLURAY":"BLURAY_VIDEO","UHD":"UHD_BLURAY_VIDEO","EMPTY":"DRIVE_PRESENT_NO_MEDIA","NO_DRIVE":"NO_OPTICAL_DRIVE","UNKNOWN_DISC":"UNKNOWN_OPTICAL_MEDIA"}.get(optical.get("state"),"DETECTION_INDETERMINATE")
 protection=optical.get("protection","UNKNOWN");snapshot=snapshot if isinstance(snapshot,dict) else {};support=snapshot.get("status","NOT_AVAILABLE")
 dependencies=snapshot.get("dependencies") if isinstance(snapshot.get("dependencies"),dict) else {};bluray=(dependencies.get("libbluray") or {}).get("status","NOT_AVAILABLE")
 media_type={"DVD_VIDEO":"DVD","BLURAY_VIDEO":"BLURAY","BLURAY_FAMILY":"BLURAY","UHD_BLURAY_VIDEO":"UHD_BLURAY"}.get(canonical,"UNKNOWN");owned=canonical in {"BLURAY_VIDEO","UHD_BLURAY_VIDEO","BLURAY_FAMILY"}
 if canonical=="DVD_VIDEO":enabled,reason=True,"DVD_EXISTING_PATH"
 elif not owned:enabled,reason=False,"MEDIA_NOT_PLAYABLE"
 elif protection=="UNKNOWN":enabled,reason=False,"PROTECTION_UNKNOWN"
 elif protection=="UNPROTECTED" and bluray=="AVAILABLE":enabled,reason=True,"UNPROTECTED_MEDIA"
 elif protection=="UNPROTECTED":enabled,reason=False,"STRUCTURAL_SUPPORT_NOT_AVAILABLE"
 elif protection=="PROTECTED" and support=="AVAILABLE":enabled,reason=True,"PROTECTED_SUPPORT_AVAILABLE"
 elif protection=="PROTECTED":enabled,reason=False,f"PROTECTED_SUPPORT_{support}"
 else:enabled,reason=False,"PROTECTION_STATE_INVALID"
 return {"owned":owned,"media_type":media_type,"protection":protection,"protected_media_support":support,"playback_action":"ENABLED" if enabled else "DISABLED",
         "playback_reason":reason,"playable":enabled,"playback_provider":"core" if canonical=="DVD_VIDEO" else "protected-optical-provider"}

def ui_contribution(presentation:dict[str,Any],decision:dict[str,Any])->dict[str,Any]:
 if not presentation.get("owned") or not decision.get("owned"):
  return {"owned":False,"item_kind":"NONE","visible":False,"display_label":"","badge_key":"NONE","enabled":False,"disabled_reason":"NONE","action_intent":"NONE"}
 enabled=decision.get("playback_action")=="ENABLED"
 return {"owned":True,"item_kind":"OPTICAL_PLAYBACK","visible":True,"display_label":presentation.get("display_label",""),
         "badge_key":presentation.get("badge_key","NONE"),"enabled":enabled,"disabled_reason":"NONE" if enabled else decision.get("playback_reason","MEDIA_NOT_PLAYABLE"),
         "action_intent":"PLAY_CURRENT_OPTICAL_MEDIA" if enabled else "NONE"}
