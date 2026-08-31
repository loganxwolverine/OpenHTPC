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
