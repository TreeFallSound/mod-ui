#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2012-2023 MOD Audio UG
# SPDX-License-Identifier: AGPL-3.0-or-later

import os
import shutil
import tempfile
import unittest

from mod import sfzbuilder


def make_wav(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'wb') as fh:
        fh.write(b'RIFF----WAVEfmt ')


class TestSanitize(unittest.TestCase):
    def test_spaces_become_underscores(self):
        self.assertEqual(sfzbuilder.sanitize_filename("kick drum.wav"), "kick_drum.wav")

    def test_sfz_breaking_chars_removed(self):
        self.assertEqual(sfzbuilder.sanitize_filename("kick=1<2#3.wav"), "kick_1_2_3.wav")

    def test_basename_only(self):
        self.assertEqual(sfzbuilder.sanitize_filename("/a/b/x.wav"), "x.wav")

    def test_empty_stem(self):
        self.assertEqual(sfzbuilder.sanitize_filename(".wav"), "sample.wav")

    def test_case_kept(self):
        self.assertEqual(sfzbuilder.sanitize_filename("Snare.WAV"), "Snare.WAV")

    def test_none_input(self):
        self.assertEqual(sfzbuilder.sanitize_filename(None), "sample")

    def test_unique_filename(self):
        used = {"a.wav"}
        self.assertEqual(sfzbuilder.unique_filename("a.wav", used), "a_1.wav")
        used.add("a_1.wav")
        self.assertEqual(sfzbuilder.unique_filename("a.wav", used), "a_2.wav")

    def test_bank_name(self):
        self.assertEqual(sfzbuilder.sanitize_bank_name("My Bank"), "My_Bank")
        with self.assertRaises(ValueError):
            sfzbuilder.sanitize_bank_name("")
        with self.assertRaises(ValueError):
            sfzbuilder.sanitize_bank_name("..")


class TestGenerateSfz(unittest.TestCase):
    def test_golden_output(self):
        regions = [
            {"key": 36, "sample": "01_kick.wav", "volume": -3, "pitch_keycenter": None, "loop_mode": "one_shot"},
            {"key": 37, "sample": "02_snare.wav", "volume": None, "pitch_keycenter": 60, "loop_mode": "no_loop"},
        ]
        expected = (
            "<region> key=36 sample=01_kick.wav volume=-3 loop_mode=one_shot\n"
            "<region> key=37 sample=02_snare.wav pitch_keycenter=60 loop_mode=no_loop\n"
        )
        self.assertEqual(sfzbuilder.generate_sfz(regions), expected)

    def test_volume_formatting(self):
        self.assertEqual(sfzbuilder.fmt_db(-3), "-3")
        self.assertEqual(sfzbuilder.fmt_db(2.5), "2.5")
        self.assertIsNone(sfzbuilder.fmt_db(None))


