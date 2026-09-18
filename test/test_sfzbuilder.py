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
    def test_spaces_are_kept(self):
        # generate_sfz writes sample= last, where the value runs to the end of
        # the line, so a space in a name is safe.
        self.assertEqual(sfzbuilder.sanitize_filename("kick drum.wav"), "kick drum.wav")

    def test_surrounding_spaces_are_dropped(self):
        self.assertEqual(sfzbuilder.sanitize_filename("  kick  .wav"), "kick.wav")

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
            "<region> key=36 volume=-3 loop_mode=one_shot sample=01_kick.wav\n"
            "<region> key=37 pitch_keycenter=60 loop_mode=no_loop sample=02_snare.wav\n"
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
        self.assertTrue(os.path.isfile(os.path.join(bank_dir, "Kit.sfz")))
        self.assertTrue(os.path.isfile(os.path.join(bank_dir, "loop.wav")))

        with open(os.path.join(bank_dir, "Kit.sfz")) as fh:
            text = fh.read()
        self.assertIn("key=36 volume=-6 loop_mode=one_shot sample=kick.wav", text)
        self.assertIn("key=37 loop_mode=no_loop sample=loop.wav", text)

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
        with open(os.path.join(bank_dir, "Kit.sfz")) as fh:
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

        with open(os.path.join(self.tmp, "SFZ Instruments", "Kit", "Kit.sfz")) as fh:
            text = fh.read()
        self.assertIn("key=36 loop_mode=one_shot sample=kick.wav", text)
        self.assertIn("key=38 loop_mode=one_shot sample=snare.wav", text)
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


class TestBankFilename(unittest.TestCase):
    # The file selector of a plugin lists an SFZ file by its basename alone, so
    # every bank writing "bank.sfz" gave a column of identical rows.
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self._real = sfzbuilder.USER_FILES_DIR
        sfzbuilder.USER_FILES_DIR = self.tmp

    def tearDown(self):
        sfzbuilder.USER_FILES_DIR = self._real
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _build(self, bank, sample="kick.wav"):
        path = sfzbuilder.create_bank(bank)
        make_wav(os.path.join(path, sample))
        return sfzbuilder.build_bank(bank, 36, [
            {"sample": sample, "source": None, "loop_mode": "one_shot"},
        ])

    def test_the_sfz_carries_the_name_of_its_bank(self):
        self.assertEqual(self._build("Drumkit A")["file"], "Drumkit_A.sfz")
        self.assertEqual(self._build("Foley")["file"], "Foley.sfz")

    def test_two_banks_do_not_share_a_filename(self):
        first = self._build("Drumkit A")["file"]
        second = self._build("Foley")["file"]
        self.assertNotEqual(first, second)

    def test_a_build_removes_an_sfz_it_did_not_write(self):
        path = sfzbuilder.create_bank("Kit")
        with open(os.path.join(path, "OldName.sfz"), "w") as fh:
            fh.write("<region> key=36 sample=gone.wav\n")
        self._build("Kit")
        self.assertEqual(sorted(sfzbuilder.find_sfz_files(path)), ["Kit.sfz"])


class TestSampleNamesWithSpaces(unittest.TestCase):
    # A file that reached the bank by any road but this panel's own upload --
    # the file manager, scp, an unzip -- keeps its name, and could not be saved
    # while build_bank ran that name through sanitize_filename a second time.
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self._real = sfzbuilder.USER_FILES_DIR
        sfzbuilder.USER_FILES_DIR = self.tmp

    def tearDown(self):
        sfzbuilder.USER_FILES_DIR = self._real
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_a_sample_with_a_space_can_be_saved(self):
        path = sfzbuilder.create_bank("Kit")
        make_wav(os.path.join(path, "My Kick.wav"))
        listed = [os.path.basename(f) for f in sfzbuilder.list_bank_samples("Kit")]
        self.assertEqual(listed, ["My Kick.wav"])

        result = sfzbuilder.build_bank("Kit", 36, [
            {"sample": "My Kick.wav", "source": None, "loop_mode": "one_shot"},
        ])
        self.assertEqual(result["count"], 1)
        with open(os.path.join(path, "Kit.sfz")) as fh:
            self.assertIn("sample=My Kick.wav", fh.read())

    def test_the_name_is_last_so_the_space_reads_whole(self):
        # Everything after "sample=" to the end of the line is the name.
        text = sfzbuilder.generate_sfz([
            {"key": 36, "sample": "My Kick.wav", "volume": -6,
             "pitch_keycenter": 60, "loop_mode": "one_shot"},
        ])
        self.assertTrue(text.rstrip("\n").endswith("sample=My Kick.wav"))

    def test_a_name_that_holds_a_path_is_refused(self):
        path = sfzbuilder.create_bank("Kit")
        make_wav(os.path.join(path, "kick.wav"))
        with self.assertRaises(ValueError):
            sfzbuilder.build_bank("Kit", 36, [
                {"sample": "../../kick.wav", "source": None, "loop_mode": "one_shot"},
            ])


