#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2012-2023 MOD Audio UG
# SPDX-License-Identifier: AGPL-3.0-or-later

import os
import re
import shutil
import json

from mod import TextFileFlusher, safe_json_load
from mod.settings import USER_FILES_DIR

# Audio extensions accepted as samples. Same set as FilesList.complete_audiofile_exts.
AUDIO_EXTENSIONS = (
    # through libsndfile
    ".aif", ".aifc", ".aiff", ".au", ".bwf", ".flac", ".htk", ".iff", ".mat4", ".mat5", ".oga", ".ogg", ".opus",
    ".paf", ".pvf", ".pvf5", ".sd2", ".sf", ".snd", ".svx", ".vcc", ".w64", ".wav", ".xi",
    # extra through ffmpeg
    ".3g2", ".3gp", ".aac", ".ac3", ".amr", ".ape", ".mp2", ".mp3", ".mpc", ".wma",
)

LOOP_MODES = ("one_shot", "no_loop")

# The sidecar is internal and never shown, so it keeps one name. The SFZ file is
# shown: the file selector of a plugin lists it by its basename alone, so every
# bank writing "bank.sfz" gave a list of identical rows and you could not tell
# which bank you were choosing. The SFZ file thus carries the name of its bank.
SIDECAR_NAME = "bank.json"
MAX_NOTES = 128


def sfz_instruments_dir():
    return os.path.join(USER_FILES_DIR, "SFZ Instruments")


def is_audio_file(path):
    return os.path.isfile(path) and path.lower().endswith(AUDIO_EXTENSIONS)


def sanitize_filename(name):
    # Keep only safe characters. A space is one of them: generate_sfz puts
    # sample= last on its line, where the value runs to the end of the line, so
    # a space in the name cannot be read as the start of another opcode.
    # The characters = < # are still removed: they break the SFZ parser.
    name = os.path.basename(name or "")
    stem, ext = os.path.splitext(name)
    if not ext and name.startswith("."):
        # Name like ".wav": treat the whole name as the extension.
        stem, ext = "sample", name
    stem = re.sub(r"[^A-Za-z0-9._ -]+", "_", stem).strip("._ ")
    ext = re.sub(r"[^A-Za-z0-9.]", "", ext)
    if not stem:
        stem = "sample"
    return stem + ext


def sanitize_bank_name(name):
    if not name:
        raise ValueError("bank name is empty")
    name = os.path.basename(name)
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip(".")
    if len(name) == 0:
        raise ValueError("bank name is empty")
    if name == "." or name == "..":
        raise ValueError("invalid bank name")
    return name


def unique_filename(name, used):
    if name not in used:
        return name
    stem, ext = os.path.splitext(name)
    i = 1
    while True:
        candidate = "%s_%d%s" % (stem, i, ext)
        if candidate not in used:
            return candidate
        i += 1


def list_audio_files(root, exclude=None):
    if not os.path.isdir(root):
        return []
    excludepath = os.path.realpath(exclude) if exclude else None
    result = []
    for dirpath, dirnames, filenames in os.walk(root):
        realdir = os.path.realpath(dirpath)
        if excludepath and (realdir == excludepath or realdir.startswith(excludepath + os.sep)):
            dirnames[:] = []
            continue
        for name in filenames:
            if is_audio_file(os.path.join(dirpath, name)):
                result.append(os.path.join(dirpath, name))
    result.sort()
    return result


def list_banks():
    root = sfz_instruments_dir()
    if not os.path.isdir(root):
        return []
    return sorted(name for name in os.listdir(root) if os.path.isdir(os.path.join(root, name)))


def bank_dir(name):
    return os.path.join(sfz_instruments_dir(), sanitize_bank_name(name))


def sfz_filename(name):
    # The name a plugin's file selector shows for this bank.
    return sanitize_bank_name(name) + ".sfz"


def find_sfz_files(path):
    # Every .sfz directly in a bank directory. A rename leaves the old one
    # behind, so a build removes what it did not write.
    try:
        return [n for n in os.listdir(path) if n.lower().endswith(".sfz")]
    except OSError:
        return []


def create_bank(name):
    path = bank_dir(name)
    if not os.path.isdir(path):
        os.makedirs(path)
    return path


def _existing_bank_dir(name):
    # A bank directory that is there, resolved and checked against its root.
    # sanitize_bank_name already drops a separator, so this guards the case
    # where the name is a symbolic link that points out of the instruments
    # directory: os.path.isdir follows a link and rmtree would then delete
    # whatever it found.
    root = sfz_instruments_dir()
    path = safe_resolve(root, sanitize_bank_name(name))
    if path == os.path.realpath(root):
        raise ValueError("invalid bank name")
    if not os.path.isdir(path):
        raise ValueError("no such bank: %s" % sanitize_bank_name(name))
    return path


