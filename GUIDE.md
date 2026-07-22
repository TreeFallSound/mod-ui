# mod-ui — the pi-stomp "ultimate" fork

> This document is the single source of truth for *this* version of `mod-ui` — the one sitting at `/Users/cam/dev/mod-ui`, on branch `more-fixes`, with the PatchStorage integration. It is meant for Claude, Gemini, and any future coding agent that has to touch this code.

## What this repo is

This is a fork of [mod-audio/mod-ui](https://github.com/moddevices/mod-ui), the web UI + control layer for the MOD audio ecosystem. It runs as a Python/Tornado webserver and talks to `mod-host` over a socket. It discovers LV2 plugins and pedalboards via `lilv`, serves an HTML5 pedalboard editor, and pushes real-time state to connected browsers and hardware peers over WebSocket.

This fork is customized for the **pi-stomp** guitar-pedal hardware platform. It lives as a sibling to `pi-stomp`, `pi-gen-pistomp`, `pistomp-recovery`, etc.

### Why "ultimate"

This branch is the accumulation of several feature/experimental branches that were merged together to make a single "do everything" target:

- PatchStorage-based plugin/pedalboard store in the web UI
- nested user pedalboard directories (`~/.pedalboards/<category>/<board>.pedalboard`)
- output clipping indicator (WebSocket push) with mod-host meter flow-control fixes
- WebSocket BPM/BBT rebroadcast between browser clients
- local WebSocket clients (i.e. pi-stomp) skip meter flow-control and self-acknowledge `output_data_ready`
- hardening around `param_set` / bypass when parameters do not exist

The user describes this as the **"ultimate version"** — the richest feature set — but some features were discussed and never implemented. Those are documented below under [Features we talked about but did not build](#features-we-talked-about-but-did-not-build).

## How to build / run locally

This is a Linux project, but it has been built/tested on macOS for development. The C++ utils library is the only compiled component.

```bash
# Python deps
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Native utils (lilv + jack + optional alsa)
make -C utils
```

To run locally against a MOD Desktop / mod-host instance, set the expected environment variables. A typical local run:

```bash
export MOD_DEV_ENVIRONMENT=0
export MOD_DEVICE_WEBSERVER_PORT=18181
export MOD_HOST_PORT=5555
export MOD_HOST_FEEDBACK_PORT=5556
export MOD_DATA_DIR=$HOME/.mod-data
export MOD_USER_PEDALBOARDS_DIR=$MOD_DATA_DIR/.pedalboards
export MOD_USER_FILES_DIR=$MOD_DATA_DIR/user-files
export MOD_KEYS_PATH=$MOD_DATA_DIR/keys/
export MOD_HTML_DIR=$PWD/html
export MOD_DEFAULT_PEDALBOARD=$PWD/default.pedalboard
export MOD_CLOUD_API=https://api.moddevices.com/v2
export PATCHSTORAGE_API_URL=https://patchstorage.com/api/beta/patches
export PATCHSTORAGE_PLATFORM_ID=8046
export PATCHSTORAGE_TARGET_ID=8280
export JACK_PROMISCUOUS_SERVER=jack
python3 server.py
```

On the device these values are injected by the `mod-ui.service` in `pi-gen-pistomp` (see `debpkgs/mod-ui/debian/mod-ui.mod-ui.service`).

## Repo layout

| Path | Purpose |
|------|---------|
| `mod/` | Core Python server: webserver, session, host logic, settings |
| `mod/host.py` | Plugin/pedalboard host controller; most WS dispatch lives here |
| `mod/session.py` | WebSocket session management, local-vs-remote client handling |
| `mod/webserver.py` | HTTP endpoints and pedalboard/config API |
| `mod/settings.py` | Environment-based defaults (PatchStorage IDs live here) |
| `utils/` | C/C++ helpers compiled into `libmod_utils.so` |
| `utils/utils_lilv.cpp` | Plugin/pedalboard discovery via lilv; nested pedalboards added here |
| `utils/patchstorage.cpp` | C++ helpers for PatchStorage metadata |
| `html/js/patchstorage.js` | Browser-side PatchStorage store UI and API client |
| `docs/output-data-flow.md` | How `output_data_ready` / `data_finish` meter flow-control works |

## Key features implemented in this fork

### 1. PatchStorage integration

The browser can open a **PatchStorage** tab to browse, install, update, and remove LV2 plugins and pedalboards from the cloud.

- Default endpoint: `https://patchstorage.com/api/beta/patches`
- Default platform: **8046** ("LV2 Plugins")
- Default target: **8280** (`rpi-aarch64`) — the pi-stomp image is 64-bit ARM
- These values are configured through environment variables (`PATCHSTORAGE_*`) and exposed to the frontend as globals in `html/index.html`.
- Each installed patch writes a `patchstorage.json` into the bundle so the UI can detect "outdated" content and offer updates.

> Historical note: the original hardcoded IDs `5027`/`5037` were deleted by PatchStorage. This fork already moved to the current IDs (`8046`/`8280`) via the systemd environment.

### 2. Nested pedalboard directories

Upstream mod-ui / lilv only loads pedalboards that are **immediate children** of each LV2_PATH entry. We added a bounded directory walk in `utils/utils_lilv.cpp` so boards can live one level deeper, e.g.

```
~/.pedalboards/
  Live/
    FuzzSong.pedalboard/
  Studio/
    CleanPlate.pedalboard/
```

The walk is intentionally defensive:
- max 2 levels deep
- skips hidden dirs, `.git`, `node_modules`, `__pycache__`
- only appends a sub-folder to `LV2_PATH` if it directly contains at least one `*.pedalboard` child
- caps each directory scan at 1024 entries and warns once

### 3. Output clipping indicator

A WebSocket message `clip_status <label> <0|1>` is sent when an output clips or clears. This rides on the existing `monitor_audio_levels` infrastructure in `mod-host`, but uses a separate `POSTPONED_AUDIO_CLIP` event so it does not re-enable the expensive per-parameter stream that pi-stomp disabled. The frontend and pi-stomp can light an LED from this single message.

See `docs/output-data-flow.md` for the full meter/flow-control handshake.

### 4. Local WebSocket clients bypass meter flow-control

`mod/session.py` treats clients marked as local (pi-stomp) differently from browser tabs: they self-acknowledge `data_ready`, avoiding the stall that can happen when a browser tab is not keeping up.

### 5. `param_set` / bypass safety

If a plugin instance or parameter does not exist, `host.py` no longer raises; it logs and returns. This prevents crashes during race conditions (e.g. blend-mode snapshot switching, MIDI footswitch events arriving while a pedalboard is being torn down).

## Architecture gotchas

### Source of truth

There are two copies of "current state" at any moment:

1. **mod-ui / mod-host** — the actual JACK audio graph and LV2 parameters.
2. **pi-stomp** — its own mirror used to drive the LCD, LEDs, and footswitch logic.

pi-stomp synchronizes by:
- polling `last.json` and the pedalboard manifest
- reading WebSocket events (`param_set`, `pedalboard`, `snapshot`, `bypass`, etc.)
- sending commands back over WebSocket or MIDI

Any agent touching state-sync code should read `docs/output-data-flow.md` and the `mod/session.py` local-client logic first.

### WebSocket echo problem

When pi-stomp sends a command to mod-ui over WebSocket, mod-ui broadcasts the resulting state change back to **all** clients, including the sender. pi-stomp has built echo-suppression machinery for some message types. If you add a new WebSocket-driven action, consider whether the sender needs to ignore its own echo.

### Nested pedalboards vs. upstream

The nested discovery is implemented in C++ inside `utils/utils_lilv.cpp`. It does **not** change how pedalboards are saved or how the manifest is parsed — it only changes which bundles are visible to lilv. Tests that run against the Python layer will not exercise this unless they also build `libmod_utils.so`.

## Features we talked about but did not build

These came up in conversation and were either rejected or left as future work. Do not re-implement them without checking with the user.

### 1. Runtime PatchStorage slug resolution

The idea was to resolve `platform_id`/`target_id` from stable slugs (`lv2-plugins`, `rpi-aarch64`) at startup, so a future PatchStorage renumbering would not silently break the store. The user rejected this; the current approach is to set the numeric IDs as environment variables in `pi-gen-pistomp/debpkgs/mod-ui/debian/mod-ui.mod-ui.service`.

### 2. Self-hosted / mirror plugin catalog

We discussed bundling a baseline plugin set in the OS image and/or maintaining a self-hosted mirror of the PatchStorage catalog as insurance against Blokas/availability risk. Not implemented — PatchStorage remains the primary channel.

### 3. Pedalboard remote-git updates from recovery

`pistomp-recovery` had a `PedalboardFacet.remote_updates()` path that duplicated PatchStorage. The decision was to **remove** that and let PatchStorage own pedalboard content delivery. Recovery should keep only stamp/rollback/factory-reset for pedalboards.

### 4. Input clipping indicator

Output clipping is wired up; input clipping was discussed but not implemented. It would require monitoring `system:capture_*` or a dedicated `tinygain` plugin placed at the input.

### 5. Plugin "factory reset" / cache cap in recovery

We discussed adding a Plugins facet to `pistomp-recovery` that could reset user-installed LV2 plugins back to the factory image baseline and possibly cap the cache size. Some scaffolding was started but not finished.

### 6. Browser-side PatchStorage store redesign

A more discoverable/filterable store UI, dependency handling between plugin bundles, and install-queue UX were discussed but not built. The current store is functional but minimal.

## Environment variables you should know

| Variable | Default / typical value | Meaning |
|----------|-------------------------|---------|
| `MOD_USER_PEDALBOARDS_DIR` | `~/.pedalboards` or `/home/pistomp/data/.pedalboards` | Where user pedalboards live |
| `MOD_FACTORY_PEDALBOARDS_DIR` | `/usr/share/mod/pedalboards/` | Read-only factory boards |
| `PATCHSTORAGE_API_URL` | `https://patchstorage.com/api/beta/patches` | PatchStorage API root |
| `PATCHSTORAGE_PLATFORM_ID` | `8046` | Platform taxonomy ID |
| `PATCHSTORAGE_TARGET_ID` | `8280` | Target/arch taxonomy ID (`rpi-aarch64`) |
| `MOD_DEVICE_WEBSERVER_PORT` | `80` on device, `18181` locally | HTTP port |
| `MOD_HOST_PORT` / `MOD_HOST_FEEDBACK_PORT` | `5555` / `5556` | mod-host command / feedback sockets |
| `MOD_LOG` | `0` | Verbose logging when non-zero |

## Coding conventions

- Python: follow the existing style in `mod/`. No hard rule on type hints, but new files in recovery-related experiments used them.
- C++: compiled with `-Wall -Wextra -Wshadow -std=gnu++0x`. Keep changes minimal; the file is large.
- Commits are small and descriptive. The current branch is `more-fixes`.
- Do not run `git commit` / `git push` / `git rebase` unless explicitly asked.

## Common test commands

```bash
# Compile the utils library
make -C utils clean && make -C utils

# Python lint/smoke (no formal test suite in mod-ui itself)
python3 -m py_compile mod/host.py mod/session.py mod/webserver.py
```x

The real integration tests live in `../pi-stomp` (a `uv`/`pytest` project). Any change to WebSocket message format or pedalboard loading should be validated there.

## Related repos

- `../pi-stomp` — the LCD/footswitch/encoder application that talks to this mod-ui over WebSocket and MIDI.
- `../pi-gen-pistomp` — image generation and OS build; owns the Debian packaging and systemd units (including `mod-ui.service`).
- `../pistomp-recovery` — recovery/rollback UI; should not duplicate PatchStorage pedalboard updates.
- `../mod-host` — the LV2 plugin host this UI controls.

## Last updated

2026-06-23
