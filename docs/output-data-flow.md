# mod-host Output Data Flow

## Overview

mod-host continuously produces two kinds of feedback on its read socket (port 5556):

- **`output_set`** — real-time meter/scope values (audio level, parameter outputs)
- **`param_set`** — state changes: bypass toggles, parameter edits, MIDI-learn assignments

These share the same socket and the same flow-control mechanism.

## Plugin Self-Writes to Input Ports Are Never Echoed

Both `output_set` and `param_set` require mod-host itself to be the one that changed
the value. There is no mechanism that notices a *plugin* silently overwriting its own
port buffer inside `run()` and forwards that as feedback.

Concretely, in `mod-host/src/effects.c`:

- **`output_set`** is gated by `HINT_MONITORED` (`effects.c:229`, `// outputs only`).
  `effects_monitor_output_parameter` (`effects.c:6563`) resolves the symbol via
  `FindEffectOutputPortBySymbol` — it requires an `lv2:OutputPort`. A plugin cannot
  get this feedback for an `lv2:InputPort`, full stop, regardless of what the plugin
  does with that port's buffer at runtime.
- **`param_set`** is sent from `SetPortValue` (`effects.c:2311`, broadcast at
  `effects.c:2355-2370`) — but only when *mod-host* is the one calling it: a browser
  `param_set` command, an HMI actuator, or a MIDI-learned CC (`effects.c:2755-2763`,
  which computes a value from the raw CC and mod-host's own min/max mapping *before*
  the plugin ever runs). None of these paths re-check the port after `run()` returns.

So a plugin pattern like "declare a control port as `lv2:InputPort` so the host will
also feed external triggers into it, but have the plugin overwrite the same buffer
every block with its own authoritative computed value" (used by, e.g., the loopjefe
LV2 plugin's 5-state `state` port, one physical port doing double duty as trigger-in
and status-out) gets **no feedback loop at all** for the plugin's own correction:

1. A MIDI CC or `param_set` write lands in the port buffer and gets echoed to the
   browser (`SetPortValue`) — this is the *raw incoming* value, not anything the
   plugin has computed yet.
2. The plugin's `run()` reads that value, treats it as "changed, thus a trigger",
   computes its own real next value internally, and overwrites the same buffer
   directly with a raw pointer write.
3. Nothing observes step 2. mod-ui never learns the corrected value; the browser
   widget is left displaying whatever raw value survived step 1, which can be
   arbitrarily wrong relative to the plugin's actual internal state.

The plugin's own internal logic/engine state is unaffected — this only desyncs
whatever a browser modgui renders from the port's displayed value. If a plugin needs
the GUI to reflect a runtime-computed correction like this, it needs a genuine
`lv2:OutputPort` mirror that `MONITOR_OUTPUT` can actually watch; reusing the
input-port buffer for both directions does not get an echo through either path above.

## The `data_finish` / `output_data_ready` Handshake

mod-host batches one frame of output data, then signals the end:

```
mod-host                    mod-ui (host.py)              WebSocket clients
    |                            |                               |
    |-- output_set inst A ------>|                               |
    |-- output_set inst B ------>|-- output_set inst A --------->|
    |-- param_set X :bypass 1 ->|-- output_set inst B --------->|
    |-- data_finish ------------>|-- param_set X :bypass 1.0 --->|
    |                            |                               |
    |                            |-- data_ready N -------------->|
    |                            |                               |
    |                            |<-- data_ready N --------------|
    |                            |   (browser echoes back)       |
    |<-- output_data_ready ------|                               |
    |                            |                               |
    |  (next frame unlocked)     |                               |
    |-- output_set inst A ------>|                               |
    ...
```

**`output_data_ready` is the unlock signal.** Until mod-ui sends it back to mod-host,
mod-host will not produce the next frame. This means `param_set :bypass` echoes (and
all other feedback) stall if `output_data_ready` is never sent.

### mod-ui side (`host.py: process_read_message_body`)

```python
if msg == "data_finish":
    if self.web_connected:          # any WebSocket client is open
        self.web_data_ready_ok = False
        self.web_data_ready_counter += 1
        self.msg_callback("data_ready %i" % counter)
        # Start a 150ms fallback timer in case no client acks in time.
        # msg_callback sets web_data_ready_ok = True if it self-acknowledged,
        # so the timer is only armed when a real ack is still outstanding.
        if not self.web_data_ready_ok and self.last_data_finish_handle is None:
            self.last_data_finish_handle = ioloop.call_later(0.15, self.send_output_data_ready_later)
        return
    else:
        yield gen.Task(self.send_output_data_ready, now)   # no client: use timer
```

### Client echo path (`session.py: ws_data_ready`)

```python
def ws_data_ready(self, counter, ws):
    ws._meter_ready = True
    # Guard: if the 150ms timer already fired, web_data_ready_ok is True —
    # skip to avoid sending a second output_data_ready to mod-host.
    if self.host.web_data_ready_counter == counter and not self.host.web_data_ready_ok:
        self.host.web_data_ready_ok = True
        self.host.send_output_data_ready(None, None)
```

