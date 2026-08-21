# SFZ Sound-Bank Builder — Implementation Plan

## 1. Purpose

This document defines the SFZ sound-bank builder for mod-ui.

The builder is a new panel in mod-ui. It lets the user do these tasks:

- Upload audio files to the device.
- Import audio files from a USB stick.
- Add sample-files that already exist on the device.
- Arrange the audio files into pad-slots.
- Set the pad-count and the base-note.
- Set per-sample options (gain, root-note, loop-mode).
- Listen to a sample in the browser.
- Build an SFZ file.
- Load the SFZ file into sfizz.

The output of the builder is one SFZ file and the sample-files that it uses.

sfizz (the sample player on the device) reads the SFZ file. The user triggers the samples with MIDI pads. Each pad plays one sample. The pads send MIDI-notes from a base-note upward.

This document does not implement the feature. It describes the design and the build steps.

## 2. Terms and Definitions

| Term | Definition |
|---|---|
| SFZ file | A text-file that maps sample-files to MIDI-notes. |
| sound-bank | A folder that contains sample-files and one SFZ file. |
| pad-slot | One position in the sound-bank. One pad-slot maps to one MIDI-note. |
| base-note | The MIDI-note of the first pad-slot. |
| pad-count | The number of pad-slots in the sound-bank. |
| sample-file | An audio file (for example .wav) that one pad-slot uses. |
| mod-ui | The web-interface of the pi-Stomp device. |
| sfizz | The SFZ sample player on the device (version 1.2.3). |
| browsepy | The directory file-browser on the device (port 8081). |
| MIDI | Musical Instrument Digital Interface. |
| USB | Universal Serial Bus. |

## 3. Background

The device runs mod-ui on port 80. mod-ui is the pedalboard editor. It runs as the user pistomp.

All user files live under `/home/pistomp/data/user-files`. The mod-ui service sets this path with the variable `MOD_USER_FILES_DIR`. The folder contains category folders. Each category folder maps to one file-type. The `SFZ Instruments` folder maps to the file-type `sfz`.

The mod-ui endpoint `/files/list` lists files by file-type. It walks the category folder recursively. It returns the full path and the file-name for each file. It does not return audio metadata (duration, sample-rate, loop-points). It has no folder-tree endpoint.

The sfizz plugin has a file parameter named `sfzfile`. The pi-Stomp fork adds the annotation `mod:fileTypes "sfz"` to this parameter. Thus, any `.sfz` file under `SFZ Instruments` appears in the sfizz file-picker. The load side needs no change.

browsepy runs on port 8081. It is a directory file-browser with upload. mod-ui shows it in the File Manager tab. It runs as the user pistomp.

USB sticks mount automatically at `/media/<label>`. The user pistomp can read and write them.

mod-ui has no endpoint to create folders or write files under `user-files`. The builder needs new endpoints.

The device footswitches send MIDI CC messages, not notes. The user triggers notes with an external pad controller. The pad controller connects with USB MIDI or DIN MIDI. The merger routes its notes into the pedalboard.

## 4. User Flow

The user does these steps:

1. Open the Sound-Bank Builder panel with the toolbar icon.
2. Create a new sound-bank or open an existing one.
3. Set the bank-name, the pad-count, and the base-note.
4. Add sample-files to the bank. Use the upload button, import files from a USB stick, or add sample-files that exist on the device.
5. Use the search-box to filter the sample list by file-name. The sample area has three sources: uploads, USB sticks, and device files.
6. Select one or more samples. Drag the selection to the pad area.
7. The samples bind to the next free pad-slots, in selection order.
8. If the selection is larger than the number of free pad-slots, only the first N samples bind. The extra samples do not bind.
9. Read the MIDI-note of each pad-slot. The note is base-note plus slot index. It is read-only.
10. Set the gain, the root-note, and the loop-mode for each pad-slot.
11. Listen to a sample with the preview button.
12. Press the Build button.
13. The system copies the USB and device sample-files into the bank-folder. Uploaded files are already there. The system writes the SFZ file. It removes copied files that the bank no longer uses.
14. Add the sfizz plugin to the pedalboard.
15. Select the new SFZ file in the sfizz file-picker.

## 5. Data Model

The bank-folder is the source of truth. Uploads go directly into the bank-folder. USB and device sample-files are copied into the bank-folder at build time. The SFZ file lives in the same folder as its sample-files. It uses relative sample paths.

The build syncs the bank-folder. It copies each referenced sample. It removes copied samples that the current build does not use.

Two different sources can have the same file-name. The system renames the copy with a numeric suffix (for example `kick_1.wav`, `kick_2.wav`). It writes the new name in the SFZ file.

```
SFZ Instruments/
  <bank-name>/
    bank.sfz
    <sample-file>...
```

Example SFZ file. Base-note 36, pad-count 4, one-shot drums:

