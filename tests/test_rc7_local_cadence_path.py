"""Real local path resolution -> policy.play_mpv -> shared refresh cadence.
Copyright 2026 Steve Dehanne
SPDX-License-Identifier: Apache-2.0
Part of the OPENHTPC project.
Original project by Steve Dehanne.
"""
import importlib.machinery
import importlib.util
import json
import pathlib
import tempfile
import unittest
from unittest import mock
from tests.test_rc7_refresh_matching import M,P,FakeRuntime,snapshot,ROOT
loader=importlib.machinery.SourceFileLoader('local_cadence',str(ROOT/'payload/openhtpc-play'))
spec=importlib.util.spec_from_loader('local_cadence',loader)
LOCAL=importlib.util.module_from_spec(spec);loader.exec_module(LOCAL)

class LocalCadenceTests(unittest.TestCase):
    def test_real_local_boundary_paths_and_packet_drain(self):
        for name in ('film.mkv',"L'été d'un film 23.mkv",'300 Rise of an Empire (2014).mkv'):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as tmp:
                home=pathlib.Path(tmp);root=home/'Movies';root.mkdir();path=root/name;path.write_bytes(b'synthetic')
                P.write_preference(home,'refresh_matching','AUTO')
                config=home/'.config/openhtpc/user-config.json';data=json.loads(config.read_text());data['local_media_sources']=[str(root)];config.write_text(json.dumps(data))
                manifest=home/'.local/state/openhtpc/media-actions/current.json';manifest.parent.mkdir(parents=True)
                manifest.write_text(json.dumps({'sources':[{'source_id':LOCAL.source_id(root),'configured_path':str(root)}]}))
                media,source=LOCAL.resolve_media_request(home,LOCAL.source_id(root),name,'synthetic-page')
                self.assertEqual(media,path.resolve())
                frames=[{'best_effort_timestamp_time':str(round(i*1001/24000,3)),'interlaced_frame':0} for i in range(160)]
                # Real observed packet-boundary drain artifact, outside the trusted prefix.
                frames[-1]['best_effort_timestamp_time']=str(round(160*1001/24000,3))
                runtime=FakeRuntime(snapshot());probe_policy=mock.Mock()
                probe_policy.probe_media.return_value={'streams':[{'codec_type':'video','avg_frame_rate':'24000/1001','r_frame_rate':'24000/1001','field_order':'progressive'}]}
                fake_spec=mock.Mock();fake_spec.loader.exec_module.return_value=None
                def player(command,**kwargs):
                    self.assertEqual(runtime.value['active_output']['current_mode_id'],'1')
                    return mock.Mock(returncode=0)
                with mock.patch.object(P.importlib.util,'spec_from_file_location',return_value=fake_spec), mock.patch.object(P.importlib.util,'module_from_spec',return_value=M), mock.patch.object(M,'load',return_value=probe_policy), mock.patch.object(M,'Runtime',return_value=runtime), mock.patch.object(M.subprocess,'run',return_value=mock.Mock(returncode=0,stdout=json.dumps({'frames':frames}))) as probe:
                    P.play_mpv(home,['mpv',str(media)],media=media,runner=player,refresh_dispatch_id='dispatch-path-proof')
                    self.assertEqual(probe.call_args.args[0][-1],str(path))
                record=M.read(home/'.local/state/openhtpc/refresh-match-last.json')
                self.assertEqual(record['cadence_rational'],'24000/1001')
                self.assertEqual(record['match_decision'],'MATCH_AVAILABLE')
                self.assertTrue(record['switch_verified']);self.assertTrue(record['restore_verified'])
                self.assertTrue(record['playback_started']);self.assertEqual(record['final_mode_id'],'0')
                self.assertEqual(record['dispatch_id'],'dispatch-path-proof')
                self.assertEqual(record['frames_validated'],128)
                self.assertEqual(len(list((home/'.local/state/openhtpc/refresh-attempts').glob('*.json'))),1)

    def test_interior_discontinuity_still_rejected(self):
        frames=[{'best_effort_timestamp_time':str(round(i*1001/24000,3)),'interlaced_frame':0} for i in range(160)]
        frames[100]['best_effort_timestamp_time']='8.5'
        p=mock.Mock();p.probe_media.return_value={'streams':[{'codec_type':'video','avg_frame_rate':'24000/1001','r_frame_rate':'24000/1001'}]}
        with mock.patch.object(M,'load',return_value=p),mock.patch.object(M.subprocess,'run',return_value=mock.Mock(returncode=0,stdout=json.dumps({'frames':frames}))):
            evidence=M.probe_cadence_evidence(pathlib.Path('/synthetic/file.mkv'))
        self.assertIsNone(evidence['cadence_fps']);self.assertEqual(evidence['cadence_reason'],'TIMESTAMP_DISCONTINUITY')

if __name__=='__main__':unittest.main()
