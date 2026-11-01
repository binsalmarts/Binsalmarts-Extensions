#!/usr/bin/env python3
"""Validate theme files using the GTK 3 engine installed with Inkscape on macOS."""
import argparse
import ctypes as c
import os
from pathlib import Path
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gtk-lib", default="/Applications/Inkscape.app/Contents/Resources/lib/libgtk-3.0.dylib")
    args = parser.parse_args()
    # No proxy modules are needed for local CSS; avoid unrelated module loader warnings.
    os.environ["GIO_MODULE_DIR"] = str(Path(__file__).parent)
    gtk = c.CDLL(args.gtk_lib)
    gobject = c.CDLL(str(Path(args.gtk_lib).parent / "libgobject-2.0.0.dylib"))
    glib = c.CDLL(str(Path(args.gtk_lib).parent / "libglib-2.0.0.dylib"))
    gtk.gtk_init_check.argtypes = [c.c_void_p, c.c_void_p]
    if not gtk.gtk_init_check(None, None):
        raise RuntimeError("GTK could not initialize. Run from a desktop session.")
    gtk.gtk_css_provider_new.restype = c.c_void_p
    gtk.gtk_css_provider_load_from_path.argtypes = [c.c_void_p, c.c_char_p, c.POINTER(c.c_void_p)]
    gtk.gtk_css_provider_load_from_path.restype = c.c_int
    gobject.g_object_unref.argtypes = [c.c_void_p]
    glib.g_error_free.argtypes = [c.c_void_p]
    class GError(c.Structure):
        _fields_ = [("domain", c.c_uint), ("code", c.c_int), ("message", c.c_char_p)]
    failed = False
    theme = Path(__file__).resolve().parents[1] / "theme/gtk-3.0"
    for path in (theme / "gtk.css", theme / "gtk-dark.css", theme / "inkscape.css"):
        provider = gtk.gtk_css_provider_new()
        error = c.c_void_p()
        okay = gtk.gtk_css_provider_load_from_path(provider, str(path).encode(), c.byref(error))
        if error.value:
            print(c.cast(error, c.POINTER(GError)).contents.message.decode(), file=sys.stderr)
            glib.g_error_free(error)
        print(path.name + (": PASS" if okay else ": FAIL"))
        failed |= not okay
        gobject.g_object_unref(provider)
    return int(failed)


if __name__ == "__main__":
    sys.exit(main())
