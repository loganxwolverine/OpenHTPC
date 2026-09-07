# Copyright 2026 Steve Dehanne
# SPDX-License-Identifier: Apache-2.0
#
# Part of the OPENHTPC project.
# Original project by Steve Dehanne.
"""Passive audio discovery and pure descriptor resolution (RC7 T7.1).

No persistence, routing, playback proof or audio-server mutation. SYSTEM is
always a policy choice, even when the server cannot currently be observed.
"""
from __future__ import annotations

import json
import subprocess

PROBE_TIMEOUT = 1.0  # per command; at most two sequential commands
DESCRIPTOR_FIELDS = ('node_name', 'bus_path', 'edid_name', 'display_label', 'device_type')


def _text(value):
    return value.strip() if isinstance(value, str) else ''


def _true(value):
    return value is True or str(value).lower() in ('true', '1', 'yes')


def system_descriptor():
    return dict(mode='SYSTEM', node_name=None, bus_path=None, edid_name=None,
                display_label='SYSTEM', device_type='UNKNOWN')


def device_descriptor(output):
    """JSON-serializable identity; deliberately never copies numeric IDs."""
    return dict(mode='DEVICE', **{key: output.get(key) for key in DESCRIPTOR_FIELDS})


def parse_sinks(raw, default_sink=None):
    """Normalize pactl JSON; reject network, virtual and disconnected outputs.

    edid_name uses explicit EDID/port product metadata first, then HDMI
    node.nick/alsa.name as an identity hint, not as verified EDID evidence.
    SUSPENDED sinks remain usable: suspension is normal when idle.
    """
    try:
        sinks = json.loads(raw)
    except (ValueError, TypeError):
        return []
    if not isinstance(sinks, list):
        return []
    outputs = []
    for sink in sinks:
        if not isinstance(sink, dict):
            continue
        props = sink.get('properties')
        props = props if isinstance(props, dict) else {}
        name = _text(sink.get('name')) or _text(props.get('node.name'))
        flags = sink.get('flags')
        flags = flags if isinstance(flags, list) else []
        protocol = ' '.join([name, _text(sink.get('driver')),
                             _text(props.get('sess.media')), _text(props.get('device.api'))]).lower()
        network = (_true(props.get('node.network')) or 'NETWORK' in flags
                   or 'raop' in protocol or 'airplay' in protocol)
        if not name or network or _true(props.get('node.virtual')):
            continue
        ports = sink.get('ports')
        ports = [p for p in ports if isinstance(p, dict)] if isinstance(ports, list) else []
        port = next((p for p in ports if p.get('name') == sink.get('active_port')), {})
        if port.get('availability') in ('not available', 'unavailable', 'no'):
            continue
        api = _text(props.get('device.api')).lower()
        bus = _text(props.get('device.bus')).lower()
        if not ('HARDWARE' in flags or api in ('alsa', 'bluez5', 'bluez')
                or name.startswith(('alsa_output.', 'bluez_output.', 'bluez_sink.'))):
            continue
        profile = ' '.join([name, _text(props.get('device.profile.name')),
                            _text(props.get('api.alsa.path')), _text(port.get('type'))]).lower()
        if api.startswith('bluez') or bus == 'bluetooth' or name.startswith(('bluez_output.', 'bluez_sink.')):
            kind = 'BLUETOOTH'
        elif 'hdmi' in profile:
            kind = 'HDMI'
        elif bus == 'usb' or name.startswith('alsa_output.usb-'):
            kind = 'USB'
        elif 'analog' in profile:
            kind = 'ANALOG'
        else:
            kind = 'UNKNOWN'
        port_props = port.get('properties')
        port_props = port_props if isinstance(port_props, dict) else {}
        nick = _text(props.get('node.nick')) or None
        alsa = _text(props.get('alsa.name')) or None
        edid = (_text(props.get('edid.name')) or _text(props.get('device.product.name.edid'))
                or _text(port_props.get('device.product.name')) or None)
        if kind == 'HDMI':
            edid = edid or nick or alsa
        outputs.append(dict(node_name=name,
                            display_label=edid or nick or alsa or _text(sink.get('description')) or name,
                            device_type=kind, bus_path=_text(props.get('device.bus_path')) or None,
                            edid_name=edid, **{'node.nick': nick, 'alsa.name': alsa},
                            is_network=False, is_default=name == default_sink))
    return outputs


def _pactl(*args):
    try:
        result = subprocess.run(['pactl', *args], capture_output=True, text=True,
                                timeout=PROBE_TIMEOUT, check=False)
        return result.stdout if result.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired, UnicodeError):
        return None


def discover_outputs():
    raw = _pactl('--format=json', 'list', 'sinks')
    outputs = parse_sinks(raw)
    if not outputs:
        return []
    default = _text(_pactl('get-default-sink'))
    for output in outputs:
        output['is_default'] = output['node_name'] == default
    return outputs


def resolve_audio(configured, outputs):
    """CONFIGURED is retained; EFFECTIVE is a policy target, never runtime proof.

    AVAILABLE for SYSTEM means the policy option exists, not that audio works.
    Composite fallback requires both nonempty identity components and uniqueness.
    """
    configured = dict(configured) if configured is not None else system_descriptor()
    if configured.get('mode') == 'SYSTEM':
        return dict(CONFIGURED=configured, AVAILABLE=True, EFFECTIVE=system_descriptor())
    eligible = [o for o in outputs if not o.get('is_network')]
    matches = []
    if configured.get('mode') == 'DEVICE':
        name = configured.get('node_name')
        matches = [o for o in eligible if name and o.get('node_name') == name]
        if not matches and configured.get('bus_path') and configured.get('edid_name'):
            matches = [o for o in eligible if o.get('bus_path') == configured['bus_path']
                       and o.get('edid_name') == configured['edid_name']]
    found = matches[0] if len(matches) == 1 else None
    return dict(CONFIGURED=configured, AVAILABLE=found is not None,
                EFFECTIVE=device_descriptor(found) if found else system_descriptor())


def recommend_output(outputs, *, interactive=False):
    """Return a suggestion only; None means multiple HDMI choices need a human."""
    if not interactive:
        return system_descriptor()
    hdmi = [o for o in outputs if o.get('device_type') == 'HDMI' and not o.get('is_network')]
    if len(hdmi) == 1:
        return device_descriptor(hdmi[0])
    return None if hdmi else system_descriptor()