def rename_bank(name, new_name):
    # The .sfz file inside carries the name of the bank (see sfz_filename), so
    # a rename has to rename that file too. Without it a plugin's file selector
    # would go on showing the old name until the next build.
    old_path = _existing_bank_dir(name)
    new_clean = sanitize_bank_name(new_name)
    new_path = os.path.join(sfz_instruments_dir(), new_clean)

    if os.path.realpath(new_path) == old_path:
        # The same bank. A name that sanitizes to what it already is, or a
        # change of nothing at all, is not an error.
        return new_clean
    if os.path.exists(new_path):
        raise ValueError("a bank named %s is already there" % new_clean)

    os.rename(old_path, new_path)

    # The sidecar is not touched: it holds the pad layout and the absolute
    # paths that samples were copied from, and neither depends on the name.
    sfz_name = sfz_filename(new_clean)
    for stale in find_sfz_files(new_path):
        if stale == sfz_name:
            continue
        os.rename(os.path.join(new_path, stale), os.path.join(new_path, sfz_name))
        break
    for stale in find_sfz_files(new_path):
        if stale != sfz_name:
            os.remove(os.path.join(new_path, stale))
    return new_clean


def delete_bank(name):
    # The whole directory goes: the .sfz, the sidecar, and every sample that
    # was uploaded to or copied into the bank. A sample that a pad points at
    # outside the bank is not touched, because it was never in here.
    shutil.rmtree(_existing_bank_dir(name))
    return sanitize_bank_name(name)


def list_bank_samples(name):
    return list_audio_files(bank_dir(name))


def list_device_samples(exclude_bank=None):
    exclude = bank_dir(exclude_bank) if exclude_bank else None
    return list_audio_files(USER_FILES_DIR, exclude=exclude)


def list_usb_samples():
    result = []
    if not os.path.isdir("/media"):
        return result
    for label in sorted(os.listdir("/media")):
        root = os.path.join("/media", label)
        if os.path.isdir(root):
            result.extend(list_audio_files(root))
    result.sort()
    return result


def sample_roots():
    # The places the panel lists samples from. An external sample can only come
    # from one of these, because they are the only ones it shows.
    roots = [USER_FILES_DIR]
    if os.path.isdir("/media"):
        roots.append("/media")
    return [os.path.realpath(r) for r in roots]


def is_allowed_source(path):
    # The path of an external sample arrives from the browser, so it is not
    # checked by anything before this. Without the test below a bank could copy
    # any readable file on the device whose name ends in an audio extension.
    for root in sample_roots():
        if path == root or path.startswith(root + os.sep):
            return True
    return False


def safe_resolve(root, name):
    root = os.path.realpath(root)
    path = os.path.realpath(os.path.join(root, name))
    if path != root and not path.startswith(root + os.sep):
        raise ValueError("path escapes its root")
    return path


def fmt_db(value):
    if value is None:
        return None
    value = round(float(value), 2)
    if value == int(value):
        return str(int(value))
    return str(value)


def generate_sfz(regions):
    # regions: list of dicts with key, sample, volume, pitch_keycenter, loop_mode
    #
    # sample= is written last on each line. The value of an SFZ opcode runs to
    # the next opcode or to the end of the line, so a name that holds a space is
    # read whole only in the last position. Every other opcode here is a number
    # or a word from a fixed set.
    lines = []
    for region in regions:
        line = "<region> key=%d" % int(region["key"])
        if region.get("pitch_keycenter") is not None:
            line += " pitch_keycenter=%d" % int(region["pitch_keycenter"])
        volume = fmt_db(region.get("volume"))
        if volume is not None:
            line += " volume=%s" % volume
        line += " loop_mode=%s" % region["loop_mode"]
        line += " sample=%s" % region["sample"]
        lines.append(line)
    return "\n".join(lines) + "\n"


def validate_slot(slot):
    if "sample" not in slot or not slot["sample"]:
        raise ValueError("slot has no sample")
    volume = slot.get("volume")
    if volume is not None:
        volume = float(volume)
        if volume < -144 or volume > 48:
            raise ValueError("volume out of range")
        slot["volume"] = volume
    pitch = slot.get("pitch_keycenter")
    if pitch is not None:
        pitch = int(pitch)
        if pitch < 0 or pitch > 127:
            raise ValueError("pitch_keycenter out of range")
        slot["pitch_keycenter"] = pitch
    loop_mode = slot.get("loop_mode", "one_shot")
    if loop_mode not in LOOP_MODES:
        raise ValueError("invalid loop_mode")
    slot["loop_mode"] = loop_mode
    return slot