### `send_output_data_ready` (`host.py`)

```python
def send_output_data_ready(self, now, callback):
    self.web_data_ready_ok = True   # mark as done before sending
    ...
    self.send_notmodified("output_data_ready", callback)   # write socket → mod-host
```

`web_data_ready_ok` is set here (rather than only in `ws_data_ready`) so that if the
150ms timer fires first, any subsequent browser ack is a no-op.

## Local Client Optimization (`_is_local`)

pi-stomp connects from `127.0.0.1`; browsers connect from LAN IPs.
Local clients don't need meter spam, so `msg_callback` skips `output_set` and
`data_ready` for them (`session.py: websocket_opened` sets `ws._is_local = True`).

**Problem:** if all connected clients are local, `data_ready` is sent to nobody,
nobody echoes, and `output_data_ready` is never sent to mod-host → everything stalls.

**Fix (`session.py: msg_callback`):** when `data_ready` was suppressed for every
connected client, self-acknowledge immediately — mirroring what a real browser echo
would do:

```python
if is_data_ready and not any_non_local_received:
    self.host.web_data_ready_ok = True
    self.host.send_output_data_ready(None, None)
```

## Backgrounded Browser Tabs (`_is_background`, `_meter_ready`)

A Chrome tab in the background throttles its JS timers to ~1 Hz. Without mitigation,
one backgrounded tab stalls the entire meter loop: it receives `data_ready N` but
doesn't echo for ~1 second, blocking `output_data_ready` and all `param_set` echoes
(including footswitch feedback to pi-stomp).

Two mechanisms work together to prevent this.

### Explicit visibility signal (`_is_background`)

When the browser page becomes hidden, the JS `visibilitychange` listener sends a
WebSocket message:

```javascript
document.addEventListener('visibilitychange', function () {
    if (ws.readyState === WebSocket.OPEN) {
        ws.send(document.hidden ? 'client_hidden' : 'client_visible')
    }
})
```

`webserver.py` sets/clears `ws._is_background` on receipt. In `msg_callback`, a
client with `_is_background = True` is skipped for both `output_set` and `data_ready`:

```python
elif is_output_set:
    if getattr(ws, '_is_background', False) or not getattr(ws, '_meter_ready', True):
        continue
elif is_data_ready:
    if getattr(ws, '_is_background', False) or not getattr(ws, '_meter_ready', True):
        continue
    ws._meter_ready = False
```

When all non-local clients are skipped this way, `any_non_local_received` stays
`False` and the self-acknowledge fires immediately — zero added latency.

When `client_visible` arrives, the server sets `_is_background = False` and
`_meter_ready = True`, and the client re-enters the normal handshake on the next frame.

### Per-client pending-ack gate (`_meter_ready`)

Each client carries a `_meter_ready` flag (default `True`). It is cleared when
`data_ready N` is sent to that client, and restored when the client echoes back.
A client with `_meter_ready = False` is skipped in `msg_callback`, the same as a
backgrounded client.

This covers a gradual slowdown that doesn't trigger `visibilitychange` (e.g., a
foreground tab under heavy CPU load that is simply lagging its echo).

### 150ms fallback timer

`_is_background` relies on the browser sending `client_hidden` before the next
`data_finish` arrives. This is not guaranteed: there is a race between Chrome's
`visibilitychange` event and mod-host's next frame. To bound the worst case,
`host.py` arms a 150ms timer after each `data_ready N` dispatch, but only when
`web_data_ready_ok` is still `False` (i.e., `msg_callback` didn't self-acknowledge):

```
t=0      data_ready N sent to Chrome, timer armed for t=150ms
t=50ms   Chrome (foreground) echoes back → ws_data_ready clears timer, output_data_ready sent
t=150ms  timer fires only if Chrome hasn't echoed → output_data_ready sent, stall bounded
```

150ms is chosen to be safely above Chrome's 50ms JS echo debounce (`triggerDelayedReadyResponse`),
so the timer never races a foreground ack in normal operation. When `client_hidden` is
working, the timer is never armed (self-acknowledge fires in `msg_callback`).

### Double-send protection

Both `send_output_data_ready` and the `ws_data_ready` echo path converge on the same
send. The `web_data_ready_ok` flag prevents a second `output_data_ready` from being
sent if both fire in the same IOLoop turn:

- `send_output_data_ready` sets `web_data_ready_ok = True` before sending.
- `ws_data_ready` checks `not web_data_ready_ok` before calling `send_output_data_ready`.

## Why the Browser Throttles

The browser JavaScript delays its echo by 50 ms before sending `data_ready` back
(`triggerDelayedReadyResponse` in `host.js`). This caps the `output_set` update rate
at ~20 fps, preventing DOM update starvation on pedalboards with many parameters.
Each new `data_ready` resets the debounce timer, so only the most recent counter is
ever echoed.
