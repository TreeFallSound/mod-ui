#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2012-2023 MOD Audio UG
# SPDX-License-Identifier: AGPL-3.0-or-later

import os, shutil, time, logging, json

from datetime import timedelta
from tornado import iostream, gen
from tornado.ioloop import IOLoop, PeriodicCallback

from mod import safe_json_load, TextFileFlusher
from mod.development import FakeHost, FakeHMI
from mod.hmi import HMI
from mod.recorder import Recorder
from mod.screenshot import ScreenshotGenerator
from mod.settings import (LOG, RECORDINGS_DIR,
                          DEV_ENVIRONMENT, DEV_HMI, DEV_HOST,
                          HMI_SERIAL_PORT, HMI_BAUD_RATE, HMI_TIMEOUT,
                          PREFERENCES_JSON_FILE, DEFAULT_SNAPSHOT_NAME, UNTITLED_PEDALBOARD_NAME)

# Refuse to start a new recording below this much free space at RECORDINGS_DIR.
RECORDING_MIN_FREE_BYTES = 500 * 1024 * 1024

if DEV_HOST:
    Host = FakeHost
else:
    from mod.host import Host

class UserPreferences(object):
    def __init__(self):
        self.prefs = safe_json_load(PREFERENCES_JSON_FILE, dict)

    def get(self, key, default, type_ = None, values = None):
        value = self.prefs.get(key, default)

        if type_ is not None and not isinstance(value, type_):
            try:
                value = type_(value)
            except:
                return default

        if values is not None and value not in values:
            return default

        return value

    def setAndSave(self, key, value, atomicSave = True):
        self.prefs[key] = value
        if atomicSave:
            self.saveAtomic()
        else:
            self.saveAsync()

    def saveAtomic(self):
        with TextFileFlusher(PREFERENCES_JSON_FILE) as fh:
            json.dump(self.prefs, fh, indent=4)

    def saveAsync(self):
        try:
            with open(PREFERENCES_JSON_FILE, 'w') as fh:
                json.dump(self.prefs, fh, indent=4)
        except OSError:
            pass

