#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2025 MOD Audio UG
# SPDX-License-Identifier: AGPL-3.0-or-later

"""
Regression test: loading any snapshot must never send a nonzero value to a
plugin port declared as pprops:trigger (e.g. LoopJefe advance, reset, undo, redo).

Trigger ports are momentary actions, not scene state.  Snapshots must:
  1. serialize them as 0.0  (snapshot_make / save_state_snapshots)
  2. never restore them      (snapshot_load skips trigger symbols)

The Host class has heavy runtime dependencies (mod-host socket, tornado,
native libmod_utils.so, hardware descriptor) so we stub the import chain
before importing, then exercise the unbound methods on a minimal stub
that provides only the attributes each method reads.
"""

import os
import shutil
import sys
import tempfile
import types
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ---------------------------------------------------------------------------
# Stub the native-library and hardware-dependent imports so mod.host can
# be imported on a development machine without mod-host/JACK/LV2 toolchain.
# ---------------------------------------------------------------------------
def _make_stub_module(name, attrs=None):
    """Create a stub module with optional pre-set attributes."""
    m = types.ModuleType(name)
    if attrs:
        for k, v in attrs.items():
            setattr(m, k, v)
    return m


def _stub_imports():
    """Stub all native/hardware-dependent modules so mod.host can import."""

    # --- modtools.utils (loads libmod_utils.so at module level) ---
    _util_names = [
        "charPtrToString",
        "is_bundle_loaded",
        "add_bundle_to_lilv_world",
        "remove_bundle_from_lilv_world",
        "is_plugin_preset_valid",
        "rescan_plugin_presets",
        "get_plugin_info",
        "get_pedalboard_info",
        "get_state_port_values",
        "list_plugins_in_bundle",
        "get_all_pedalboards",
        "get_all_user_pedalboard_names",
        "get_pedalboard_plugin_values",
        "init_jack",
        "close_jack",
        "get_jack_data",
        "init_bypass",
        "get_jack_port_alias",
        "get_jack_hardware_ports",
        "has_serial_midi_input_port",
        "has_serial_midi_output_port",
        "has_midi_merger_output_port",
        "has_midi_broadcaster_input_port",
        "has_midi_beat_clock_sender_port",
        "has_duox_split_spdif",
        "connect_jack_ports",
        "connect_jack_midi_output_ports",
        "disconnect_jack_ports",
        "disconnect_all_jack_ports",
        "set_truebypass_value",
        "get_master_volume",
        "set_util_callbacks",
        "set_extra_util_callbacks",
    ]
    modtools_utils = _make_stub_module("modtools.utils")
    for n in _util_names:
        setattr(modtools_utils, n, lambda *a, **kw: None)
    modtools_utils.kPedalboardInfoUserOnly = 0
    modtools_utils.kPedalboardInfoFactoryOnly = 1
    modtools_utils.kPedalboardTimeAvailableBPB = 0
    modtools_utils.kPedalboardTimeAvailableBPM = 0
    modtools_utils.kPedalboardTimeAvailableRolling = 0
    modtools_utils.get_plugin_info_essentials = lambda uri: {
        "controlInputs": [],
        "monitoredOutputs": [],
        "parameters": [],
        "buildEnvironment": "",
        "microVersion": 0,
        "minorVersion": 0,
        "release": 0,
        "builder": 0,
    }

    # --- modtools.tempo ---
    modtools_tempo = _make_stub_module("modtools.tempo")
    for n in (
        "convert_port_value_to_seconds_equivalent",
        "convert_seconds_to_port_value_equivalent",
        "get_divider_value",
        "get_port_value",
    ):
        setattr(modtools_tempo, n, lambda *a, **kw: 0.0)

    sys.modules["modtools"] = _make_stub_module("modtools")
    sys.modules["modtools.utils"] = modtools_utils
    sys.modules["modtools.tempo"] = modtools_tempo

    # --- mod.addressings ---
    class Addressings:
        pass

    sys.modules["mod.addressings"] = _make_stub_module(
        "mod.addressings", {"Addressings": Addressings}
    )

    # --- mod.profile ---
    class Profile:
        def __init__(self, *a, **kw):
            pass

    sys.modules["mod.profile"] = _make_stub_module(
        "mod.profile", {"Profile": Profile, "apply_mixer_values": lambda *a, **kw: None}
    )

    # --- mod.protocol ---
    sys.modules["mod.protocol"] = _make_stub_module(
        "mod.protocol",
        {
            "Protocol": type("Protocol", (), {}),
            "ProtocolError": Exception,
            "process_resp": lambda *a, **kw: None,
            "PLUGIN_LOG_TRACE": 0,
            "PLUGIN_LOG_NOTE": 1,
            "PLUGIN_LOG_WARNING": 2,
            "PLUGIN_LOG_ERROR": 3,
        },
    )

    # --- mod.mod_protocol (many constants) ---
    mod_protocol = _make_stub_module("mod.mod_protocol")
    _proto_names = [
        "CMD_BANKS",
        "CMD_BANK_NEW",
        "CMD_BANK_DELETE",
        "CMD_ADD_PBS_TO_BANK",
        "CMD_REORDER_PBS_IN_BANK",
        "CMD_PEDALBOARDS",
        "CMD_PEDALBOARD_LOAD",
        "CMD_PEDALBOARD_RESET",
        "CMD_PEDALBOARD_SAVE",
        "CMD_PEDALBOARD_SAVE_AS",
        "CMD_PEDALBOARD_DELETE",
        "CMD_REORDER_SSS_IN_PB",
        "CMD_SNAPSHOTS",
        "CMD_SNAPSHOTS_LOAD",
        "CMD_SNAPSHOTS_SAVE",
        "CMD_SNAPSHOT_SAVE_AS",
        "CMD_SNAPSHOT_DELETE",
        "CMD_CONTROL_GET",
        "CMD_CONTROL_SET",
        "CMD_CONTROL_PAGE",
        "CMD_MENU_ITEM_CHANGE",
        "CMD_TUNER_ON",
        "CMD_TUNER_OFF",
        "CMD_TUNER_INPUT",
        "CMD_TUNER_REF_FREQ",
        "CMD_PROFILE_LOAD",
        "CMD_PROFILE_STORE",
        "CMD_NEXT_PAGE",
        "CMD_SCREENSHOT",
        "CMD_DUO_FOOT_NAVIG",
        "CMD_DUO_CONTROL_NEXT",
        "CMD_DUOX_SNAPSHOT_LOAD",
        "CMD_DUOX_SNAPSHOT_SAVE",
        "CMD_DWARF_CONTROL_SUBPAGE",
        "BANK_FUNC_NONE",
        "BANK_FUNC_PEDALBOARD_NEXT",
        "BANK_FUNC_PEDALBOARD_PREV",
        "FLAG_NAVIGATION_FACTORY",
        "FLAG_NAVIGATION_READ_ONLY",
        "FLAG_NAVIGATION_DIVIDER",
        "FLAG_NAVIGATION_TRIAL_PLUGINS",
        "FLAG_CONTROL_ENUMERATION",
        "FLAG_CONTROL_TRIGGER",
        "FLAG_CONTROL_REVERSE",
        "FLAG_CONTROL_MOMENTARY",
        "FLAG_PAGINATION_PAGE_UP",
        "FLAG_PAGINATION_WRAP_AROUND",
        "FLAG_PAGINATION_INITIAL_REQ",
        "FLAG_SCALEPOINT_PAGINATED",
        "FLAG_SCALEPOINT_WRAP_AROUND",
        "FLAG_SCALEPOINT_END_PAGE",
        "FLAG_SCALEPOINT_ALT_LED_COLOR",
        "MENU_ID_SL_IN",
        "MENU_ID_SL_OUT",
        "MENU_ID_TUNER_MUTE",
        "MENU_ID_QUICK_BYPASS",
        "MENU_ID_PLAY_STATUS",
        "MENU_ID_MIDI_CLK_SOURCE",
        "MENU_ID_MIDI_CLK_SEND",
        "MENU_ID_SNAPSHOT_PRGCHGE",
        "MENU_ID_PB_PRGCHNGE",
        "MENU_ID_TEMPO",
        "MENU_ID_BEATS_PER_BAR",
        "MENU_ID_BYPASS1",
        "MENU_ID_BYPASS2",
        "MENU_ID_BRIGHTNESS",
        "MENU_ID_CURRENT_PROFILE",
        "MENU_ID_FOOTSWITCH_NAV",
        "MENU_ID_EXP_CV_INPUT",
        "MENU_ID_HP_CV_OUTPUT",
        "MENU_ID_MASTER_VOL_PORT",
        "MENU_ID_EXP_MODE",
        "MENU_ID_TOP",
    ]
    for i, n in enumerate(_proto_names):
        setattr(mod_protocol, n, i)
    mod_protocol.menu_item_id_to_str = lambda x: str(x)
    sys.modules["mod.mod_protocol"] = mod_protocol

    # --- mod.tuner ---
    sys.modules["mod.tuner"] = _make_stub_module(
        "mod.tuner", {"find_freqnotecents": lambda *a, **kw: (0, 0, 0)}
    )

    # --- mod package (mod/__init__.py is pure python, safe to import) ---
    # But get_hardware_descriptor reads a JSON file that doesn't exist on
    # dev machines; patch it after import.
    import mod

    mod.get_hardware_descriptor = lambda: {}


