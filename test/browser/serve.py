#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2012-2023 MOD Audio UG
# SPDX-License-Identifier: AGPL-3.0-or-later

"""
Serves html/ for the browser smoke test.

The test page must come from the same place that gives the browser the rest of
the files, because the island reads its own files with a relative path. An
earlier version of this test copied the page into html/. That was wrong: html/
is the directory that deploy.sh sends to the device, and the copy and the
deletion of the page raced with rsync.

This server writes nothing. It gives one path, /_smoke.html, from
test/browser/smoke.html, and every other path from html/.
"""

import functools
import http.server
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
HTML_DIR = os.path.join(ROOT, "html")
SMOKE_PAGE = os.path.join(ROOT, "test", "browser", "smoke.html")


class Handler(http.server.SimpleHTTPRequestHandler):
    def translate_path(self, path):
        if path.split("?")[0].split("#")[0] == "/_smoke.html":
            return SMOKE_PAGE
        return super().translate_path(path)

    def log_message(self, fmt, *args):
        pass


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8899
    handler = functools.partial(Handler, directory=HTML_DIR)
    with http.server.ThreadingHTTPServer(("127.0.0.1", port), handler) as httpd:
        httpd.serve_forever()


if __name__ == "__main__":
    main()
