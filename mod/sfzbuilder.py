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

SFZ_NAME = "bank.sfz"
SIDECAR_NAME = "bank.json"
MAX_NOTES = 128


def sfz_instruments_dir():
    return os.path.join(USER_FILES_DIR, "SFZ Instruments")


def is_audio_file(path):
    return os.path.isfile(path) and path.lower().endswith(AUDIO_EXTENSIONS)


def sanitize_filename(name):
    # Keep only safe characters. Spaces become underscores.
    # The characters = < # are removed: they break the SFZ parser.
    name = os.path.basename(name or "")
    stem, ext = os.path.splitext(name)
    if not ext and name.startswith("."):
        # Name like ".wav": treat the whole name as the extension.
        stem, ext = "sample", name
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", stem).strip("._")
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


def create_bank(name):
    path = bank_dir(name)
    if not os.path.isdir(path):
        os.makedirs(path)
    return path


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
    lines = []
    for region in regions:
        line = "<region> key=%d sample=%s" % (int(region["key"]), region["sample"])
        if region.get("pitch_keycenter") is not None:
            line += " pitch_keycenter=%d" % int(region["pitch_keycenter"])
        volume = fmt_db(region.get("volume"))
        if volume is not None:
            line += " volume=%s" % volume
        line += " loop_mode=%s" % region["loop_mode"]
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
    if base_note + len(slots) > MAX_NOTES:
        raise ValueError("too many slots for the base note")

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
            dest = sanitize_filename(slot["sample"])
            if dest in claimed:
                raise ValueError("sample name conflict: %s" % dest)
            if not is_audio_file(os.path.join(path, dest)):
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

    sfz_path = os.path.join(path, SFZ_NAME)
    with TextFileFlusher(sfz_path) as fh:
        fh.write(generate_sfz(regions))

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
        "file": SFZ_NAME,
        "count": len(regions),
    }
