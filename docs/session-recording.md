# Session Recording (mod-ui side)

mod-ui owns session recording end-to-end: its own toolbar trigger, its own
UX. This does **not** have a pi-stomp counterpart plan or a protocol designed
for pi-stomp consumption — the WebSocket messages below exist for mod-ui's
own multi-tab sync, and pi-stomp is free to ignore them. Duplication between
packages is acceptable; each owns its own UX. (pi-stomp keeps NAM capture as
a separate, unrelated pedal-side utility.)

This repurposes the old share-clip recorder wholesale: the share-clip UI
(`.js-cloud` / the pedalboard-share modal) is only reachable when
`using_mod` is true (`html/index.html:181-197`), which requires a MOD device
key — unreachable on pi-stomp. So `Recorder`, the `/recording/*` endpoints,
and the `Player` class were dead code on this deployment and have been
repurposed/removed outright.

## Design

- **Format**: WAV, 32-bit IEEE float, stereo (`mod-monitor:out_1`/`out_2`) —
  no fixed duration cap. Float is `jack_capture`'s default when no `-b` flag
  is given; unlike any fixed-point depth (including `-b 32`, which is 32-bit
  *integer*) it doesn't clip samples that exceed +/-1.0 — a hot gain stage
  upstream is preserved losslessly instead of being pinned/truncated at
  digital full-scale. ~1.3 GB/hour; WAV's 4 GB ceiling gives ≈3 hours,
  acceptable for v1 (a follow-up could switch to `-f rf64` to remove it).
  Trade-off: some older/simpler WAV players don't support float PCM: the
  file may need normalizing back under 0 dBFS before it'll play everywhere.
- **Location**: `<user-files>/Audio Recordings/` (`mod/settings.py:
  RECORDINGS_DIR`). This is mod-ui's existing user-files category
  (`FilesList`, `filetype=audiorecording`), so recordings automatically show
  up in the File Manager tab and are selectable by any audio file-player
  plugin — listen-back comes free, no custom playback path needed.
- **Filename**: `YYYY-MM-DD_HHMMSS.wav`, optionally suffixed with a
  slugified pedalboard title.
- **Crash watch**: a ~1s `PeriodicCallback` polls the `jack_capture`
  process; if it dies (disk full, JACK gone), the recorder finalizes and
  broadcasts a stop like a normal one.
- **State sync**: recording start/stop is broadcast over WebSocket
  (`recording start <filename>` / `recording stop <filename>
  <duration_seconds>`) via `msg_callback` (all sockets, not
  `msg_callback_broadcast`) since the HTTP initiator isn't itself a
  WebSocket client. A newly-opened socket gets a `recording start` message
  immediately if a recording is already in progress, so page reloads and
  second tabs resync.
- **Guards**: refuses to start if already recording, or if free space at
  `RECORDINGS_DIR` is below 500 MB.

## REST endpoints (`mod/webserver.py`)

| Endpoint | Returns |
|---|---|
| `GET /recording/start` | `{ok: true, filename}` or `{ok: false, error}` |
| `GET /recording/stop` | `{ok, filename, duration}` |
| `GET /recording/status` | `{recording, filename, elapsed}` — lets a client resync without waiting on a broadcast (used on page load) |
| `GET /recording/file/<name>` | Streams the WAV (`web.StaticFileHandler` rooted at `RECORDINGS_DIR`) |

Deleting recordings happens through the File Manager — there is no delete
endpoint in v1.

## Frontend

- Toolbar record button (`#mod-recorder`, next to `#mod-xruns` /
  `#mod-cpu-stats`): click to start/stop. Button state (red/pulsing +
  elapsed timer) is driven **only** by the `recording *` WebSocket
  messages, so it reflects reality across tabs/reloads and (if a peer ever
  triggers it another way) other clients too.
- On stop, a notification shows the filename/duration with a
  `/recording/file/<name>` download link.
- The old share-clip record/play/download UI (`#record-step-*` in
  `index.html`, the ajax factories in `desktop.js`) is unreachable dead
  markup, left in place but disconnected from any backend.

## Out of scope (v1)

- Dry-input / multichannel re-amp recording (would add extra
  `--port system:capture_1`).
- RF64 for files over the 4 GB WAV ceiling.
- A recordings list UI in mod-ui — the File Manager already covers
  browse/download/delete.
- Any pi-stomp-side trigger/LED work.