class Session(object):
    def __init__(self):
        logging.basicConfig(level=(logging.DEBUG if LOG else logging.WARNING))

        self.prefs = UserPreferences()
        self.recorder = Recorder()
        self.recorder.watch_for_crash(self._recording_crashed)
        self.external_ui_timer = None

        self.screenshot_generator = ScreenshotGenerator()
        self.websockets = []

        # Used in mod-app to know when the current pedalboard changed
        self.pedalboard_changed_callback = lambda ok,bundlepath,title:None

        # Try to open real HMI
        hmiOpened = False

        if not DEV_HMI:
            self.hmi  = HMI(HMI_SERIAL_PORT, HMI_BAUD_RATE, HMI_TIMEOUT, self.hmi_initialized_cb, self.hmi_reinit_cb)
            hmiOpened = self.hmi.sp is not None

        #print("Using HMI =>", hmiOpened)

        if not hmiOpened:
            self.hmi = FakeHMI(self.hmi_initialized_cb)
            print("Using FakeHMI =>", self.hmi)

        self.host = Host(self.hmi, self.prefs, self.msg_callback)

    def signal_save(self):
        # reuse HMI function
        self.host.hmi_save_current_pedalboard(lambda r:None)

    def signal_device_updated(self):
        self.msg_callback("cc-device-updated")

    def signal_disconnect(self):
        sockets = self.websockets
        self.websockets = []
        for ws in sockets:
            ws.write_message("stop")
            ws.close()
        self.host.end_session(lambda r:None)

    def get_hardware_actuators(self):
        return self.host.addressings.get_actuators()

    def wait_for_hardware_if_needed(self, callback):
        return self.host.addressings.wait_for_cc_if_needed(callback)

    # -----------------------------------------------------------------------------------------------------------------
    # App utilities, needed only for mod-app

    def setupApp(self, pedalboardChangedCallback):
        self.pedalboard_changed_callback = pedalboardChangedCallback

    def reconnectApp(self):
        if self.host.readsock is not None:
            self.host.readsock.close()
            self.host.readsock = None
        if self.host.writesock is not None:
            self.host.writesock.close()
            self.host.writesock = None
        self.host.open_connection_if_needed(None)

    # -----------------------------------------------------------------------------------------------------------------
    # Initialization

    @gen.coroutine
    def hmi_initialized_cb(self):
        self.hmi.initialized = not self.hmi.isFake()
        uiConnected = bool(len(self.websockets) > 0)
        yield gen.Task(self.host.initialize_hmi, uiConnected)

    # This is very nasty, sorry
    def hmi_reinit_cb(self):
        if not os.path.exists("/usr/bin/hmi-reset"):
            return
        # stop websockets
        self.hmi.initialized = False
        self.signal_disconnect()
        # restart hmi
        os.system("/usr/bin/hmi-reset; /usr/bin/sleep 3")
        # reconnect to newly started hmi
        self.hmi = HMI(HMI_SERIAL_PORT, HMI_BAUD_RATE, HMI_TIMEOUT, self.hmi_initialized_cb, self.hmi_reinit_cb)
        self.host.reconnect_hmi(self.hmi)

    # -----------------------------------------------------------------------------------------------------------------
    # Webserver callbacks, called from the browser (see webserver.py)
    # These will be called as a reponse to an action in the browser.
    # A callback must always be used unless specified otherwise.

    # Add a new plugin, starts enabled (ie, not bypassed)
    def web_add(self, instance, uri, x, y, callback):
        self.host.add_plugin(instance, uri, x, y, callback)

    # Remove a plugin
    def web_remove(self, instance, callback):
        self.host.remove_plugin(instance, callback)

    # Address a plugin parameter
    def web_parameter_address(self, port, actuator_uri, label, minimum, maximum, value,
                              steps, tempo, dividers, page, subpage, coloured, momentary, operational_mode, callback):
        instance, portsymbol = port.rsplit("/",1)
        extras = {
            'tempo': tempo,
            'dividers': dividers,
            'page': page,
            'subpage': subpage,
            'coloured': coloured,
            'momentary': momentary,
            'operational_mode': operational_mode,
        }
        self.host.address(instance, portsymbol, actuator_uri, label, minimum, maximum, value, steps, extras, callback)

    def web_set_sync_mode(self, mode, callback):
        self.host.set_sync_mode(mode, True, False, True, callback)
        
    # Set a plugin parameter via pi-stomp
    # We use ":bypass" symbol for on/off state
    def pi_stomp_parameter_set(self, port, value, callback):
        instance, portsymbol = port.rsplit("/",1)
        if portsymbol == ":bypass":
            bvalue = value >= 0.5
            self.host.bypass(instance, bvalue, callback)
        else:
            self.host.param_set(port, value, callback)

    # Connect 2 ports
    def web_connect(self, port_from, port_to, callback):
        self.host.connect(port_from, port_to, callback)

    # Disconnect 2 ports
    def web_disconnect(self, port_from, port_to, callback):
        self.host.disconnect(port_from, port_to, callback)

    # Save the current pedalboard
    # returns saved bundle path
    def web_save_pedalboard(self, title, asNew, callback):
        bundlepath, newTitle = self.host.save(title, asNew, callback)
        self.pedalboard_changed_callback(True, bundlepath, title)

        if self.hmi.initialized and self.host.descriptor.get('hmi_set_pb_name', False):
            self.hmi_set_pb_name(newTitle or title)

        self.screenshot_generator.schedule_screenshot(bundlepath)
        return bundlepath, newTitle

    # Get list of Hardware MIDI devices
    # returns (devsInUse, devList, names, midiAggregatedMode)
    def web_get_midi_device_list(self):
        return self.host.get_midi_ports()

    # Set the selected MIDI devices to @a newDevs
    # Will remove or add new JACK ports as needed
    def web_set_midi_devices(self, newDevs, midiAggregatedMode, midiLoopback):
        return self.host.set_midi_devices(newDevs, midiAggregatedMode, midiLoopback)

    # Send a ping to HMI and Websockets
    def web_ping(self, callback):
        if self.hmi.initialized:
            self.hmi.ping(callback)
        else:
            callback(False)
        self.msg_callback("ping")

    def web_cv_addressing_plugin_port_add(self, uri, name):
        return self.host.cv_addressing_plugin_port_add(uri, name)

    def web_cv_addressing_plugin_port_remove(self, uri, callback):
        self.host.cv_addressing_plugin_port_remove(uri, callback)

    # A new webbrowser page has been open
    # We need to cache its socket address and send any msg callbacks to it
    def websocket_opened(self, ws, callback):
        # Pi-stomp connects from localhost; browsers come from LAN IPs.
        # Local clients are exempt from data_ready flow control (see msg_callback).
        if ws.request.remote_ip in ('127.0.0.1', '::1'):
            ws._is_local = True

        def ready(_):
            self.websockets.append(ws)
            self.host.open_connection_if_needed(ws)
            if self.recorder.recording:
                ws.write_message("recording start %s" % self.recorder.filename)
            callback(True)

        # if this is the 1st socket, start ui session
        if len(self.websockets) == 0:
            self.host.start_session(ready)
        else:
            ready(True)

    # Webbrowser page closed
    def websocket_closed(self, ws, callback):
        try:
            self.websockets.remove(ws)
        except ValueError:
            pass

        # if this is the last socket, end ui session
        if len(self.websockets) == 0:
            self.host.end_session(callback)
        else:
            callback(True)

    # -----------------------------------------------------------------------------------------------------------------

    # Start recording. Returns (ok, filename_or_error).
    def web_recording_start(self):
        if self.recorder.recording:
            return False, "already recording"

        os.makedirs(RECORDINGS_DIR, exist_ok=True)
        free = shutil.disk_usage(RECORDINGS_DIR).free
        if free < RECORDING_MIN_FREE_BYTES:
            return False, "not enough free disk space"

        filename = self.recorder.start()
        self.msg_callback("recording start %s" % filename)
        return True, filename

    # Stop recording. Returns (filename, duration_seconds), or (None, None) if not recording.
    def web_recording_stop(self):
        result = self.recorder.stop()
        if result is None:
            return None, None
        filename, duration = result
        self.msg_callback("recording stop %s %.1f" % (filename, duration))
        return filename, duration

    # Recorder process died unexpectedly (disk full, JACK gone, ...)
    def _recording_crashed(self, filename, duration):
        self.msg_callback("recording stop %s %.1f" % (filename, duration))

    # Current recording state, for a client to resync on page load / reconnect
    def web_recording_status(self):
        if not self.recorder.recording:
            return False, None, 0
        return True, self.recorder.filename, time.time() - self.recorder.tstamp

    # -----------------------------------------------------------------------------------------------------------------
    # Websocket funtions, called when receiving messages from socket (see webserver.py)
    # There are no callbacks for these functions.

    # Receive data ready, with matching counter value
    # This indicates web browser side is ready to receive more events
    def ws_data_ready(self, counter, ws):
        ws._meter_ready = True
        # Guard: if the timer already fired and sent output_data_ready, web_data_ready_ok
        # is True — don't send a second one to mod-host.
        if self.host.web_data_ready_counter == counter and not self.host.web_data_ready_ok:
            self.host.web_data_ready_ok = True
            self.host.send_output_data_ready(None, None)

    # Set a plugin parameter
    # We use ":bypass" symbol for on/off state
    def ws_parameter_set(self, port, value, ws):
        instance, portsymbol = port.rsplit("/",1)

        if portsymbol == ":bypass":
            bvalue = value >= 0.5
            self.host.bypass(instance, bvalue, None)
        else:
            self.host.param_set(port, value, None)

        self.msg_callback_broadcast("param_set %s %s %f" % (instance, portsymbol, value), ws)

    # LV2 patch support
    def ws_patch_get(self, instance, uri, ws):
        self.host.patch_get(instance, uri, None)

    def ws_patch_set(self, instance, uri, valuetype, valuedata, ws):
        writable = self.host.patch_set(instance, uri, valuedata, None)
        self.msg_callback_broadcast("patch_set %s %d %s %c %s" % (instance,
                                                                  1 if writable else 0,
                                                                  uri, valuetype, valuedata), ws)

    # Set a plugin block position within the canvas
    def ws_plugin_position(self, instance, x, y, ws):
        self.host.set_position(instance, x, y)
        self.msg_callback_broadcast("plugin_pos %s %d %d" % (instance, x, y), ws)

    # set the size of the pedalboard (in 1:1 view, aka "full zoom")
    def ws_pedalboard_size(self, width, height):
        self.host.set_pedalboard_size(width, height)

    def ws_show_external_ui(self, instance):
        instance_id = self.host.mapper.get_id_without_creating(instance)
        self.host.send_notmodified("show_external_ui %d" % (instance_id,))

        # we need to keep socket active, so UI receives idle time, just setup an idle function here
        if self.external_ui_timer is not None:
            return
        self.external_ui_timer = PeriodicCallback(lambda: self.host.send_notmodified("cpu_load"), 1000/30)
        self.external_ui_timer.start()

    # -----------------------------------------------------------------------------------------------------------------
    # web session helpers

    @gen.coroutine
    def hmi_set_pb_name(self, name):
        yield gen.Task(self.hmi.set_pedalboard_name, name)

    @gen.coroutine
    def hmi_set_pb_and_ss_name(self, pbname):
        if self.host.descriptor.get('hmi_set_pb_name', False):
            yield gen.Task(self.hmi.set_pedalboard_name, pbname)

        if self.host.descriptor.get('hmi_set_ss_name', False):
            ssname = self.host.snapshot_name() or DEFAULT_SNAPSHOT_NAME
            yield gen.Task(self.hmi.set_snapshot_name, self.host.current_pedalboard_snapshot_id, ssname)

    def readdress_presets(self, instance, callback):
        instance_id = self.host.mapper.get_id_without_creating(instance)
        addressings = self.host.plugins[instance_id]['addressings']

        if ':presets' not in addressings:
            callback(True)
            return

        presets = addressings[':presets']
        data = self.host.addressings.get_presets_as_options(instance_id)
        if not data:
            callback(True)
            return

        value, maximum, options, spreset = data
        port = instance + '/' + presets['port']
        minimum = presets['minimum']
        label = presets['label']
        steps = presets['steps']
        actuator_uri = presets['actuator_uri']
        tempo = presets.get('tempo', False)
        dividers = presets.get('dividers', None)
        page = presets.get('page', None)
        subpage = presets.get('subpage', None)
        coloured = presets.get('coloured', None)
        momentary = presets.get('momentary', None)
        operational_mode = presets.get('operationalMode', None)

        self.web_parameter_address(port, actuator_uri, label, minimum, maximum, value, steps, tempo, dividers,
                                   page, subpage, coloured, momentary, operational_mode, callback)

    # -----------------------------------------------------------------------------------------------------------------
    # TODO
    # Everything after this line is yet to be documented

    # See docs/output-data-flow.md for the full data_finish / output_data_ready
    # handshake and the _is_local local-client optimization.
    def msg_callback(self, msg):
        is_output_set = msg.startswith("output_set ")
        is_data_ready = msg.startswith("data_ready ")
        any_non_local_received = False
        for ws in self.websockets:
            if getattr(ws, '_is_local', False):
                # output_set does reach local clients: pi-stomp renders plugin
                # state (loopjefe's looper state drives its footswitch LED and
                # LCD slot) from it, and drops the ports it hasn't subscribed
                # to. Measured cost of a live meter is ~30 msg/s, not the
                # per-cycle rate -- plugins update monitored outputs at about
                # UI refresh and mod-host discards the rest.
                # data_ready stays suppressed: acking it would put pi-stomp's
                # 10ms loop inside mod-host's feedback path.
                if is_data_ready:
                    continue
            elif is_output_set:
                if getattr(ws, '_is_background', False) or not getattr(ws, '_meter_ready', True):
                    continue
            elif is_data_ready:
                # Skip backgrounded or slow clients so they can't stall mod-host.
                # For backgrounded tabs the browser sends client_hidden which sets
                # _is_background; the self-acknowledge below then fires immediately.
                if getattr(ws, '_is_background', False) or not getattr(ws, '_meter_ready', True):
                    continue
                ws._meter_ready = False
            ws.write_message(msg)
            if is_data_ready:
                any_non_local_received = True

        # If data_ready was suppressed for every connected client (all are local/privileged),
        # mirror what ws_data_ready does: acknowledge and send output_data_ready back to
        # mod-host so its feedback loop stays unblocked.
        if is_data_ready and not any_non_local_received:
            self.host.web_data_ready_ok = True
            self.host.send_output_data_ready(None, None)

    def msg_callback_broadcast(self, msg, ws2):
        for ws in self.websockets:
            if ws == ws2: continue
            ws.write_message(msg)

    def load_pedalboard(self, bundlepath, isDefault):
        self.host.send_notmodified("feature_enable processing 0")
        title = self.host.load(bundlepath, isDefault)
        self.host.send_notmodified("feature_enable processing 1")

        if isDefault:
            bundlepath = ""
            title = ""

        if self.hmi.initialized and (self.host.descriptor.get('hmi_set_pb_name', False) or
                                     self.host.descriptor.get('hmi_set_ss_name', False)):
            self.hmi_set_pb_and_ss_name(title or UNTITLED_PEDALBOARD_NAME)

        self.pedalboard_changed_callback(True, bundlepath, title)
        return title

    def reset(self, callback):
        logging.debug("SESSION RESET")
        self.host.send_notmodified("feature_enable processing 0")
        self.host.msg_callback("resetConnections")

        def host_callback(resp):
            self.host.send_notmodified("feature_enable processing 1")
            callback(resp)

        def reset_host(_):
            self.host.reset(None, host_callback)

        if self.hmi.initialized:
            def set_pb_name(_):
                self.hmi.set_pedalboard_name(UNTITLED_PEDALBOARD_NAME, reset_host)
            def clear_ss_name(_):
                self.host.hmi_clear_ss_name(set_pb_name)
            def clear_hmi(_):
                self.hmi.clear(clear_ss_name)
            if self.host.descriptor.get("hmi_bank_navigation", False):
                self.host.setNavigateWithFootswitches(False, clear_hmi)
            else:
                clear_hmi(True)
        else:
            reset_host(True)

        # Update the title in HMI
        self.pedalboard_changed_callback(True, "", "")

    # host commands

    def format_port(self, port):
        if not 'system' in port and not 'effect' in port:
            port = "effect_%s" % port
        return port

    # END host commands

SESSION = Session()