```
<global>
loop_mode=one_shot

<region> key=36 sample=01_kick.wav  volume=-3
<region> key=37 sample=02_snare.wav
<region> key=38 sample=03_hat.wav
<region> key=39 sample=04_tom.wav
```

## 6. SFZ Generation Rules

These rules come from the SFZ specification and the sfizz 1.2.3 source. The builder must follow them.

- Write one region per pad-slot.
- Use `key=N`. Never omit it. `key=N` sets `lokey`, `hikey`, and `pitch_keycenter` to N.
- Use numeric note values (0 to 127).
- Use relative sample paths only.
- Sanitize file-names. Replace spaces with `_`. Remove the characters `=`, `<`, `#`.
- Always write `loop_mode` for each region.
  - Use `loop_mode=one_shot` for drums and one-shot pads. The sample plays to the end. Note-off does not cut it.
  - Use `loop_mode=no_loop` for pads that must stop at note-off.
  - Do not omit `loop_mode`. The default is `no_loop` with a 0.001 second release. A short pad press cuts the sample.
- Write gain as `volume=` (dB). Range is -144 to +48.
- Write the root-note as `pitch_keycenter=`. Default is the pad-note. If the user sets a root-note, write it explicitly.
- Check that every sample-file exists before the build. sfizz skips a region with a missing file. It does not report an error.
- Make sure that the copied file-names are unique in the bank-folder. Use a numeric suffix when two sources have the same name.
- Do not write a MIDI channel. sfizz has no channel concept. It is omni. The SFZ format has no channel opcode.

## 7. Limitations

- MIDI channel per sample is not possible with sfizz. sfizz ignores the channel opcodes by design. One sfizz instance triggers from any channel. Per-pad channel separation needs MIDI routing at the mod-host level. This is a separate feature.
- The mod-ui Python environment has no audio-metadata library. It has no soundfile, no numpy, and no mutagen. The builder cannot read duration, sample-rate, or loop-points in Python. Loop-mode comes from the user toggle, not from file metadata.
- The device has the `ffmpeg` binary. A later phase can use it to read audio metadata.
- A sample-file larger than the upload limit does not upload. The upload endpoint must set a per-file limit (for example 50 MB).
- sfizz loads samples lazily. The first hit of each sample pays the decode cost. Prefer 16-bit or 24-bit WAV files. Avoid many OGG files.
- A bank with USB or device sample-files uses extra SD-card space. The build copies these files into the bank-folder. The original files stay in place. Sample-files are usually small, so the extra space is small.
- A generated bank with no sample-files is invalid. The Build button must not write an empty SFZ file.

## 8. Backend Design

Add new endpoints in `mod/webserver.py`. Register them in the application block (webserver.py:2413-2533).

| Endpoint | Method | Purpose |
|---|---|---|
| `/sfzbuilder/banks` | GET | List the sound-banks. |
| `/sfzbuilder/bank` | POST | Create a bank-folder. |
| `/sfzbuilder/upload` | POST | Upload audio files (multipart) into the bank-folder. |
| `/sfzbuilder/usb` | GET | List audio files on USB sticks. |
| `/sfzbuilder/device` | GET | List audio files on the device, under `USER_FILES_DIR`. |
| `/sfzbuilder/import` | POST | Copy USB files into the bank-folder. |
| `/sfzbuilder/samples` | GET | List the sample-files in the bank-folder. |
| `/sfzbuilder/audio` | GET | Serve one sample-file for the browser preview. |
| `/sfzbuilder/build` | POST | Copy the USB and device samples, sync the bank-folder, and write the SFZ file. |

Design rules:

- All handlers subclass `JsonRequestHandler` (webserver.py:279).
- The upload handler uses multipart. Follow the pattern of `SDKEffectInstaller` (webserver.py:888).
- Keep all paths under `USER_FILES_DIR/SFZ Instruments`. Reject path traversal (`..`).
- Put the SFZ text generation in a new file `mod/sfzbuilder.py`. This file is pure text generation. It is unit-testable.
- Use `TextFileFlusher` (mod/__init__.py:209) for the SFZ write. It writes atomically.
- The device listing walks `USER_FILES_DIR` recursively with the audio extensions. It excludes the current bank-folder.
- The audio preview endpoint follows the pattern of the recording static handler. It must check the path against `USER_FILES_DIR`.

## 9. Frontend Design

New files:

- `html/js/sfzbuilder.js` — the panel logic.
- `html/include/sfzbuilder.html` — the Mustache templates.

Changes:

- `html/index.html` — add the panel div (`#sfzbuilder-library`, classes `mod-hidden mod-init-hidden`), add the toolbar icon in `#main-menu`, add the new elements to the `Desktop(elements)` call (index.html:110), add the script tag with the `?v={{version}}` cache-buster.
- `html/js/desktop.js` — accept the new elements, add a factory method (pattern at :1695-1870), add the statusTooltip init (:1292).
- CSS — extend `main.less` or add a panel style-file.

