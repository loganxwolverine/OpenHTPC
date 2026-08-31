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
