#!/usr/bin/env python3
"""O1 deterministic physical optical detection and playback separation."""
import importlib.util, json, pathlib, subprocess, tempfile, unittest

ROOT=pathlib.Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("o1_optical",ROOT/"payload/openhtpc-optical.py")
optical=importlib.util.module_from_spec(spec); spec.loader.exec_module(optical)

def completed(command,code=0,out=""):
    return subprocess.CompletedProcess(command,code,out,"")

def runner(*,fstype="udf",media=True,bd=False,dvd=False,bdinfo=False):
    def invoke(command):
        if command[0]=="lsblk":
            block={"name":"fixture","type":"rom","fstype":fstype,"label":"MISLEADING_UHD_LABEL","mountpoints":[]}
            return completed(command,out=json.dumps({"blockdevices":[block]}))
        if command[0]=="udevadm":
            props=["ID_CDROM=1"]
            if media: props.append("ID_CDROM_MEDIA=1")
            if bd: props.append("ID_CDROM_MEDIA_BD=1")
            return completed(command,out="\n".join(props)+"\n")
        if command[0]=="lsdvd":
            return completed(command,out="<lsdvd><track/></lsdvd>" if dvd else "",code=0 if dvd else 1)
        return completed(command,code=1)
    return invoke

class Detection(unittest.TestCase):
    def probe(self,*,header=None,**values):
        return optical.probe_device(pathlib.Path("/dev/fixture"),runner(**values),lambda block:(header,"BDMV/index.bdmv") if header else (None,None))

    def test_drive_no_media(self):
        state=self.probe(fstype="",media=False)
        self.assertEqual(state["canonical_state"],"DRIVE_PRESENT_NO_MEDIA")

    def test_dvd_detection_and_core_playback_non_regression(self):
        state=self.probe(fstype="udf",dvd=True)
        self.assertEqual((state["canonical_state"],state["state"]),("DVD_VIDEO","DVD"))
        self.assertEqual((state["playback_provider"],state["playable"]),("core",True))

    def test_bluray_video_requires_plugin(self):
        state=self.probe(bd=True,header="INDX0200")
        self.assertEqual(state["canonical_state"],"BLURAY_VIDEO")
        self.assertEqual((state["playback_provider"],state["playable"]),("plugin:bluray",False))

    def test_uhd_requires_unencrypted_version_0300_evidence(self):
        state=self.probe(bd=True,header="INDX0300")
        self.assertEqual((state["canonical_state"],state["uhd_status"]),("UHD_BLURAY_VIDEO","CONFIRMED"))
        self.assertEqual((state["playback_provider"],state["playable"]),("plugin:uhd",False))

    def test_ambiguous_bluray_family_is_truthful(self):
        state=self.probe(bd=True,header="INDX0400")
        self.assertEqual((state["canonical_state"],state["uhd_status"]),("BLURAY_FAMILY","UNKNOWN"))
        self.assertFalse(state["playable"])

    def test_unreadable_bluray_structure_does_not_guess_uhd(self):
        state=self.probe(bd=True)
        self.assertEqual((state["canonical_state"],state["uhd_status"]),("BLURAY_FAMILY","UNKNOWN"))

    def test_unknown_optical_media(self):
        self.assertEqual(self.probe(fstype="vfat")["canonical_state"],"UNKNOWN_OPTICAL_MEDIA")

    def test_label_bdxl_and_uhd_are_never_classifiers(self):
        state=self.probe(bd=True)
        self.assertNotEqual(state["canonical_state"],"UHD_BLURAY_VIDEO")

    def test_tmdb_and_plugin_absence_do_not_block_detection(self):
        state=self.probe(bd=True,header="INDX0200")
        self.assertTrue(state["detected"]); self.assertEqual(state["playback_status"],"PLUGIN_REQUIRED")

class Transitions(unittest.TestCase):
    def test_no_drive(self):
        with tempfile.TemporaryDirectory() as raw:
            self.assertEqual(optical.current_state(sys_block=pathlib.Path(raw))["canonical_state"],"NO_OPTICAL_DRIVE")

    def test_eject_transition_replaces_media_identity(self):
        with tempfile.TemporaryDirectory() as raw:
            home=pathlib.Path(raw)
            optical.publish(home,{"state":"DVD","canonical_state":"DVD_VIDEO","device":"/dev/x","disc_id":"secret"},generation=1)
            value=optical.publish(home,optical._state("DRIVE_PRESENT_NO_MEDIA","/dev/x","EMPTY"),generation=2)
            self.assertNotIn("disc_id",value); self.assertEqual(value["canonical_state"],"DRIVE_PRESENT_NO_MEDIA")

    def test_device_removal_prevents_stale_card(self):
        with tempfile.TemporaryDirectory() as raw:
            home=pathlib.Path(raw)
            optical.publish(home,{"state":"BLURAY","canonical_state":"BLURAY_VIDEO","device":"/dev/x"},generation=1)
            value=optical.publish(home,optical._state("NO_OPTICAL_DRIVE",None,"NO_DRIVE",drives=[]),generation=2)
            self.assertIsNone(value["device"]); self.assertEqual(value["canonical_state"],"NO_OPTICAL_DRIVE")

    def test_bounded_bd_to_confirmed_uhd_refreshes_ui_generation(self):
        family=optical._state("BLURAY_FAMILY","/dev/x","BLURAY",uhd_status="UNKNOWN")
        uhd=optical._state("UHD_BLURAY_VIDEO","/dev/x","UHD",uhd_status="CONFIRMED")
        self.assertNotEqual(optical.ui_state_hash(family),optical.ui_state_hash(uhd))

if __name__=="__main__": unittest.main()
