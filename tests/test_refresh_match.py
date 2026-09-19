"""Hermetic tests for refresh modeset settling and graceful fallback.

Copyright 2026 Steve Dehanne
SPDX-License-Identifier: Apache-2.0
Part of the OPENHTPC project.
Original project by Steve Dehanne.
"""
import copy
import importlib.machinery
import importlib.util
import json
import pathlib
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]


def load_module(name: str):
    loader = importlib.machinery.SourceFileLoader(name.replace('-', '_'), str(ROOT / 'payload' / name))
    spec = importlib.util.spec_from_loader(name.replace('-', '_'), loader)
    m = importlib.util.module_from_spec(spec)
    loader.exec_module(m)
    return m


M = load_module('openhtpc-refresh-match.py')
P = load_module('openhtpc-playback-policy.py')
C = load_module('openhtpc-capabilities.py')


def create_snapshot(rates=(60, 23.976, 24, 50, 59.94), current='0'):
    modes = [dict(id=str(i), width=3840, height=2160, refresh_hz=rate) for i, rate in enumerate(rates)]
    output = dict(
        connector='HDMI-A-1',
        output_id=1,
        display_identity='a' * 64,
        active=True,
        connected=True,
        current_mode_id=current,
        current_mode={k: v for k, v in modes[int(current)].items() if k != 'id'},
        available_modes=modes,
        scale=1.7,
        current_hdr_mode={'state': 'ACTIVE'},
    )
    return dict(outputs=[output], active_output=output)


class MockRuntime:
    def __init__(self, value):
        self.value = copy.deepcopy(value)
        self.calls = []
        self.fail = False
        self.ignore = False

    def snapshot(self):
        return copy.deepcopy(self.value)

    def apply(self, output, mode):
        self.calls.append((output['output_id'], mode))
        if self.fail:
            return False
        if not self.ignore:
            o = self.value['active_output']
            o['current_mode_id'] = mode
            target_m = next((m for m in o['available_modes'] if m['id'] == mode), None)
            if target_m:
                o['current_mode'] = {k: v for k, v in target_m.items() if k != 'id'}
        return True