class TestBuildBank(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.orig_user_files_dir = sfzbuilder.USER_FILES_DIR
        sfzbuilder.USER_FILES_DIR = self.tmp

    def tearDown(self):
        sfzbuilder.USER_FILES_DIR = self.orig_user_files_dir
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_build_with_upload_and_external(self):
        # Simulate an upload: file already in the bank folder.
        make_wav(os.path.join(self.tmp, "SFZ Instruments", "Kit", "kick.wav"))
        # Device source outside the bank folder.
        external = os.path.join(self.tmp, "Audio Samples", "loop.wav")
        make_wav(external)

        slots = [
            {"sample": "kick.wav", "source": None, "volume": -6, "loop_mode": "one_shot"},
            {"sample": "loop.wav", "source": external, "volume": None, "loop_mode": "no_loop"},
        ]
        result = sfzbuilder.build_bank("Kit", 36, slots)

        self.assertTrue(result["ok"])
        self.assertEqual(result["count"], 2)
        bank_dir = os.path.join(self.tmp, "SFZ Instruments", "Kit")
        self.assertTrue(os.path.isfile(os.path.join(bank_dir, "bank.sfz")))
        self.assertTrue(os.path.isfile(os.path.join(bank_dir, "loop.wav")))

        with open(os.path.join(bank_dir, "bank.sfz")) as fh:
            text = fh.read()
        self.assertIn("key=36 sample=kick.wav volume=-6 loop_mode=one_shot", text)
        self.assertIn("key=37 sample=loop.wav loop_mode=no_loop", text)

        # Sidecar tracks the copy.
        with open(os.path.join(bank_dir, "bank.json")) as fh:
            import json
            sidecar = json.load(fh)
        self.assertEqual(sidecar["copied"], {os.path.realpath(external): "loop.wav"})

    def test_rebuild_removes_stale_copy_keeps_upload(self):
        make_wav(os.path.join(self.tmp, "SFZ Instruments", "Kit", "kick.wav"))
        external = os.path.join(self.tmp, "Audio Samples", "loop.wav")
        make_wav(external)
        bank_dir = os.path.join(self.tmp, "SFZ Instruments", "Kit")

        sfzbuilder.build_bank("Kit", 36, [
            {"sample": "kick.wav", "source": None, "loop_mode": "one_shot"},
            {"sample": "loop.wav", "source": external, "loop_mode": "one_shot"},
        ])
        self.assertTrue(os.path.isfile(os.path.join(bank_dir, "loop.wav")))

        # Rebuild without the external sample.
        sfzbuilder.build_bank("Kit", 36, [
            {"sample": "kick.wav", "source": None, "loop_mode": "one_shot"},
        ])
        self.assertFalse(os.path.isfile(os.path.join(bank_dir, "loop.wav")))
        self.assertTrue(os.path.isfile(os.path.join(bank_dir, "kick.wav")))

    def test_duplicate_basenames_get_suffix(self):
        d1 = os.path.join(self.tmp, "Audio Samples", "A")
        d2 = os.path.join(self.tmp, "Audio Samples", "B")
        make_wav(os.path.join(d1, "hit.wav"))
        make_wav(os.path.join(d2, "hit.wav"))

        result = sfzbuilder.build_bank("Kit", 36, [
            {"sample": "hit.wav", "source": os.path.join(d1, "hit.wav"), "loop_mode": "one_shot"},
            {"sample": "hit_1.wav", "source": os.path.join(d2, "hit.wav"), "loop_mode": "one_shot"},
        ])
        bank_dir = os.path.join(self.tmp, "SFZ Instruments", "Kit")
        self.assertTrue(os.path.isfile(os.path.join(bank_dir, "hit.wav")))
        self.assertTrue(os.path.isfile(os.path.join(bank_dir, "hit_1.wav")))
        with open(os.path.join(bank_dir, "bank.sfz")) as fh:
            text = fh.read()
        self.assertIn("sample=hit.wav", text)
        self.assertIn("sample=hit_1.wav", text)
        self.assertEqual(result["count"], 2)

    def test_errors(self):
        make_wav(os.path.join(self.tmp, "Audio Samples", "a.wav"))
        with self.assertRaises(ValueError):
            sfzbuilder.build_bank("Kit", 36, [])
        with self.assertRaises(ValueError):
            sfzbuilder.build_bank("Kit", 128, [{"sample": "a.wav", "source": os.path.join(self.tmp, "Audio Samples", "a.wav")}])
        with self.assertRaises(ValueError):
            sfzbuilder.build_bank("Kit", 120, [{"sample": "a.wav", "source": os.path.join(self.tmp, "Audio Samples", "a.wav")}] * 9)
        with self.assertRaises(ValueError):
            sfzbuilder.build_bank("Kit", 36, [{"sample": "a.wav", "source": os.path.join(self.tmp, "Audio Samples", "a.wav"), "volume": 100}])
        with self.assertRaises(ValueError):
            sfzbuilder.build_bank("Kit", 36, [{"sample": "missing.wav", "source": None, "loop_mode": "one_shot"}])

    def test_device_list_excludes_current_bank(self):
        make_wav(os.path.join(self.tmp, "SFZ Instruments", "Kit", "kick.wav"))
        make_wav(os.path.join(self.tmp, "Audio Samples", "loop.wav"))
        files = sfzbuilder.list_device_samples(exclude_bank="Kit")
        self.assertEqual(files, [os.path.join(self.tmp, "Audio Samples", "loop.wav")])

    def test_bank_roundtrip_listing(self):
        make_wav(os.path.join(self.tmp, "SFZ Instruments", "Kit", "kick.wav"))
        self.assertEqual(sfzbuilder.list_banks(), ["Kit"])
        self.assertEqual(len(sfzbuilder.list_bank_samples("Kit")), 1)
        self.assertEqual(sfzbuilder.list_usb_samples(), [])

    def test_free_pad_keeps_its_note_number(self):
        make_wav(os.path.join(self.tmp, "SFZ Instruments", "Kit", "kick.wav"))
        make_wav(os.path.join(self.tmp, "SFZ Instruments", "Kit", "snare.wav"))

        # Pad 2 is free. The sample on pad 3 must keep key 38, not key 37.
        result = sfzbuilder.build_bank("Kit", 36, [
            {"sample": "kick.wav", "source": None, "loop_mode": "one_shot"},
            None,
            {"sample": "snare.wav", "source": None, "loop_mode": "one_shot"},
        ])
        self.assertEqual(result["count"], 2)

        with open(os.path.join(self.tmp, "SFZ Instruments", "Kit", "bank.sfz")) as fh:
            text = fh.read()
        self.assertIn("key=36 sample=kick.wav", text)
        self.assertIn("key=38 sample=snare.wav", text)
        self.assertNotIn("key=37", text)

    def test_build_rejects_only_free_pads(self):
        sfzbuilder.create_bank("Kit")
        with self.assertRaises(ValueError):
            sfzbuilder.build_bank("Kit", 36, [None, None])


class TestLoadBank(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.orig_user_files_dir = sfzbuilder.USER_FILES_DIR
        sfzbuilder.USER_FILES_DIR = self.tmp

    def tearDown(self):
        sfzbuilder.USER_FILES_DIR = self.orig_user_files_dir
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_layout_survives_a_build(self):
        make_wav(os.path.join(self.tmp, "SFZ Instruments", "Kit", "kick.wav"))
        external = os.path.join(self.tmp, "Audio Samples", "loop.wav")
        make_wav(external)

        sfzbuilder.build_bank("Kit", 40, [
            {"sample": "kick.wav", "source": None, "volume": -6, "loop_mode": "one_shot"},
            None,
            {"sample": "loop.wav", "source": external, "loop_mode": "no_loop"},
        ])

        state = sfzbuilder.load_bank("Kit")
        self.assertEqual(state["base_note"], 40)
        self.assertEqual(len(state["slots"]), 3)
        self.assertEqual(state["slots"][0]["sample"], "kick.wav")
        self.assertEqual(state["slots"][0]["volume"], -6)
        self.assertIsNone(state["slots"][1])
        # The external file is copied into the bank, so the layout is bank-local.
        self.assertEqual(state["slots"][2]["sample"], "loop.wav")
        self.assertEqual(state["slots"][2]["loop_mode"], "no_loop")

    def test_bank_without_a_sidecar(self):
        make_wav(os.path.join(self.tmp, "SFZ Instruments", "Kit", "kick.wav"))
        state = sfzbuilder.load_bank("Kit")
        self.assertEqual(state["base_note"], 36)
        self.assertEqual(state["slots"], [])

    def test_unsafe_name_stays_inside_the_root(self):
        # sanitize_bank_name() contains a traversal instead of rejecting it.
        # The lookup must stay under the SFZ Instruments folder.
        state = sfzbuilder.load_bank("../escape")
        self.assertEqual(state["slots"], [])
        self.assertTrue(sfzbuilder.bank_dir("../escape").startswith(
            sfzbuilder.sfz_instruments_dir() + os.sep))

    def test_empty_name_is_rejected(self):
        with self.assertRaises(ValueError):
            sfzbuilder.load_bank("")


if __name__ == "__main__":
    unittest.main()