def load_bank(name):
    # Returns the saved pad layout so the UI can open a bank again for edit.
    path = os.path.join(bank_dir(name), SIDECAR_NAME)
    data = safe_json_load(path, dict)
    slots = data.get("slots")
    if not isinstance(slots, list):
        slots = []
    base_note = data.get("base_note")
    try:
        base_note = int(base_note)
    except (TypeError, ValueError):
        base_note = 36
    if base_note < 0 or base_note > 127:
        base_note = 36
    return {
        "base_note": base_note,
        "slots": [slot if isinstance(slot, dict) else None for slot in slots],
    }


def build_bank(name, base_note, slots):
    # The bank folder is the source of truth.
    # Uploads land there directly. External files (device, USB) are copied
    # there. The sidecar tracks the copies so a rebuild can remove stale ones.
    name = sanitize_bank_name(name)
    if base_note is None:
        raise ValueError("base note is missing")
    base_note = int(base_note)
    if base_note < 0 or base_note > 127:
        raise ValueError("base note out of range")
    if not slots:
        raise ValueError("no slots")
    # slots is pad-aligned: a None entry is a free pad and keeps its note number.
    if not any(slot for slot in slots):
        raise ValueError("no slots")
    # Only a pad that holds a sample needs a note. A bank of eight pads with a
    # sample on the first one is a bank the panel offers at any base note, and
    # refusing it because seven empty pads run past 127 was refusing to save
    # work that is there.
    last_filled = max(i for i, slot in enumerate(slots) if slot)
    if base_note + last_filled >= MAX_NOTES:
        raise ValueError("pad %d would need note %d, and the last note is %d"
                         % (last_filled + 1, base_note + last_filled, MAX_NOTES - 1))

    path = create_bank(name)
    sidecar_path = os.path.join(path, SIDECAR_NAME)
    old_copied = safe_json_load(sidecar_path, dict).get("copied", {})

    used = set(os.listdir(path))
    claimed = set()
    new_copied = {}
    regions = []

    layout = []
    for i, slot in enumerate(slots):
        if not slot:
            layout.append(None)
            continue
        key = base_note + i
        validate_slot(slot)
        source = slot.get("source")
        if source:
            src = os.path.realpath(source)
            if not is_allowed_source(src):
                raise ValueError("sample is not in a place the panel reads: %s" % source)
            if not is_audio_file(src):
                raise ValueError("source is not an audio file: %s" % src)
            dest = old_copied.get(src)
            if not dest or dest in claimed or not is_audio_file(os.path.join(path, dest)):
                dest = unique_filename(sanitize_filename(os.path.basename(src)), used)
            shutil.copy2(src, os.path.join(path, dest))
            new_copied[src] = dest
            claimed.add(dest)
            used.add(dest)
        else:
            # The name is already the name of a file in the bank, so it is used
            # as it is. Running it through sanitize_filename again renamed the
            # file that the panel had just listed -- "My Kick.wav" was looked up
            # as "My_Kick.wav" -- and no sample that came from anywhere but this
            # panel's own upload could be saved.
            dest = slot["sample"]
            if dest != os.path.basename(dest):
                raise ValueError("sample name holds a path: %s" % dest)
            resolved = safe_resolve(path, dest)
            if dest in claimed:
                raise ValueError("sample name conflict: %s" % dest)
            if not is_audio_file(resolved):
                raise ValueError("sample not found in bank: %s" % dest)

        regions.append({
            "key": key,
            "sample": dest,
            "volume": slot.get("volume"),
            "pitch_keycenter": slot.get("pitch_keycenter"),
            "loop_mode": slot["loop_mode"],
        })
        # The layout keeps the bank-local name, so a reload needs no source path.
        layout.append({
            "sample": dest,
            "volume": slot.get("volume"),
            "pitch_keycenter": slot.get("pitch_keycenter"),
            "loop_mode": slot["loop_mode"],
        })

    # Remove stale copies. Untracked uploads stay untouched.
    for src, dest in old_copied.items():
        if src not in new_copied:
            stale = os.path.join(path, dest)
            if is_audio_file(stale):
                os.remove(stale)
                used.discard(dest)

    sfz_name = sfz_filename(name)
    sfz_path = os.path.join(path, sfz_name)
    with TextFileFlusher(sfz_path) as fh:
        fh.write(generate_sfz(regions))

    # An .sfz under an earlier name would else stay in the file selector of a
    # plugin next to the one this build wrote.
    for stale in find_sfz_files(path):
        if stale != sfz_name:
            os.remove(os.path.join(path, stale))

    with TextFileFlusher(sidecar_path) as fh:
        json.dump({
            "copied": new_copied,
            "base_note": base_note,
            "slots": layout,
        }, fh, indent=2)

    return {
        "ok": True,
        "name": name,
        "path": sfz_path,
        "file": sfz_name,
        "count": len(regions),
    }
