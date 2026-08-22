# pi-stomp Web UI

The web UI lives at **http://pistomp.local** (or whatever hostname your device is on). It is the primary control surface for your pi-stomp: you build signal chains here, store them as named pedalboards, switch snapshots, and manage plugins. Everything you do in the browser is reflected immediately on the hardware.

For developer and integration documentation see [`docs/webapp-dev.md`](webapp-dev.md).

---

## What you can do with this software

This UI is a **live LV2 pedalboard editor**. Think of it as a patchbay and parameter panel rolled into one browser tab. You can:

- Build a signal chain by dragging plugins onto a canvas and wiring their ports together with virtual patch cables.
- Tune every plugin parameter in real time — knobs, toggles, selectors — and hear the result immediately.
- Save the whole arrangement as a named **pedalboard**, and switch between pedalboards instantly.
- Save multiple **snapshots** (parameter freezes) within one pedalboard so you can jump between tonal states — e.g. verse, chorus, solo — without switching pedalboards.
- Assign plugin parameters to footswitches or encoders on the hardware, or to MIDI CC messages, so you can control them hands-free.
- Install new plugins and pedalboards from the **PatchStorage** cloud store without restarting anything.

What this software is **not**:

- It is not a DAW. There is a basic recording endpoint in the server but no multitrack timeline, no arrangement view, no bouncing.
- It is not a step sequencer or pattern editor.
- It does not synthesize audio on its own — it hosts and connects LV2 plugins that you choose.
- It does not manage the operating system, networking, or system updates (those live in pi-stomp and pi-gen-pistomp).

---

## The interface at a glance

### Pedalboard canvas

The centre of the screen is the pedalboard canvas: a pannable, zoomable workspace where your signal chain lives. Each plugin appears as a graphical block — drawn from its own LV2 GUI bundle when one exists, or rendered with a default template otherwise. Audio ports appear as jacks on the sides; connecting two ports draws a patch cable. Hardware input and output buses appear at fixed left/right edges.

What you can do on the canvas:

| Action | How |
|--------|-----|
| Add a plugin | Drag it from the Plugin Browser panel onto the canvas |
| Move a plugin | Drag the plugin block |
| Bypass a plugin | Click the bypass toggle on the plugin block (or the footswitch assigned to it) |
| Adjust a parameter | Click/drag a knob, or right-click a parameter for addressing options |
| Connect ports | Drag from an output jack to an input jack |
| Disconnect a cable | Click the cable and delete, or drag it off the target port |
| Remove a plugin | Right-click the block → Remove |
| View plugin info / presets | Click the info button on a plugin block |
| Zoom in/out | Zoom buttons in the toolbar, or scroll wheel |

Multiple browser tabs can be open simultaneously; all share the same live state. Changes made in one tab (or by the hardware) appear in all tabs within the same meter frame.

### Plugin browser

The **Plugins** panel (left side) lists every LV2 plugin installed on the device. You can filter by category, search by name/brand/keyword, or browse by category tree. Drag any result onto the canvas to add it.

Plugins are discovered at server startup from `~/.lv2` and the factory plugin directory. Installing a plugin via the PatchStorage store makes it available immediately — no page reload or restart needed.

### Pedalboards and banks

A **pedalboard** is a named file (`.pedalboard` bundle) containing the full canvas layout: which plugins are loaded, how they are wired, their parameter values, snapshot list, and hardware/MIDI assignments.

Pedalboards live in `~/.pedalboards/` and can be nested one level deep into category subdirectories, e.g.:

```
~/.pedalboards/
  Live/
    FuzzSong.pedalboard/
  Studio/
    CleanPlate.pedalboard/
```

The **Pedalboards** panel lists all your boards. Clicking one loads it; the current pedalboard is shown in the title bar. You can save, save-as, reset to last-saved state, or delete from this panel.

**Banks** group pedalboards for quick live switching. A bank is an ordered list of pedalboards; the hardware can cycle through them with footswitches. The **Banks** panel lets you create and reorder banks.

### Snapshots

A **snapshot** captures the current value of every plugin parameter in the pedalboard — without changing the wiring or which plugins are loaded. Snapshots let you move between "verse", "chorus", and "solo" sounds by switching a preset rather than reloading a whole pedalboard. BPM and beats-per-bar are included in snapshots.

The snapshot list lives in the top toolbar. You can:

- Switch to a snapshot by clicking it in the list
- Save the current parameter state into an existing snapshot (overwrite)
- Save as a new snapshot (with a name)
- Rename or delete snapshots
- Address a snapshot slot to a hardware footswitch via the addressing dialog

Snapshots are written to disk immediately on save, so a power loss after saving does not lose the state.

### Transport

The transport toolbar controls the global JACK transport: BPM (tempo), beats per bar (time signature numerator), and rolling (start/stop). Plugins that sync to JACK transport — arpeggiators, sequencers, tempo-synced delays — respond to these values.

Sync mode determines what drives the transport clock:
- **Internal** — mod-ui is the JACK transport master; BPM/BPB are set here.
- **MIDI Clock** — tempo is slaved to an incoming MIDI clock signal.

BPM and beats-per-bar can be addressed to hardware knobs or footswitches, and they are broadcast to all browser tabs when changed by any source (hardware, another tab, or MIDI).

### PatchStorage store

The **PatchStorage** tab opens a cloud browser for LV2 plugins and pedalboards built for the pi-stomp (`rpi-aarch64` target). You can:

- Browse and search available patches
- Install a plugin or pedalboard with one click
- Update an installed patch to a newer version (detected automatically from metadata)
- Remove an installed patch

Installed patches write a `patchstorage.json` file into their bundle so the UI can detect staleness. No restart is needed after installing; the plugin becomes drag-droppable immediately.

### Plugin presets ("Snapshots")

Individual plugins can have **presets**/**snapshots** — named configurations of their own parameters. These are separate from pedalboard snapshots: a preset belongs to the plugin and can be loaded across different pedalboards. Use the preset button on a plugin block to browse, save, or load plugin-level presets.

### Hardware and MIDI addressing

Right-clicking any parameter knob opens an **addressing dialog** where you can assign that parameter to:

- A hardware actuator (footswitch, encoder) via the HMI — labeled `/hmi/...`
- A MIDI CC message (MIDI learn or manual entry)
- A CV input port
- BPM sync (tempo division)

Hardware mappings are saved as part of the pedalboard. When the pedalboard loads, all mappings are replayed so pi-stomp's LCD, LEDs, and footswitches are immediately configured.

### System status

The top-right toolbar shows:

- CPU load and xrun count (xruns are audio glitches; a spike here means the DSP can't keep up)
- RAM usage and CPU temperature/frequency (in the status tooltip)
- Buffer size

These update in real time from the WebSocket `stats` / `sys_stats` messages.

---

*See also [`docs/webapp-dev.md`](webapp-dev.md) for codebase architecture and pi-stomp integration guidance.*