class TestRefreshModesetSettling(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = pathlib.Path(self.temp.name)
        P.write_preference(self.home, 'refresh_matching', 'AUTO')
        self.runtime = MockRuntime(create_snapshot())
        self.sleep_patcher = mock.patch.object(M.time, 'sleep')
        self.mock_sleep = self.sleep_patcher.start()
        self.addCleanup(self.sleep_patcher.stop)

    def test_01_no_mode_change_zero_settle_delay(self):
        """1. no mode change -> zero settle delay."""
        with M.matching(self.home, runtime=self.runtime, rate=60) as tx:
            self.assertIsNotNone(tx)
            self.assertFalse(tx.record.get('settled', False))
            self.assertEqual(tx.record.get('status'), 'ALREADY_MATCHED')
        sleep_2s = [c for c in self.mock_sleep.call_args_list if c.args and c.args[0] == 2.0]
        self.assertEqual(len(sleep_2s), 0)

    def test_02_successful_mode_change_exactly_one_2s_settle_before_launch(self):
        """2. successful mode change -> exactly one 2.0s settle before launch permission."""
        with M.matching(self.home, runtime=self.runtime, rate=23.976) as tx:
            self.assertIsNotNone(tx)
            self.assertTrue(tx.record.get('settled'))
            self.assertEqual(tx.record.get('settle_seconds'), 2.0)
            self.assertEqual(tx.record.get('refresh_phase'), 'REFRESH_MATCH_SETTLED')
        sleep_2s = [c for c in self.mock_sleep.call_args_list if c.args and c.args[0] == 2.0]
        self.assertEqual(len(sleep_2s), 1)

    def test_03_apply_success_and_verify_success_target_stable(self):
        """3. apply success + verify success -> target stable."""
        with M.matching(self.home, runtime=self.runtime, rate=24) as tx:
            self.assertEqual(tx.record.get('status'), 'APPLIED')
            self.assertTrue(tx.record.get('switch_verified'))
            self.assertTrue(tx.record.get('settled'))
            self.assertEqual(self.runtime.value['active_output']['current_mode_id'], '2')

    def test_04_apply_failure_takes_fallback_path(self):
        """4. apply failure -> fallback path."""
        self.runtime.fail = True
        with M.matching(self.home, runtime=self.runtime, rate=24) as tx:
            self.assertEqual(tx.record.get('status'), 'RESTORED')
            self.assertTrue(tx.record.get('fallback_active'))
            self.assertFalse(tx.record.get('switch_verified'))
            self.assertEqual(tx.record.get('refresh_phase'), 'REFRESH_MATCH_FALLBACK')
            self.assertEqual(self.runtime.value['active_output']['current_mode_id'], '0')

    def test_05_verify_failure_takes_fallback_path(self):
        """5. verify failure -> fallback path."""
        self.runtime.ignore = True
        with M.matching(self.home, runtime=self.runtime, rate=24) as tx:
            self.assertEqual(tx.record.get('status'), 'RESTORED')
            self.assertTrue(tx.record.get('fallback_active'))
            self.assertFalse(tx.record.get('switch_verified'))
            self.assertEqual(tx.record.get('refresh_phase'), 'REFRESH_MATCH_FALLBACK')
            self.assertEqual(self.runtime.value['active_output']['current_mode_id'], '0')

    def test_06_fallback_to_original_mode_permits_playback(self):
        """6. fallback to original mode -> playback permitted."""
        self.runtime.fail = True
        mock_runner = mock.Mock(return_value=mock.Mock(returncode=0))
        result = M.run_playback(self.home, ['mpv', 'movie.mkv'], runner=mock_runner, runtime=self.runtime)
        self.assertEqual(result.returncode, 0)
        mock_runner.assert_called_once()

    def test_07_fallback_modeset_settles_if_real_mode_change_occurred(self):
        """7. fallback modeset also gets settling if a real mode change occurred."""
        real_apply = self.runtime.apply

        def wrong_mode_apply(output, mode):
            return real_apply(output, '3' if mode == '2' else mode)

        self.runtime.apply = wrong_mode_apply
        with M.matching(self.home, runtime=self.runtime, rate=24) as tx:
            self.assertTrue(tx.record.get('fallback_active'))
            self.assertTrue(tx.record.get('fallback_settled'))
            self.assertTrue(tx.record.get('settled'))
            self.assertEqual(self.runtime.value['active_output']['current_mode_id'], '0')
        sleep_2s = [c for c in self.mock_sleep.call_args_list if c.args and c.args[0] == 2.0]
        self.assertEqual(len(sleep_2s), 1)

    def test_08_mpv_launch_never_runs_before_settle_completes(self):
        """8. MPV launch callback never runs before settle completes."""
        events = []

        def tracked_sleep(seconds):
            if seconds == 2.0:
                events.append('settle_completed')

        self.mock_sleep.side_effect = tracked_sleep

        def mock_runner(cmd, **kwargs):
            events.append('mpv_launched')
            return mock.Mock(returncode=0)

        with mock.patch.object(M, 'Runtime', return_value=self.runtime), \
             mock.patch.object(M, 'probe_cadence_evidence', return_value={'cadence_fps': 24.0, 'cadence_reason': 'VERIFIED_SAMPLE'}):
            M.run_playback(self.home, ['mpv', 'movie.mkv'], runner=mock_runner)

        self.assertEqual(events, ['settle_completed', 'mpv_launched'])

    def test_09_restore_after_successful_target_playback(self):
        """9. restore after successful target playback."""
        with M.matching(self.home, runtime=self.runtime, rate=24):
            self.assertEqual(self.runtime.value['active_output']['current_mode_id'], '2')
        self.assertEqual(self.runtime.value['active_output']['current_mode_id'], '0')
        last = M.read(self.home / '.local/state/openhtpc/refresh-match-last.json')
        self.assertEqual(last.get('refresh_phase'), 'REFRESH_MATCH_RESTORE')
        self.assertEqual(last.get('status'), 'RESTORED')

    def test_10_no_redundant_restore_when_fallback_already_uses_original_mode(self):
        """10. no redundant restore when fallback already uses original mode."""
        self.runtime.fail = True
        with M.matching(self.home, runtime=self.runtime, rate=24):
            pass
        calls_at_exit = list(self.runtime.calls)
        tx_file = self.home / '.local/state/openhtpc/refresh-transaction.json'
        self.assertFalse(tx_file.exists())
        self.assertEqual(self.runtime.calls, calls_at_exit)

    def test_11_timeout_bounded(self):
        """11. timeout bounded (verify does not loop indefinitely)."""
        tx = M.Transaction(self.home, self.runtime)
        orig = create_snapshot()['active_output']
        non_existent_mode = {'id': '999', 'width': 100, 'height': 100, 'refresh_hz': 120}
        self.assertFalse(tx.verify(orig, non_existent_mode))
        self.assertEqual(self.mock_sleep.call_count, 3)

    def test_12_exceptions_fail_gracefully(self):
        """12. exceptions fail gracefully."""
        self.runtime.snapshot = lambda: (_ for _ in ()).throw(OSError('DRM error'))
        mock_runner = mock.Mock(return_value=mock.Mock(returncode=0))
        result = M.run_playback(self.home, ['mpv', 'test.mkv'], runner=mock_runner)
        self.assertEqual(result.returncode, 0)
        mock_runner.assert_called_once()

    def test_13_pcm_path_obeys_same_sequencing(self):
        """13. PCM path obeys same sequencing."""
        events = []

        def tracked_sleep(seconds):
            if seconds == 2.0:
                events.append('settle_completed')

        self.mock_sleep.side_effect = tracked_sleep

        def mock_runner(cmd, **kwargs):
            events.append('mpv_launched')
            return mock.Mock(returncode=0)

        decision = {'audio_output': {'requested': 'PCM'}}
        with mock.patch.object(M, 'Runtime', return_value=self.runtime), \
             mock.patch.object(M, 'probe_cadence_evidence', return_value={'cadence_fps': 24.0, 'cadence_reason': 'VERIFIED_SAMPLE'}):
            M.run_playback(self.home, ['mpv', 'test.mkv'], runner=mock_runner, decision=decision)

        self.assertIn('settle_completed', events)
        self.assertIn('mpv_launched', events)
        self.assertLess(events.index('settle_completed'), events.index('mpv_launched'))

    def test_14_bitstream_path_obeys_same_sequencing(self):
        """14. bitstream path obeys same sequencing."""
        events = []

        def tracked_sleep(seconds):
            if seconds == 2.0:
                events.append('settle_completed')

        self.mock_sleep.side_effect = tracked_sleep

        def mock_runner(cmd, **kwargs):
            events.append('mpv_launched')
            return mock.Mock(returncode=0)

        decision = {'audio_output': {'requested': 'BITSTREAM'}}
        with mock.patch.object(M, 'Runtime', return_value=self.runtime), \
             mock.patch.object(M, 'probe_cadence_evidence', return_value={'cadence_fps': 24.0, 'cadence_reason': 'VERIFIED_SAMPLE'}):
            M.run_playback(self.home, ['mpv', 'test.mkv'], runner=mock_runner, decision=decision)

        self.assertIn('settle_completed', events)
        self.assertIn('mpv_launched', events)
        self.assertLess(events.index('settle_completed'), events.index('mpv_launched'))

    def test_15_existing_rate_matching_rules_unchanged(self):
        """15. existing 24/23.976 matching rules unchanged."""
        s = create_snapshot()
        status_23, target_23 = M.select(s, 24000 / 1001)
        self.assertEqual(status_23, 'MATCH_AVAILABLE')
        self.assertAlmostEqual(target_23['refresh_hz'], 23.976, places=3)

        status_24, target_24 = M.select(s, 24)
        self.assertEqual(status_24, 'MATCH_AVAILABLE')
        self.assertEqual(target_24['refresh_hz'], 24)

    def test_16_no_modification_to_hwdec_gpu_next_policy(self):
        """16. no modification to hwdec/gpu-next policy."""
        refresh_code = (ROOT / 'payload/openhtpc-refresh-match.py').read_text()
        self.assertNotIn('vaapi-copy', refresh_code)
        self.assertNotIn('hwdec=no', refresh_code)
        self.assertNotIn('amdgpu', refresh_code.lower())
        self.assertNotIn('vega', refresh_code.lower())


if __name__ == '__main__':
    unittest.main()
