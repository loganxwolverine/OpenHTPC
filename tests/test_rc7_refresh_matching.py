"""T8.6 hermetic refresh transactions; no compositor/hardware calls.
Copyright 2026 Steve Dehanne
SPDX-License-Identifier: Apache-2.0
Part of the OPENHTPC project.
Original project by Steve Dehanne.
"""
import copy
import importlib.util
import json
import pathlib
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
def module(name):
    spec = importlib.util.spec_from_file_location(name.replace('-', '_'), ROOT/'payload'/name)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m
M = module('openhtpc-refresh-match.py')
C = module('openhtpc-capabilities.py')
P = module('openhtpc-playback-policy.py')


def snapshot(rates=(60, 23.976, 24, 50, 59.94), current='0'):
    modes = [dict(id=str(i), width=3840, height=2160, refresh_hz=rate) for i,rate in enumerate(rates)]
    output = dict(connector='HDMI-A-6', output_id=1, display_identity='a'*64,
                  active=True, connected=True, current_mode_id=current,
                  current_mode={k:v for k,v in modes[int(current)].items() if k != 'id'},
                  available_modes=modes, scale=2.0, current_hdr_mode={'state':'ACTIVE'})
    return dict(outputs=[output], active_output=output)


class FakeRuntime:
    def __init__(self, value):
        self.value=copy.deepcopy(value); self.calls=[]; self.fail=False; self.ignore=False
    def snapshot(self): return copy.deepcopy(self.value)
    def apply(self, output, mode):
        self.calls.append((output['output_id'], mode))
        if self.fail: return False
        if not self.ignore:
            o=self.value['active_output'];o['current_mode_id']=mode
            o['current_mode']={k:v for k,v in next(m for m in o['available_modes'] if m['id']==mode).items() if k!='id'}
        return True


class RefreshTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.home=pathlib.Path(self.temp.name)
        P.write_preference(self.home,'refresh_matching','AUTO')
        self.runtime=FakeRuntime(snapshot())
        patch=mock.patch.object(M.time,'sleep');patch.start();self.addCleanup(patch.stop)

    def test_rates(self):
        for rate,expected in [(24000/1001,23.976),(24,24),(25,50),(30000/1001,59.94)]:
            with self.subTest(rate=rate):
                status,target=M.select(snapshot(),rate)
                self.assertEqual(status,'MATCH_AVAILABLE');self.assertEqual(target['refresh_hz'],expected)

    def test_all_families(self):
        for rate in (23.976,24,25,29.97,30,50,59.94,60):
            self.assertTrue(M.clean_multiple(rate,rate))
            self.assertTrue(M.clean_multiple(rate*2,rate))

    def test_fractional_distinction(self):
        for a,b in [(23.976,24),(59.94,60),(29.97,30),(23.976,59.94)]:
            self.assertFalse(M.clean_multiple(b,a))

    def test_already_multiple(self):
        self.assertEqual(M.select(snapshot(),30)[0],'ALREADY_MATCHED')
        self.assertEqual(M.select(snapshot(current='1'),23.976)[0],'ALREADY_MATCHED')

    def test_no_clean_match(self):
        self.assertEqual(M.select(snapshot((60,)),23.976)[0],'NO_CLEAN_MATCH')

    def test_same_resolution(self):
        s=snapshot((60,23.976));s['active_output']['available_modes'][1]['width']=1920
        self.assertEqual(M.select(s,23.976)[0],'NO_CLEAN_MATCH')

    def test_multi_display(self):
        s=snapshot();s['outputs'].append(dict(active=True))
        self.assertEqual(M.select(s,24)[0],'MULTI_DISPLAY_UNSUPPORTED')

    def test_unknown(self):
        self.assertEqual(M.select(snapshot(),None)[0],'UNAVAILABLE')
        self.assertEqual(M.select({},24)[0],'DISPLAY_UNAVAILABLE')

    def test_missing_identity(self):
        s=snapshot();s['active_output'].pop('display_identity')
        self.assertEqual(M.select(s,24)[0],'DISPLAY_UNAVAILABLE')

    def test_normal_restore_exact_id(self):
        with M.matching(self.home,runtime=self.runtime,rate=23.976):
            self.assertEqual(M.read(self.home/'.local/state/openhtpc/refresh-transaction.json')['state'],'APPLIED')
            self.assertEqual(self.runtime.calls,[(1,'1')])
        self.assertEqual(self.runtime.calls,[(1,'1'),(1,'0')])
        self.assertFalse((self.home/'.local/state/openhtpc/refresh-transaction.json').exists())

    def test_error_and_stop_restore(self):
        for error in (RuntimeError('MPV'),SystemExit(0),KeyboardInterrupt()):
            with self.subTest(error=type(error).__name__):
                with self.assertRaises(type(error)):
                    with M.matching(self.home,runtime=self.runtime,rate=24): raise error
                self.assertEqual(self.runtime.value['active_output']['current_mode_id'],'0')

    def test_switch_failure_allows_playback(self):
        self.runtime.fail=True
        with M.matching(self.home,runtime=self.runtime,rate=24): pass
        self.assertEqual(self.runtime.value['active_output']['current_mode_id'],'0')

    def test_verification_failure_restore(self):
        self.runtime.ignore=True
        with M.matching(self.home,runtime=self.runtime,rate=24): pass
        self.assertEqual(M.read(self.home/'.local/state/openhtpc/refresh-match-last.json')['status'],'RESTORED')

    def test_wrong_achieved_mode_restore(self):
        real=self.runtime.apply
        def wrong(output,mode): return real(output,'3' if mode=='2' else mode)
        self.runtime.apply=wrong
        with M.matching(self.home,runtime=self.runtime,rate=24): pass
        self.assertEqual(self.runtime.calls,[(1,'3'),(1,'0')])

    def prepare_stale(self):
        tx=M.Transaction(self.home,self.runtime);tx.acquire();tx.begin(24);tx.release()
        return tx

    def test_stale_recovery(self):
        self.prepare_stale()
        tx=M.Transaction(self.home,self.runtime);tx.acquire()
        try: self.assertTrue(tx.restore())
        finally:tx.release()
        self.assertEqual(self.runtime.value['active_output']['current_mode_id'],'0')

    def test_stale_different_monitor(self):
        self.prepare_stale();self.runtime.value['active_output']['display_identity']='b'*64
        calls=list(self.runtime.calls)
        tx=M.Transaction(self.home,self.runtime);tx.acquire()
        try:self.assertFalse(tx.restore())
        finally:tx.release()
        self.assertEqual(self.runtime.calls,calls)

    def test_stale_mode_id_reused(self):
        self.prepare_stale();self.runtime.value['active_output']['available_modes'][0]['refresh_hz']=50
        tx=M.Transaction(self.home,self.runtime);tx.acquire()
        try:self.assertFalse(tx.restore())
        finally:tx.release()
        self.assertEqual(len(self.runtime.calls),1)

    def test_hdr_scale_preserved(self):
        with M.matching(self.home,runtime=self.runtime,rate=24):
            o=self.runtime.value['active_output'];self.assertEqual(o['scale'],2);self.assertEqual(o['current_hdr_mode'],{'state':'ACTIVE'})
        self.assertTrue(all(len(call)==2 for call in self.runtime.calls))

    def test_disabled_no_probe(self):
        P.write_preference(self.home,'refresh_matching','OFF')
        with mock.patch.object(M,'probe_cadence',side_effect=AssertionError('probe')):
            with M.matching(self.home,runtime=self.runtime):pass
        self.assertEqual(self.runtime.calls,[])

    def test_fresh_migration_disabled_preserves_keys(self):
        cfg=self.home/'.config/openhtpc/user-config.json';cfg.write_text(json.dumps({'tmdb':{'extra':'keep'}}))
        self.assertFalse(M.policy(self.home));self.assertEqual(P.read_preferences(self.home)['refresh_matching'],'OFF')
        P.write_preference(self.home,'refresh_matching','AUTO')
        self.assertEqual(json.loads(cfg.read_text())['tmdb'],{'extra':'keep'})

    def test_busy_transaction_no_second_switch(self):
        with M.matching(self.home,runtime=self.runtime,rate=24):
            with M.matching(self.home,runtime=self.runtime,rate=25):pass
            self.assertEqual(self.runtime.calls,[(1,'2')])

    def test_cadence_strict(self):
        def probe(a,b):return {'streams':[dict(codec_type='video',avg_frame_rate=a,r_frame_rate=b,field_order='progressive')]}
        self.assertAlmostEqual(M.cadence(probe('24000/1001','24000/1001')),23.976,places=3)
        for a,b in [('0/0','0/0'),('24/1','25/1'),('nan','nan')]:self.assertIsNone(M.cadence(probe(a,b)))
        self.assertIsNone(M.cadence(None))

    def test_optical_unknown_cadence(self):
        self.assertIsNone(M.probe_cadence(None))
        with M.matching(self.home,runtime=self.runtime):pass
        self.assertEqual(self.runtime.calls,[])

    def test_kscreen_exact_modes(self):
        raw={'outputs':[dict(name='HDMI-A-6',id=1,connected=True,enabled=True,currentModeId='original',scale=2,hdr=False,modes=[dict(id='original',refreshRate=59.94,size=dict(width=3840,height=2160))])]}
        o=C.parse_kscreen_json(json.dumps(raw))[0]
        self.assertEqual(o['current_mode_id'],'original');self.assertEqual(o['available_modes'][0]['refresh_hz'],59.94)

    def test_runtime_exception_does_not_block(self):
        self.runtime.snapshot=lambda: (_ for _ in ()).throw(OSError('no compositor'))
        with M.matching(self.home,runtime=self.runtime,rate=24):pass

    def test_production_mode_only_command(self):
        r=M.Runtime.__new__(M.Runtime);r.home=self.home;r.install=ROOT/'payload';r.caps=mock.Mock()
        r.caps.resolve_graphical_context.return_value={'status':'RESOLVED','environment':{}}
        with mock.patch.object(M.subprocess,'run',return_value=mock.Mock(returncode=0)) as run:
            self.assertTrue(r.apply(snapshot()['active_output'],'1'))
            self.assertEqual(run.call_args.args[0],['kscreen-doctor','output.1.mode.1'])

    def test_restore_failure_explicit(self):
        with M.matching(self.home,runtime=self.runtime,rate=24):
            self.runtime.fail=True
        self.assertEqual(M.read(self.home/'.local/state/openhtpc/refresh-match-last.json')['status'],'RESTORE_FAILED')
        self.assertTrue((self.home/'.local/state/openhtpc/refresh-transaction.json').exists())

    def test_prepared_persisted_before_apply(self):
        original_apply=self.runtime.apply
        def apply(output,mode):
            tx=M.read(self.home/'.local/state/openhtpc/refresh-transaction.json')
            self.assertIn(tx['state'],('PREPARED','APPLIED'))
            self.assertEqual(tx['original_mode']['id'],'0')
            return original_apply(output,mode)
        self.runtime.apply=apply
        with M.matching(self.home,runtime=self.runtime,rate=24):pass

    def test_corrupt_recovery_no_switch(self):
        path=self.home/'.local/state/openhtpc/refresh-transaction.json'
        path.parent.mkdir(parents=True,exist_ok=True);path.write_text('broken')
        with M.matching(self.home,runtime=self.runtime,rate=24):pass
        self.assertEqual(self.runtime.calls,[])
        self.assertEqual(path.read_text(),'broken')

    def test_cadence_sample_and_vfr_rejection(self):
        probe={'streams':[dict(codec_type='video',avg_frame_rate='24000/1001',r_frame_rate='24000/1001')]}
        fake_policy=mock.Mock();fake_policy.probe_media.return_value=probe
        frames=[dict(best_effort_timestamp_time=str(round(i*1001/24000,3)),interlaced_frame=0) for i in range(160)]
        with mock.patch.object(M,'load',return_value=fake_policy), mock.patch.object(M.subprocess,'run') as run:
            run.return_value=mock.Mock(returncode=0,stdout=json.dumps({'frames':frames}))
            self.assertAlmostEqual(M.probe_cadence('synthetic.mkv'),24000/1001)
            frames[20]['best_effort_timestamp_time']='3.5'
            run.return_value.stdout=json.dumps({'frames':frames})
            self.assertIsNone(M.probe_cadence('synthetic.mkv'))

    def test_shared_paths(self):
        self.assertIn('policy.play_mpv(home, command, media=media', (ROOT/'payload/openhtpc-play').read_text())
        self.assertIn('policy.play_mpv(home,command,runner=runner', (ROOT/'payload/openhtpc-protected-optical-backend.py').read_text())
        self.assertIn('refresh_runner=(python3 "$INSTALL/openhtpc-refresh-match.py" --)', (ROOT/'payload/openhtpc-play-dvd').read_text())

if __name__=='__main__':unittest.main()
