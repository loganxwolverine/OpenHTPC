# Copyright 2026 Steve Dehanne
# SPDX-License-Identifier: Apache-2.0
# Part of the OPENHTPC project.
# Original project by Steve Dehanne.
"""Hermetic T8.4 compositor/EDID separation and installed-API contract."""
import json
import os
import pathlib
import tempfile
import unittest
from unittest import mock
from tests.test_rc7_system_model import cap_mod as cap, sys_model as model, ui_mod as ui, PAYLOAD


resolve_context = cap.resolve_graphical_context

def edid(hdr=True):
    base = bytearray(128); base[:8] = b'\x00\xff\xff\xff\xff\xff\xff\x00'; base[126] = 1
    ext = bytearray(128); ext[:4] = bytes([2, 3, 8, 0]); ext[4:8] = bytes([0xe3, 6, 0x0d if hdr else 1, 1])
    for block in (base, ext): block[127] = (-sum(block)) % 256
    return bytes(base + ext)


class DisplayRuntime(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.home = pathlib.Path(temp.name); self.sys = self.home/'sys'; self.sys.mkdir()
        self.output = {'name': 'HDMI-A-6', 'connected': True, 'enabled': True,
                       'currentModeId': 'current', 'scale': 2.0, 'hdr': False, 'maxBpc': 12,
                       'modes': [{'id': 'preferred', 'size': {'width': 3840, 'height': 2160}, 'refreshRate': 120},
                                 {'id': 'current', 'size': {'width': 3840, 'height': 2160}, 'refreshRate': 59.94}]}
        p = mock.patch.object(cap, 'resolve_graphical_context', return_value={'status': 'RESOLVED', 'environment': {'XDG_SESSION_TYPE': 'wayland'}, 'evidence': 'FIXTURE'})
        p.start(); self.addCleanup(p.stop)
        p = mock.patch.object(model, '_load_gpu_runtime', return_value=None); p.start(); self.addCleanup(p.stop)
        self.calls = []

    def connector(self, name='card1-HDMI-A-6', hdr=True, status='connected'):
        p = self.sys/'class/drm'/name; p.mkdir(parents=True)
        (p/'status').write_text(status); (p/'edid').write_bytes(edid(hdr))
        return p

    def collect(self, outputs=None, status='OK', text=None):
        def runner(argv, timeout):
            self.calls.append(argv)
            self.assertEqual(argv[-2:], ['kscreen-doctor', '-j'])
            self.assertEqual(timeout, 6)
            return {'status': status, 'stdout': text if text is not None else json.dumps({'outputs': outputs if outputs is not None else [self.output]}), 'stderr': '', 'returncode': 0}
        return cap.collect_display(self.home, PAYLOAD, runner, self.sys, self.sys)

    def present(self, state):
        return model.build(self.home, PAYLOAD, {}, {}, display_snapshot=state,
                           display_resolution=({'pci_address': '0000:03:00.0', 'model': 'Intel Arc A310'}, 'RESOLVED'),
                           gpu_binding={'status': 'AUTO_FALLBACK'}, pure_conf_text='hwdec=vaapi\n')

    def test_current_mode_precision_and_scale(self):
        self.connector(); m = self.present(self.collect())
        self.assertEqual(m['display']['resolution'], '3840 × 2160')
        self.assertEqual(m['display']['refresh'], '59.940 Hz')
        self.assertEqual(m['display']['scale'], '200 %')
        self.assertEqual(m['display']['connector'], 'HDMI-A-6')

    def test_preferred_mode_not_current(self):
        self.output['modes'][1]['refreshRate'] = 60
        self.assertEqual(self.present(self.collect())['display']['refresh'], '60.000 Hz')

    def test_hdr_capability_independent_of_current_hdr(self):
        self.connector()
        for enabled, label in [(False, 'Désactivé'), (True, 'Activé')]:
            self.output['hdr'] = enabled
            d = self.present(self.collect())['display']
            self.assertEqual(d['hdr_capable'], 'Oui'); self.assertEqual(d['hdr_current'], label)

    def test_missing_edid_and_max_bpc_do_not_invent_facts(self):
        d = self.present(self.collect())['display']
        self.assertEqual(d['hdr_capable'], 'Non déterminé')
        self.assertEqual(d['depth'], 'Non déterminée')
        self.assertEqual(d['hdr_pipeline'], 'Non déterminé')
        self.assertEqual(d['auto_refresh'], 'Désactivé')

    def test_other_connector_hdr_not_merged(self):
        self.connector(hdr=False); self.connector('card1-HDMI-A-1', hdr=True)
        second = {**self.output, 'name': 'HDMI-A-1', 'enabled': False}
        d = self.present(self.collect([second, self.output]))['display']
        self.assertEqual(d['connector'], 'HDMI-A-6'); self.assertEqual(d['hdr_capable'], 'Non déterminé')

    def test_multi_active_no_arbitrary_winner(self):
        self.assertIsNone(self.collect([self.output, {**self.output, 'name': 'DP-1'}])['active_output'])

    def test_disconnected_never_active(self):
        self.output['connected'] = False
        self.assertIsNone(self.collect()['active_output'])

    def test_sysfs_disconnection_invalidates_output(self):
        self.connector(status='disconnected')
        self.assertIsNone(self.collect()['active_output'])

    def test_duplicate_drm_connector_no_edid_guess(self):
        self.connector(); self.connector('card2-HDMI-A-6')
        self.assertEqual(self.collect()['active_output']['hdr_capable']['status'], 'UNKNOWN')

    def test_stale_passport_and_snapshot_not_current(self):
        p = self.home/'.config/openhtpc'; p.mkdir(parents=True)
        (p/'profile.json').write_text(json.dumps({'display': {'connector': 'OLD', 'refresh': 120}}))
        self.assertEqual(self.present(self.collect())['display']['connector'], 'HDMI-A-6')
        with mock.patch.object(model, '_current_display', return_value={}):
            m = model.build(self.home, PAYLOAD, {}, {}, display_resolution=(None, 'UNKNOWN'), gpu_binding={})
        self.assertEqual(m['display']['refresh'], 'Non déterminée')

    def test_probe_failures_and_truncation(self):
        for status, text in [('TIMEOUT', ''), ('FAILED', ''), ('COMMAND_UNAVAILABLE', ''), ('OK', '{"outputs":[')]:
            self.assertIsNone(self.collect(status=status, text=text)['active_output'])

    def test_ambiguous_or_absent_mode_not_preferred(self):
        for modes in [[], [self.output['modes'][0]], [self.output['modes'][1]] * 2]:
            out = {**self.output, 'modes': modes}
            self.assertIsNone(self.collect([out])['active_output']['current_mode'])

    def test_edid_invalid_or_truncated_unknown(self):
        good = edid()
        for data in [b'', good[:128], good[:-1], b'x'+good[1:]]:
            self.assertEqual(cap.edid_hdr_capability(data)['status'], 'UNKNOWN')

    def test_kwin_child_context_after_controller_stops(self):
        uid = os.getuid()
        parent = self.sys/'10'; child = self.sys/'11'
        parent.mkdir(); child.mkdir()
        (parent/'comm').write_text('kwin_wayland')
        (parent/'status').write_text(f'Uid: {uid} {uid} {uid} {uid}\n')
        (child/'comm').write_text('plasma-keyboard')
        (child/'status').write_text(f'Uid: {uid} {uid} {uid} {uid}\nPPid: 10\n')
        (child/'cmdline').write_bytes(b'/usr/bin/plasma-keyboard\0')
        (child/'environ').write_bytes(f'XDG_RUNTIME_DIR=/run/user/{uid}\0DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/{uid}/bus\0WAYLAND_DISPLAY=wayland-7\0XDG_SESSION_TYPE=wayland\0'.encode())
        result = resolve_context(self.sys, uid=uid, environment={}, home=self.home, install=PAYLOAD)
        self.assertEqual(result['environment']['WAYLAND_DISPLAY'], 'wayland-7')
        (parent/'comm').write_text('unrelated')
        self.assertEqual(resolve_context(self.sys, uid=uid, environment={}, home=self.home, install=PAYLOAD)['status'], 'UNAVAILABLE')

    def test_no_session_does_not_probe(self):
        with mock.patch.object(cap, 'resolve_graphical_context', return_value={'status': 'UNAVAILABLE'}):
            self.assertIsNone(self.collect()['active_output'])
        self.assertEqual(self.calls, [])

    def test_fractional_refresh_is_not_rounded_in_summary(self):
        self.output['modes'][1]['refreshRate'] = 23.97599983215332
        d = self.present(self.collect())['display']
        self.assertEqual(d['refresh'], '23.976 Hz')
        self.assertIn('23.976 Hz', d['summary'])

    def test_refresh_policy_presented(self):
        config = self.home / '.config/openhtpc/user-config.json'
        config.parent.mkdir(parents=True, exist_ok=True)
        for choice, label in [('AUTO', 'Automatique'), ('OFF', 'Désactivé')]:
            config.write_text(json.dumps({'refresh_matching': choice}))
            self.assertEqual(self.present(self.collect())['display']['auto_refresh'], label)

    def test_auto_refresh_absent_empty_unknown_never_blank(self):
        from PIL import ImageDraw
        m = self.present(self.collect())
        self.assertEqual(m['display']['auto_refresh'], 'Désactivé')
        m['available'] = True
        for value in (None, '', '   ', 'UNKNOWN', 'NOT_PROVEN', 'Non déterminé'):
            with self.subTest(value=value):
                if value is None:
                    m['display'].pop('auto_refresh', None)
                else:
                    m['display']['auto_refresh'] = value
                with mock.patch.object(ImageDraw.ImageDraw, 'text', autospec=True) as draw:
                    ui.system_page_png(m, self.home/'refresh-proof.png', PAYLOAD/'flex/assets/fonts/OpenSans-Regular.ttf', 'display')
                texts = [(c.args[1], c.args[2]) for c in draw.call_args_list]
                label = next(pos for pos, text in texts if text == 'Mode de rafraîchissement')
                values = [text for pos, text in texts if pos[0] > label[0] and abs(pos[1] - label[1]) <= 2]
                self.assertEqual(values, ['Non déterminé'])

    def test_t83_and_couch_render(self):
        self.connector(); m = self.present(self.collect())
        self.assertEqual(m['overview']['gpu'], 'Intel Arc A310')
        self.assertEqual(m['overview']['video_accel'], 'VA-API')
        self.assertEqual(m['technical']['physical_decode_gpu'], 'Non déterminé')
        from PIL import ImageDraw
        with mock.patch.object(ImageDraw.ImageDraw, 'text', autospec=True) as draw:
            ui.system_page_png(m, self.home/'display.png', PAYLOAD/'flex/assets/fonts/OpenSans-Regular.ttf', 'display')
        text = ' '.join(str(c.args[2]) for c in draw.call_args_list)
        for token in ['max_bpc', 'NOT_PROVEN', 'CTA-861', 'EOTF', 'Prise en charge automatique']:
            self.assertNotIn(token, text)

if __name__ == '__main__': unittest.main()
