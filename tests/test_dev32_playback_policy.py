#!/usr/bin/env python3
"""Dev32 playback policy, provenance and signing contract tests.

Copyright 2026 Steve Dehanne
SPDX-License-Identifier: Apache-2.0

Part of the OPENHTPC project.
Original project by Steve Dehanne.
"""
from __future__ import annotations

import importlib.machinery
import importlib.util
import json
import pathlib
import shutil
import subprocess
import tempfile
import unittest
import os

ROOT = pathlib.Path(__file__).resolve().parents[1]
PAYLOAD = ROOT / "payload"


def load(name: str, path: pathlib.Path):
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(name, loader)
    module = importlib.util.module_from_spec(spec); loader.exec_module(module)
    return module


policy = load("dev32_policy", PAYLOAD / "openhtpc-playback-policy.py")


def stream(kind: str, language: str = "", title: str = "", default: int = 0, forced: int = 0) -> dict:
    return {"codec_type": kind, "tags": {"language": language, "title": title}, "disposition": {"default": default, "forced": forced}}


class PlaybackPreferences(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.home = pathlib.Path(self.temp.name)
        root = self.home / ".config/openhtpc"; root.mkdir(parents=True)
        (root / "user-config.json").write_text(json.dumps({"schema":1,"configuration_completed":True,"local_media_sources":["/media"],"tmdb":{"configured":False}}))

    def tearDown(self): self.temp.cleanup()

    def test_defaults_and_invalid_fallback(self):
        self.assertEqual(policy.read_preferences(self.home), policy.DEFAULTS)
        path = policy.config_path(self.home); data = json.loads(path.read_text()); data.update({"presentation_mode":"BAD","audio_language_policy":4,"subtitle_policy":"BAD"}); path.write_text(json.dumps(data))
        self.assertEqual(policy.read_preferences(self.home), policy.DEFAULTS)

    def test_persistence_and_existing_config_preserved(self):
        policy.write_preference(self.home, "presentation_mode", "CINEMA_AUTO")
        policy.write_preference(self.home, "audio_language_policy", "FR")
        policy.write_preference(self.home, "subtitle_policy", "FR_FORCED")
        data = json.loads(policy.config_path(self.home).read_text())
        self.assertEqual(data["local_media_sources"], ["/media"])
        self.assertEqual(policy.read_preferences(self.home), {"presentation_mode":"CINEMA_AUTO","audio_language_policy":"FR","subtitle_policy":"FR_FORCED"})
        self.assertEqual(json.loads((self.home/".config/openhtpc/video-profile.json").read_text())["active_profile"], "CINEMA_AUTO")

    def test_rc2_video_profile_migrates_without_write(self):
        (self.home/".config/openhtpc/video-profile.json").write_text(json.dumps({"active_profile":"CINEMA_AUTO"}))
        self.assertEqual(policy.read_preferences(self.home)["presentation_mode"], "CINEMA_AUTO")


class AudioPolicy(unittest.TestCase):
    def test_single_fr_and_fr_en(self):
        self.assertEqual(policy.choose_audio("FR", {"streams":[stream("audio","fra") ]})["resolved"], "AID_1")
        self.assertEqual(policy.choose_audio("FR", {"streams":[stream("audio","eng"),stream("audio","fr")]})["resolved"], "AID_2")

    def test_vff_before_plain_and_vfq(self):
        probe={"streams":[stream("audio","fr","VFQ"),stream("audio","fra","Français"),stream("audio","fre","TrueFrench VFF")]}
        self.assertEqual(policy.choose_audio("FR",probe)["resolved"],"AID_3")

    def test_secondary_metadata_and_no_fr(self):
        self.assertEqual(policy.choose_audio("FR",{"streams":[stream("audio","und","French VFF") ]})["resolved"],"AID_1")
        self.assertEqual(policy.choose_audio("FR",{"streams":[stream("audio","eng") ]})["resolved"],"MPV_DEFAULT")

    def test_default_track(self):
        result=policy.choose_audio("DEFAULT",{"streams":[stream("audio","fr"),stream("audio","eng",default=1)]})
        self.assertEqual(result["mpv_args"],["--aid=2"])


class SubtitlePolicy(unittest.TestCase):
    def test_forced_precedes_full(self):
        probe={"streams":[stream("subtitle","fr","Français complet"),stream("subtitle","fra","Français",forced=1)]}
        self.assertEqual(policy.choose_subtitle("FR_FORCED",probe)["resolved"],"SID_2")
        self.assertEqual(policy.choose_subtitle("FR_FULL",probe)["resolved"],"SID_1")

    def test_forced_title_secondary(self):
        probe={"streams":[stream("subtitle","fre","Français forcé")]}
        self.assertEqual(policy.choose_subtitle("FR_FORCED",probe)["resolved"],"SID_1")

    def test_no_forced_never_uses_full(self):
        result=policy.choose_subtitle("FR_FORCED",{"streams":[stream("subtitle","fr","Complet")]})
        self.assertEqual(result["resolved"],"NONE");self.assertEqual(result["reason"],"no_qualified_forced_track");self.assertEqual(result["mpv_args"],["--sid=no"])

    def test_full_avoids_forced_only_and_no_fr(self):
        self.assertEqual(policy.choose_subtitle("FR_FULL",{"streams":[stream("subtitle","fr","Forced",forced=1)]})["resolved"],"NONE")
        self.assertEqual(policy.choose_subtitle("FR_FULL",{"streams":[stream("subtitle","eng","Full")]})["resolved"],"NONE")

    def test_auto_and_off(self):
        self.assertEqual(policy.choose_subtitle("AUTO",{})["mpv_args"],[])
        self.assertEqual(policy.choose_subtitle("OFF",{})["mpv_args"],["--sid=no"])


class EndToEndContract(unittest.TestCase):
    def test_player_passes_policy_osd_and_structured_log(self):
        source=(PAYLOAD/"openhtpc-play").read_text()
        for marker in ("*policy_args", "--osd-playing-msg=", '"PLAYBACK_POLICY"', "presentation_requested", "audio_resolved", "subtitle_resolved"):
            self.assertIn(marker,source)
        dvd=(PAYLOAD/"openhtpc-play-dvd").read_text()
        for marker in ('"${policy_args[@]}"', "--osd-playing-msg=", "PLAYBACK_POLICY", "resolved_presentation"):
            self.assertIn(marker,dvd)

    def test_auto_local_resolves_qualified_pure(self):
        with tempfile.TemporaryDirectory() as value:
            home=pathlib.Path(value);policy.write_preference(home,"presentation_mode","CINEMA_AUTO")
            result=policy.resolve(home,probe={"streams":[]})
            self.assertEqual((result["presentation"]["requested"],result["presentation"]["resolved"]),("CINEMA_AUTO","PURE"))
            self.assertIn("Mode vidéo appliqué : PURE",policy.osd_text(result))

    def test_real_dispatcher_command_reaches_mpv(self):
        with tempfile.TemporaryDirectory() as value:
            base=pathlib.Path(value);home=base/"home";media_root=home/"media";media_root.mkdir(parents=True);media=media_root/"fixture.mkv";media.touch()
            config=home/".config/openhtpc";config.mkdir(parents=True);runtime=config/"pure.conf";runtime.write_text("vo=null\n")
            (config/"profile.json").write_text(json.dumps({"runtime":{"status":"ready"},"runtime_profiles":{"profiles":{"PURE":{"generation_status":"generated","config_path":str(runtime)}}}}))
            (config/"user-config.json").write_text(json.dumps({"schema":1,"local_media_sources":[str(media_root)],"presentation_mode":"CINEMA_AUTO","audio_language_policy":"FR","subtitle_policy":"FR_FORCED"}))
            fake=base/"bin";fake.mkdir();arglog=base/"mpv-args"
            ffprobe=fake/"ffprobe";ffprobe.write_text('#!/bin/sh\nprintf \'%s\\n\' \'{"streams":[{"codec_type":"audio","tags":{"language":"eng"},"disposition":{}},{"codec_type":"audio","tags":{"language":"fra","title":"TrueFrench VFF"},"disposition":{}},{"codec_type":"subtitle","tags":{"language":"fr","title":"Français"},"disposition":{"forced":1}}]}\'\n');ffprobe.chmod(0o755)
            mpv=fake/"mpv";mpv.write_text(f'#!/bin/sh\nprintf "%s\\n" "$@" >"{arglog}"\nfor arg in "$@";do case "$arg" in --log-file=*) printf "Video: fixture\\nAudio: fixture\\nVO: null\\nAO: null\\n" >"${{arg#--log-file=}}";;esac;done\n');mpv.chmod(0o755)
            env={**os.environ,"OPENHTPC_HOME":str(home),"OPENHTPC_INSTALL_DIR":str(PAYLOAD),"OPENHTPC_FLEX_RETAINED":"1","PATH":str(fake)+os.pathsep+os.environ["PATH"]}
            result=subprocess.run([str(PAYLOAD/"openhtpc-play"),str(media)],env=env,text=True,capture_output=True)
            self.assertEqual(result.returncode,0,result.stderr)
            raw_args=arglog.read_text();args=raw_args.splitlines();self.assertIn("--aid=2",args);self.assertIn("--sid=1",args);self.assertIn("--osd-playing-msg=Mode vidéo appliqué : PURE\nAudio : Français\nSous-titres : Français forcés",raw_args)
            records=[json.loads(line) for line in (home/".local/state/openhtpc/runtime.log").read_text().splitlines()]
            event=next(item for item in records if item["event"]=="PLAYBACK_POLICY");self.assertEqual((event["audio_resolved"],event["subtitle_resolved"]),("AID_2","SID_1"))

    def test_ui_has_all_couch_options(self):
        session=load("dev32_session",PAYLOAD/"openhtpc-session-engine.py")
        with tempfile.TemporaryDirectory() as value:
            root=pathlib.Path(value);home=root/"home";install=root/"install";install.mkdir();shutil.copy2(PAYLOAD/"openhtpc-playback-policy.py",install/"openhtpc-playback-policy.py")
            sections="\n".join(session._playback_policy_sections(home,install,pathlib.Path("icon.png")))
            for label in ("PURE","CINÉMA AUTO","FRANÇAIS","PISTE PAR DÉFAUT","DÉSACTIVÉS","FRANÇAIS FORCÉS","FRANÇAIS COMPLETS"):
                self.assertIn(label,sections)

    def test_update_and_setup_preserve_preferences(self):
        update=(ROOT/"update.sh").read_text();self.assertNotIn("user-config.json",update)
        setup=load("dev32_setup",PAYLOAD/"openhtpc-initial-setup.py")
        with tempfile.TemporaryDirectory() as value:
            home=pathlib.Path(value);root=home/".config/openhtpc";root.mkdir(parents=True);(root/"user-config.json").write_text(json.dumps({**policy.DEFAULTS,"presentation_mode":"CINEMA_AUTO"}))
            setup.save(home,[],None);self.assertEqual(json.loads((root/"user-config.json").read_text())["presentation_mode"],"CINEMA_AUTO")


class ProvenanceAndSigning(unittest.TestCase):
    def test_required_provenance_and_no_private_key(self):
        for name in ("LICENSE","NOTICE","THIRD_PARTY_NOTICES.md","AUTHORS.md","SIGNING.md"): self.assertTrue((ROOT/name).is_file())
        forbidden=(b"BEGIN OPENSSH "+b"PRIVATE KEY",b"BEGIN "+b"PRIVATE KEY",b"github_"+b"pat_")
        for path in ROOT.rglob("*"):
            if not path.is_file() or ".git" in path.parts or "artifacts" in path.parts or "__pycache__" in path.parts: continue
            data=path.read_bytes()
            self.assertFalse(any(value in data for value in forbidden),str(path))
            self.assertFalse(path.name.startswith("openhtpc-release-signing") and path.suffix != ".pub")
        for path in (PAYLOAD/"assets/shaders").iterdir():
            if path.is_file(): self.assertNotIn(b"Copyright 2026 Steve Dehanne",path.read_bytes())

    @unittest.skipUnless(shutil.which("ssh-keygen"),"ssh-keygen unavailable")
    def test_ephemeral_signing_valid_and_tamper_failures(self):
        with tempfile.TemporaryDirectory() as value:
            tmp=pathlib.Path(value);key=tmp/"test-key";wrong=tmp/"wrong-key";archive=tmp/"candidate.tar.gz";archive.write_bytes(b"qualified fixture")
            subprocess.run(["ssh-keygen","-q","-t","ed25519","-N","","-f",str(key)],check=True)
            subprocess.run(["ssh-keygen","-q","-t","ed25519","-N","","-f",str(wrong)],check=True)
            sign=subprocess.run([str(ROOT/"tools/sign-release.sh"),str(archive),str(key)],text=True,capture_output=True)
            self.assertEqual(sign.returncode,0,sign.stderr)
            verify=[str(ROOT/"tools/verify-release.sh"),str(archive),str(archive)+".sha256",str(archive)+".sig",str(key)+".pub"]
            self.assertEqual(subprocess.run(verify,capture_output=True).returncode,0)
            original=archive.read_bytes();archive.write_bytes(original+b"x");self.assertNotEqual(subprocess.run(verify,capture_output=True).returncode,0);archive.write_bytes(original)
            bad_sha=tmp/"bad.sha256";bad_sha.write_text("0"*64+"  candidate.tar.gz\n");self.assertNotEqual(subprocess.run([verify[0],verify[1],str(bad_sha),verify[3],verify[4]],capture_output=True).returncode,0)
            self.assertNotEqual(subprocess.run([*verify[:-1],str(wrong)+".pub"],capture_output=True).returncode,0)
            signature=pathlib.Path(str(archive)+".sig");raw=signature.read_bytes();signature.write_bytes(raw[:-2]+b"xx");self.assertNotEqual(subprocess.run(verify,capture_output=True).returncode,0)

    def test_signer_refuses_repository_private_key(self):
        candidate=ROOT/"test-private-key"
        try:
            candidate.write_text("not a key")
            result=subprocess.run([str(ROOT/"tools/sign-release.sh"),str(ROOT/"README.md"),str(candidate)],capture_output=True,text=True)
            self.assertEqual(result.returncode,3);self.assertIn("INSIDE_REPOSITORY_REFUSED",result.stderr)
        finally: candidate.unlink(missing_ok=True)


if __name__ == "__main__": unittest.main()