Panel layout:

- Header: bank-name field, pad-count stepper, base-note field, Build button.
- Sample area: source selector (uploads, device files, USB sticks), upload button, USB import button, search-box, sample list.
- Pad area: a grid of N pad-slots.
  - Each pad-slot shows the read-only MIDI-note (base-note plus index).
  - Each pad-slot shows the sample-name.
  - Each pad-slot has gain, root-note, and loop-mode controls.
  - Each pad-slot has a preview button.
- Drag-and-drop with jQuery UI (already in the project). Multi-select with checkboxes. Drag the selection to the pad area.
- Search: a client-side search-box over the sample file-names. No category tabs.

The preview uses an HTML5 `<audio>` element. Its URL is `/sfzbuilder/audio?bank=<name>&file=<file>`.

## 10. Build Order

1. `mod/sfzbuilder.py` — SFZ text generator, file-name sanitizer, path safety.
2. The backend endpoints.
3. Unit tests for the generator.
4. The frontend panel.
5. Manual device test.

## 11. Verification

- Unit test: the SFZ generator output. Check the regions, the key sequence, `one_shot`, `volume`, `pitch_keycenter`, and the sanitized names.
- Endpoint test: upload, list, and build round-trip.
- Build test: add a device sample, build, and check that the file appears in the bank-folder. Rebuild after a slot removal and check that the stale copy is gone.
- Path-traversal test: reject `..` in names.
- Manual device test: build a bank with N samples, load it into sfizz, trigger the pads with an external MIDI controller, and check that each pad plays its sample. Check that note-off does not cut a one-shot sample.
- Manual test: build a bank with more samples than pad-slots. Check that only the first N bind.

## 12. Scope Phases

Phase 1 (this plan):

- Upload with the browser and with USB.
- Add existing device sample-files (copy into the bank at build).
- Bank-folder creation.
- Pad-count and base-note settings.
- Auto-bind with the slot cap.
- Read-only MIDI-note display.
- Per-slot gain, root-note, and loop-mode.
- Browser preview.
- Search.
- SFZ build and load into sfizz.

Phase 2 (later):

- Velocity layers (`lovel`/`hivel`).
- Round-robin samples.
- Choke groups (`group`/`off_by`).
- `amp_veltrack`.
- `loop_continuous` for loop-point files.
- Audio metadata with the `ffmpeg` binary.
- MIDI channel separation with mod-host routing.

## 13. References

| Fact | Source |
|---|---|
| `USER_FILES_DIR` override | mod-ui service file, `MOD_USER_FILES_DIR=/home/pistomp/data/user-files` |
| File-type to folder map, `sfz` → `SFZ Instruments` | mod/webserver.py:2316-2360 |
| `/files/list` flat recursive walk, no tree endpoint | mod/webserver.py:2303-2395, 2406-2531 |
| `mod:fileTypes "sfz"` annotation on sfzfile | pi-gen-pistomp/debpkgs/sfizz-pistomp/debian/patches/add-mod-filetype.patch |
| browsepy on port 8081, upload + removable, no auth | pi-gen-pistomp/debpkgs/browsepy/debian/browsepy.browsepy.service:9-12 |
| USB mount at `/media/<label>`, pistomp rw | pi-gen-pistomp/debpkgs/pistomp-usb-automount/files/99-pistomp-usb-automount.rules |
| `JsonRequestHandler`, `TextFileFlusher` | mod/webserver.py:279, mod/__init__.py:209 |
| Multipart upload pattern | mod/webserver.py:888 (SDKEffectInstaller) |
| `Desktop(elements)` call | html/index.html:110 |
| Panel factory methods | html/js/desktop.js:1695-1870 |
| statusTooltip init | html/js/desktop.js:1292-1298 |
| `key=N` sets lokey, hikey, pitch_keycenter | sfzformat.com/opcodes/key/ |
| `loop_mode=one_shot` ignores note-off | sfzformat.com/opcodes/loopmode/; sfizz Voice.cpp |
| sfizz omni, channel opcodes ignored | sfizz Region.cpp:863-868, Synth.cpp:1248 |
| Default `no_loop`, 0.001 s release | sfizz Defaults.cpp:149-152, 209 |
| Relative sample paths, default_path | sfzformat.com/opcodes/sample/, /opcodes/default_path/ |
| Path root = .sfz directory; absolute overrides; `..` works; case-insensitive fallback | sfizz Parser.cpp:73-74, Synth.cpp:699, FilePool.cpp:168-230 |
| No audio-metadata library in mod-ui venv | pi-gen-pistomp/debpkgs/mod-ui/debian/rules (pip list) |
| `ffmpeg` installed on device | pi-gen-pistomp/stage3/01-pistomp/01-run.sh:189 |