class TestRenameAndDelete(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self._real = sfzbuilder.USER_FILES_DIR
        sfzbuilder.USER_FILES_DIR = self.tmp

    def tearDown(self):
        sfzbuilder.USER_FILES_DIR = self._real
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _build(self, bank, sample="kick.wav"):
        path = sfzbuilder.create_bank(bank)
        make_wav(os.path.join(path, sample))
        sfzbuilder.build_bank(bank, 36, [
            {"sample": sample, "source": None, "loop_mode": "one_shot"},
        ])
        return path

    def test_rename_moves_the_directory(self):
        self._build("Kit")
        self.assertEqual(sfzbuilder.rename_bank("Kit", "Drumkit A"), "Drumkit_A")
        self.assertEqual(sfzbuilder.list_banks(), ["Drumkit_A"])

    def test_rename_renames_the_sfz_with_it(self):
        # A plugin's file selector shows the basename, so an .sfz left under
        # the old name would keep showing the old name until the next build.
        self._build("Kit")
        sfzbuilder.rename_bank("Kit", "Drumkit A")
        path = sfzbuilder.bank_dir("Drumkit A")
        self.assertEqual(sfzbuilder.find_sfz_files(path), ["Drumkit_A.sfz"])

    def test_rename_keeps_the_samples_and_the_layout(self):
        self._build("Kit")
        sfzbuilder.rename_bank("Kit", "Foley")
        state = sfzbuilder.load_bank("Foley")
        self.assertEqual(state["base_note"], 36)
        self.assertEqual(state["slots"][0]["sample"], "kick.wav")
        listed = [os.path.basename(f) for f in sfzbuilder.list_bank_samples("Foley")]
        self.assertEqual(listed, ["kick.wav"])

    def test_rename_onto_an_existing_bank_is_refused(self):
        self._build("Kit")
        self._build("Foley")
        with self.assertRaises(ValueError):
            sfzbuilder.rename_bank("Kit", "Foley")
        self.assertEqual(sfzbuilder.list_banks(), ["Foley", "Kit"])

    def test_rename_to_the_same_name_is_not_an_error(self):
        # "Kit A" and "Kit_A" sanitize to the same directory, so this is the
        # path a rename that only changes a space takes.
        self._build("Kit_A")
        self.assertEqual(sfzbuilder.rename_bank("Kit_A", "Kit A"), "Kit_A")
        self.assertEqual(sfzbuilder.list_banks(), ["Kit_A"])

    def test_rename_of_a_bank_that_is_not_there(self):
        with self.assertRaises(ValueError):
            sfzbuilder.rename_bank("Gone", "Kit")

    def test_rename_to_an_empty_name_is_refused(self):
        self._build("Kit")
        with self.assertRaises(ValueError):
            sfzbuilder.rename_bank("Kit", "...")
        self.assertEqual(sfzbuilder.list_banks(), ["Kit"])

    def test_delete_removes_the_bank(self):
        self._build("Kit")
        self._build("Foley")
        self.assertEqual(sfzbuilder.delete_bank("Kit"), "Kit")
        self.assertEqual(sfzbuilder.list_banks(), ["Foley"])

    def test_delete_of_a_bank_that_is_not_there(self):
        with self.assertRaises(ValueError):
            sfzbuilder.delete_bank("Gone")

    def test_delete_does_not_follow_a_link_out_of_the_root(self):
        # rmtree on a name that resolves outside the instruments directory
        # would take the target with it.
        outside = os.path.join(self.tmp, "keep")
        make_wav(os.path.join(outside, "precious.wav"))
        root = sfzbuilder.sfz_instruments_dir()
        os.makedirs(root, exist_ok=True)
        os.symlink(outside, os.path.join(root, "Escape"))
        with self.assertRaises(ValueError):
            sfzbuilder.delete_bank("Escape")
        self.assertTrue(os.path.isfile(os.path.join(outside, "precious.wav")))


class TestNoteCeiling(unittest.TestCase):
    # A free pad needs no note, so free pads at the end must not stop a save.
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self._real = sfzbuilder.USER_FILES_DIR
        sfzbuilder.USER_FILES_DIR = self.tmp
        path = sfzbuilder.create_bank("Kit")
        make_wav(os.path.join(path, "kick.wav"))

    def tearDown(self):
        sfzbuilder.USER_FILES_DIR = self._real
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _slot(self):
        return {"sample": "kick.wav", "source": None, "loop_mode": "one_shot"}

    def test_free_pads_past_the_last_note_are_allowed(self):
        # Base 120 with 8 pads runs to note 127 on the last pad. Only the first
        # holds a sample, so the other seven need nothing.
        slots = [self._slot()] + [None] * 7
        self.assertEqual(sfzbuilder.build_bank("Kit", 126, slots)["count"], 1)

    def test_a_filled_pad_past_the_last_note_is_refused(self):
        slots = [None] * 7 + [self._slot()]
        with self.assertRaises(ValueError):
            sfzbuilder.build_bank("Kit", 126, slots)

    def test_the_last_note_itself_is_allowed(self):
        slots = [None, self._slot()]
        self.assertEqual(sfzbuilder.build_bank("Kit", 126, slots)["count"], 1)


class TestExternalSource(unittest.TestCase):
    # The path of an external sample comes from the browser. Nothing else checks
    # it, so build_bank must, or a bank could copy any readable audio file.
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.files = os.path.join(self.tmp, "user-files")
        os.makedirs(self.files)
        self._real = sfzbuilder.USER_FILES_DIR
        sfzbuilder.USER_FILES_DIR = self.files
        sfzbuilder.create_bank("Kit")

    def tearDown(self):
        sfzbuilder.USER_FILES_DIR = self._real
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _build(self, source):
        return sfzbuilder.build_bank("Kit", 36, [
            {"sample": os.path.basename(source), "source": source,
             "loop_mode": "one_shot"},
        ])

    def test_a_sample_under_user_files_is_copied(self):
        source = os.path.join(self.files, "Loops", "kick.wav")
        make_wav(source)
        self.assertEqual(self._build(source)["count"], 1)
        self.assertTrue(os.path.isfile(
            os.path.join(sfzbuilder.bank_dir("Kit"), "kick.wav")))

    def test_a_sample_from_anywhere_else_is_refused(self):
        source = os.path.join(self.tmp, "elsewhere", "secret.wav")
        make_wav(source)
        with self.assertRaises(ValueError):
            self._build(source)

    def test_a_link_that_points_out_is_refused(self):
        outside = os.path.join(self.tmp, "elsewhere", "secret.wav")
        make_wav(outside)
        link = os.path.join(self.files, "kick.wav")
        os.symlink(outside, link)
        with self.assertRaises(ValueError):
            self._build(link)


class TestExtensionsAgree(unittest.TestCase):
    # model.js keeps its own copy of the list, because the panel removes the
    # files the server would refuse before it sends a batch. The two lists have
    # to say the same thing or the panel drops a file the server accepts.
    def test_the_panel_knows_the_same_audio_types(self):
        import re
        here = os.path.dirname(os.path.abspath(__file__))
        js = os.path.join(here, "..", "html", "js", "app", "sfzbuilder", "model.js")
        with open(js) as fh:
            text = fh.read()
        body = re.search(r"export const AUDIO_EXTENSIONS = \[(.*?)\]", text, re.S)
        self.assertIsNotNone(body, "AUDIO_EXTENSIONS is not in model.js any more")
        found = tuple(re.findall(r"'([^']+)'", body.group(1)))
        self.assertEqual(found, sfzbuilder.AUDIO_EXTENSIONS)
