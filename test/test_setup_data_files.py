#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2012-2023 MOD Audio UG
# SPDX-License-Identifier: AGPL-3.0-or-later

"""
Guards the install list of setup.py.

setup.py names each directory of html/ with a glob that is not recursive. Thus a
new directory is absent from the package and the browser reads nothing. The
panel of that feature is then empty and gives no other sign.

An island keeps its code and its stylesheet in html/js/app/<feature>/. This test
reads the globs of setup.py and asks that each of those files is in one of them.
"""

import ast
import glob as globmodule
import os
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ISLAND_ROOT = os.path.join(ROOT, "html", "js", "app")


def installed_files():
    """Gives every file that the data_files list of setup.py installs.

    The test runs the same glob() calls that setup.py runs. fnmatch is not
    correct here, because its * goes past a / and thus 'html/js/*.js' would
    appear to hold a file in a directory below.
    """
    with open(os.path.join(ROOT, "setup.py")) as fh:
        tree = ast.parse(fh.read())

    patterns = []
    for node in ast.walk(tree):
        # Each entry looks like glob('html/js/app/sfzbuilder/*.js').
        if not isinstance(node, ast.Call):
            continue
        if not isinstance(node.func, ast.Name) or node.func.id != "glob":
            continue
        if len(node.args) != 1 or not isinstance(node.args[0], ast.Constant):
            continue
        patterns.append(node.args[0].value)

    found = set()
    for pattern in patterns:
        for path in globmodule.glob(os.path.join(ROOT, pattern)):
            found.add(os.path.relpath(path, ROOT))
    return patterns, found


class TestSetupDataFiles(unittest.TestCase):
    def test_island_files_are_installed(self):
        patterns, installed = installed_files()
        self.assertTrue(patterns, "setup.py holds no glob() call")

        missing = []
        for dirpath, dirnames, filenames in os.walk(ISLAND_ROOT):
            dirnames[:] = [d for d in dirnames if d != "node_modules"]
            for name in filenames:
                if not name.endswith((".js", ".css")):
                    continue
                path = os.path.relpath(os.path.join(dirpath, name), ROOT)
                if path not in installed:
                    missing.append(path)

        self.assertEqual(
            missing, [],
            "these island files are not in the data_files list of setup.py, so "
            "the device does not get them:\n  " + "\n  ".join(missing))


if __name__ == "__main__":
    unittest.main()
