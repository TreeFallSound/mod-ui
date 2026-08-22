#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2012-2023 MOD Audio UG
# SPDX-License-Identifier: AGPL-3.0-or-later

import os, subprocess, time
from signal import SIGINT
from tornado.ioloop import PeriodicCallback
from mod.settings import RECORDINGS_DIR, DEVICE_KEY

class Recorder(object):
    def __init__(self):
        self.recording = False
        self.tstamp = None
        self.filename = None
        self.proc = None
        self.crash_watch = None
        self.crash_callback = None

    def start(self, name_suffix=None):
        if self.recording:
            self.stop()

        os.makedirs(RECORDINGS_DIR, exist_ok=True)

        self.tstamp = time.time()
        filename = time.strftime('%Y-%m-%d_%H%M%S', time.localtime(self.tstamp))
        if name_suffix:
            filename += '_' + name_suffix
        filename += '.wav'
        self.filename = filename

        # --no-stdin: without it jack_capture reads console input to detect a
        # "press Return to stop" keypress; under Popen (no controlling tty) it
        # hits EOF on stdin immediately and treats that as the stop signal,
        # ending the recording within a second of starting.
        #
        # No -b (bitdepth) flag: omitting it is what selects jack_capture's
        # default 32-bit IEEE float sample format. Passing "-b 32" instead
        # gives 32-bit *integer* PCM, which still clips at +/-1.0 same as any
        # fixed-point format -- only the float default preserves samples that
        # exceed unity (e.g. from a hot gain stage) without truncating them.
        cmd = ['jack_capture', '-f', 'wav', '-V', '-dc', '--no-stdin',
               '--port', 'mod-monitor:out_1', '--port', 'mod-monitor:out_2',
               os.path.join(RECORDINGS_DIR, filename)]
        if DEVICE_KEY: # if using a real MOD, setup niceness
            cmd = ["/usr/bin/nice", "-n", "+1"] + cmd
        self.proc = subprocess.Popen(cmd)
        self.recording = True
        return filename

    # Poll jack_capture so a crash (disk full, JACK gone) still ends the
    # recording state and gets broadcast, instead of leaving clients stuck
    # thinking a recording is still active.
    def watch_for_crash(self, callback):
        self.crash_callback = callback
        if self.crash_watch is not None:
            return
        self.crash_watch = PeriodicCallback(self._poll_crash, 1000)
        self.crash_watch.start()

    def _poll_crash(self):
        if not self.recording or self.proc is None:
            return
        if self.proc.poll() is None:
            return
        filename, duration = self._finish()
        if self.crash_callback is not None:
            self.crash_callback(filename, duration)

    def stop(self):
        if not self.recording:
            return None
        self.proc.send_signal(SIGINT)
        self.proc.wait()
        return self._finish()

    def _finish(self):
        filename = self.filename
        duration = time.time() - self.tstamp
        self.recording = False
        self.filename = None
        self.proc = None
        return filename, duration
