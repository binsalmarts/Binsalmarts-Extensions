#!/usr/bin/env python3
"""Use an existing Inkscape's Inkex with a Python environment containing Pillow.

python3 tests/run_tests.py --inkex-dir /usr/share/inkscape/extensions
Optional --extra-packages supplies pure-Python Inkex dependencies from a bundle.
"""
import argparse
import os
from pathlib import Path
import sys
import unittest

parser = argparse.ArgumentParser()
parser.add_argument("--inkex-dir")
parser.add_argument("--extra-packages")
parser.add_argument("--inkscape")
parser.add_argument("--pattern", default="test_*.py")
options = parser.parse_args()
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
if options.inkex_dir:
    sys.path.append(options.inkex_dir)
if options.extra_packages:
    sys.path.append(options.extra_packages)
if options.inkscape:
    os.environ["INKSCAPE_COMMAND"] = options.inkscape
suite = unittest.defaultTestLoader.discover(str(Path(__file__).parent), options.pattern)
result = unittest.TextTestRunner(verbosity=2).run(suite)
sys.exit(not result.wasSuccessful())