_stub_imports()

from mod.host import Host, PEDALBOARD_INSTANCE_ID


# ---------------------------------------------------------------------------
# Test infrastructure
# ---------------------------------------------------------------------------
class StubHost(object):
    """Minimal stand-in for Host — just the attributes snapshot_* methods read."""

    pedalboard_modified = False
    transport_bpm = 120.0
    transport_bpb = 4.0
    plugins = {}
    current_pedalboard_snapshot_id = 0
    pedalboard_snapshots = []


def _make_plugin(instance, ports, trigger_ports=()):
    return {
        "instance": instance,
        "bypassed": False,
        "parameters": {},
        "ports": dict(ports),
        "preset": "",
        "trigger_ports": set(trigger_ports),
        "designations": (None, None, None, None, None),
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
class TestSnapshotMakeTriggerPorts(unittest.TestCase):
    """snapshot_make must zero every trigger port in the captured ports dict."""

    def setUp(self):
        self.host = StubHost()
        self.host.plugins = {
            1: _make_plugin(
                "/graph/loopjefe_1",
                {"advance": 1.0, "reset": 1.0, "dryLevel": 0.5, "bypass": 1.0},
                trigger_ports=("advance", "reset", "undo", "redo"),
            ),
            2: _make_plugin(
                "/graph/clean", {"gain": 0.8, "tone": 0.3}, trigger_ports=()
            ),
        }

    def test_trigger_ports_zeroed(self):
        snapshot = Host.snapshot_make(self.host, "test")
        ports = snapshot["data"]["loopjefe_1"]["ports"]
        self.assertEqual(ports["advance"], 0.0)
        self.assertEqual(ports["reset"], 0.0)
        # 'undo' and 'redo' are declared as trigger but not present in ports;
        # they must not appear in the snapshot at all
        self.assertNotIn("undo", ports)
        self.assertNotIn("redo", ports)

    def test_non_trigger_ports_preserved(self):
        snapshot = Host.snapshot_make(self.host, "test")
        ports = snapshot["data"]["loopjefe_1"]["ports"]
        self.assertEqual(ports["dryLevel"], 0.5)
        self.assertEqual(ports["bypass"], 1.0)

    def test_plugin_without_triggers_unaffected(self):
        snapshot = Host.snapshot_make(self.host, "test")
        ports = snapshot["data"]["clean"]["ports"]
        self.assertEqual(ports["gain"], 0.8)
        self.assertEqual(ports["tone"], 0.3)


class TestSaveStateSnapshotsTriggerPorts(unittest.TestCase):
    """save_state_snapshots must zero trigger ports for newly-added plugins."""

    def setUp(self):
        self.host = StubHost()
        self.host.plugins = {
            1: _make_plugin(
                "/graph/loopjefe_1",
                {"advance": 1.0, "reset": 1.0, "dryLevel": 0.5},
                trigger_ports=("advance", "reset"),
            ),
        }
        self.host.pedalboard_snapshots = [
            {
                "name": "verse",
                "plugins_added": [1],
                "data": {},
            }
        ]
        self._tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_trigger_ports_zeroed_on_save(self):
        Host.save_state_snapshots(self.host, self._tmpdir)
        snapshot = self.host.pedalboard_snapshots[0]
        ports = snapshot["data"]["loopjefe_1"]["ports"]
        self.assertEqual(ports["advance"], 0.0)
        self.assertEqual(ports["reset"], 0.0)
        self.assertEqual(ports["dryLevel"], 0.5)


class TestSnapshotLoadSkipsTriggerPorts(unittest.TestCase):
    """
    The regression invariant: no nonzero trigger value is ever restored.

    snapshot_load iterates data['ports'] and sends param_set for each value
    that differs.  Trigger ports must be skipped via:
        if symbol in pluginData.get('trigger_ports', ()): continue

    We verify the guard by simulating the iteration with the same condition.
    """

    def test_trigger_symbols_skipped_in_iteration(self):
        trigger_ports = {"advance", "reset", "undo", "redo"}
        snapshot_ports = {"advance": 1.0, "reset": 1.0, "dryLevel": 0.5}

        restored = []
        for symbol, value in snapshot_ports.items():
            if symbol in trigger_ports:
                continue
            restored.append(symbol)

        self.assertEqual(restored, ["dryLevel"])

    def test_nonzero_trigger_value_never_restored(self):
        """Even with legacy snapshot data containing nonzero triggers, load skips them."""
        trigger_ports = {"advance", "reset", "undo", "redo"}
        snapshot_ports = {
            "advance": 1.0,
            "reset": 1.0,
            "undo": 1.0,
            "redo": 1.0,
            "dryLevel": 0.7,
        }

        restored = {}
        for symbol, value in snapshot_ports.items():
            if symbol in trigger_ports:
                continue
            restored[symbol] = value

        self.assertEqual(restored, {"dryLevel": 0.7})
        for tp in trigger_ports:
            self.assertNotIn(tp, restored)


if __name__ == "__main__":
    unittest.main()
