# Copyright 2026 Steve Dehanne
# SPDX-License-Identifier: Apache-2.0
#
# Part of the OPENHTPC project.
# Original project by Steve Dehanne.
import importlib.util
import json
from pathlib import Path
import subprocess
from unittest.mock import patch

import pytest

spec = importlib.util.spec_from_file_location('rc7_audio', Path(__file__).resolve().parents[1] / 'payload/openhtpc-audio.py')
audio = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audio)


def sink(label='DENON-AVR', name='alsa_output.pci-0000_04_00.0.hdmi-surround71', **props):
    return dict(index=1207, state='SUSPENDED', name=name, description='HDMI controller',
                flags=['HARDWARE'], properties={'device.api': 'alsa',
                'device.bus_path': 'pci-0000:04:00.0', 'node.nick': label,
                'alsa.name': label, **props})


def discover(*sinks):
    return audio.parse_sinks(json.dumps(sinks))


@pytest.mark.parametrize('label', ['DENON-AVR', 'Living room TV'])
def test_physical_hdmi(label):
    row, = discover(sink(label))
    assert row['display_label'] == row['edid_name'] == label
    assert row['device_type'] == 'HDMI'
    assert row['bus_path'] == 'pci-0000:04:00.0'
    assert row['node.nick'] == row['alsa.name'] == label
    assert not row['is_network']


@pytest.mark.parametrize('network_props,name', [
    ({'node.network': True}, 'alsa_output.network.hdmi'),
    ({'node.network': 'true'}, 'alsa_output.network.hdmi'),
    ({}, 'raop_sink.Denon'), ({}, 'airplay_sink.Denon'),
])
def test_network_excluded(network_props, name):
    assert len(discover(sink(), sink(name=name, **network_props))) == 1


def test_two_hdmi_no_recommendation():
    rows = discover(sink(), sink('TV', 'alsa_output.other.hdmi'))
    assert audio.recommend_output(rows, interactive=True) is None


def test_single_hdmi_suggestion_only_interactive():
    rows = discover(sink())
    assert audio.recommend_output(rows, interactive=True) == audio.device_descriptor(rows[0])
    assert audio.recommend_output(rows)['mode'] == 'SYSTEM'


@pytest.mark.parametrize('name,props,kind', [
    ('alsa_output.pci.analog-stereo', {}, 'ANALOG'),
    ('alsa_output.usb-headset.analog-stereo', {'device.bus': 'usb'}, 'USB'),
    ('bluez_output.headset', {'device.api': 'bluez5'}, 'BLUETOOTH'),
    ('alsa_output.pci.iec958-stereo', {}, 'UNKNOWN'),
])
def test_non_hdmi(name, props, kind):
    rows = discover(sink(name=name, **props))
    assert rows[0]['device_type'] == kind
    assert audio.recommend_output(rows, interactive=True)['mode'] == 'SYSTEM'


def test_numeric_ids_irrelevant():
    raw = sink()
    before = discover(raw)
    raw['index'] = 9988
    raw['properties'].update({'object.id': '88', 'object.serial': '9988', 'device.id': '72'})
    after = discover(raw)
    assert before == after
    descriptor = audio.device_descriptor(before[0])
    assert set(descriptor) == {'mode', 'node_name', 'bus_path', 'edid_name', 'display_label', 'device_type'}
    assert audio.resolve_audio(descriptor, after)['AVAILABLE']


def test_profile_change_composite_resolution():
    configured = audio.device_descriptor(discover(sink())[0])
    rows = discover(sink(name='alsa_output.pci-0000_04_00.0.hdmi-stereo'))
    result = audio.resolve_audio(configured, rows)
    assert result['CONFIGURED'] == configured
    assert result['AVAILABLE']
    assert result['EFFECTIVE']['node_name'] == rows[0]['node_name']
    assert set(result) == {'CONFIGURED', 'AVAILABLE', 'EFFECTIVE'}


def test_ambiguous_composite_unavailable():
    configured = audio.device_descriptor(discover(sink())[0])
    rows = discover(sink(name='alsa_output.a.hdmi'), sink(name='alsa_output.b.hdmi'))
    assert audio.resolve_audio(configured, rows)['AVAILABLE'] is False
    assert audio.resolve_audio(configured, rows)['EFFECTIVE']['mode'] == 'SYSTEM'


def test_exact_name_precedes_composite():
    rows = discover(sink(), sink(name='alsa_output.other.hdmi'))
    configured = audio.device_descriptor(rows[0])
    assert audio.resolve_audio(configured, rows)['EFFECTIVE'] == configured


def test_missing_amplifier():
    configured = audio.device_descriptor(discover(sink())[0])
    assert audio.resolve_audio(configured, []) == dict(CONFIGURED=configured, AVAILABLE=False,
                                                     EFFECTIVE=audio.system_descriptor())


@pytest.mark.parametrize('missing', ['bus_path', 'edid_name'])
def test_incomplete_composite_never_matches(missing):
    configured = audio.device_descriptor(discover(sink())[0])
    configured[missing] = None
    assert not audio.resolve_audio(configured, discover(sink(name='alsa_output.other.hdmi')))['AVAILABLE']


@pytest.mark.parametrize('failure', [FileNotFoundError(), subprocess.TimeoutExpired('pactl', 1),
                                    subprocess.CompletedProcess([], 1, '', 'Connection refused'),
                                    subprocess.CompletedProcess([], 0, '{invalid', '')])
def test_probe_failures(failure):
    with patch.object(audio.subprocess, 'run') as run:
        if isinstance(failure, Exception):
            run.side_effect = failure
        else:
            run.return_value = failure
        assert audio.discover_outputs() == []
        assert run.call_count == 1
    assert audio.resolve_audio(None, [])['EFFECTIVE']['mode'] == 'SYSTEM'


def test_passive_commands_bounded_and_default():
    raw = sink()
    with patch.object(audio.subprocess, 'run', side_effect=[
        subprocess.CompletedProcess([], 0, json.dumps([raw])),
        subprocess.CompletedProcess([], 0, raw['name'] + '\n'),
    ]) as run:
        assert audio.discover_outputs()[0]['is_default']
        assert [call.args[0] for call in run.call_args_list] == [
            ['pactl', '--format=json', 'list', 'sinks'], ['pactl', 'get-default-sink']]
        for call in run.call_args_list:
            assert 0 < call.kwargs['timeout'] <= 1
            assert not call.kwargs.get('shell')


def test_default_query_failure_keeps_discovery():
    with patch.object(audio.subprocess, 'run', side_effect=[
        subprocess.CompletedProcess([], 0, json.dumps([sink()])), FileNotFoundError(),
    ]):
        rows = audio.discover_outputs()
    assert len(rows) == 1 and not rows[0]['is_default']


@pytest.mark.parametrize('raw', ['null', '{}', '[null, 3, "bad", {"properties": null}]'])
def test_malformed_shapes(raw):
    assert audio.parse_sinks(raw) == []


def test_virtual_and_disconnected_excluded():
    disconnected = sink()
    disconnected.update(active_port='hdmi-output-0', ports=[dict(name='hdmi-output-0', availability='not available')])
    assert discover(disconnected, sink(**{'node.virtual': 'true'}), dict(name='auto_null')) == []


def test_system_can_follow_network_default():
    rows = audio.parse_sinks(json.dumps([sink(), sink(name='raop_sink.Denon')]), 'raop_sink.Denon')
    assert not rows[0]['is_default']
    assert audio.resolve_audio(audio.system_descriptor(), rows)['EFFECTIVE']['mode'] == 'SYSTEM'
