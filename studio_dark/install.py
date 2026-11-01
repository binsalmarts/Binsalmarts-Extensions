#!/usr/bin/env python3
"""Install Studio Dark in one Inkscape profile, with reversible preferences.

No third-party packages are required. An explicit alternate --profile is intended
for an isolated preview; close any Inkscape instance using that profile first.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import uuid
import xml.etree.ElementTree as ET


THEME = "Studio-Dark"
STATE_DIR = ".studio-dark-install"
SOURCE = Path(__file__).resolve().parent / "theme"
LIGHT_ICON = str(int("d5d7daff", 16))
UI_CSS = THEME + ".css"


def theme_target(profile):
    if sys.platform == "darwin":
        # The macOS bundle searches its application-specific share/themes.
        app_root = profile.parent.parent if profile.name == "inkscape" and profile.parent.name == "config" else profile
        return app_root / "share/themes" / THEME
    data_home = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share"))
    if profile.resolve() != default_profile().resolve():
        data_home = profile / "share"
    return data_home / "themes" / THEME


def css_block(profile, target):
    relative = Path(os.path.relpath(target / "gtk-3.0/inkscape.css", profile / "ui")).as_posix()
    relative = relative.replace("\\", "\\\\").replace('"', '\\"')
    return ('\n/* Studio Dark: begin managed import */\n'
            '@import url("' + relative + '");\n'
            '/* Studio Dark: end managed import */\n').encode("utf-8")


class InstallError(Exception):
    pass


def default_profile():
    override = os.environ.get("INKSCAPE_PROFILE_DIR")
    if override:
        return Path(override).expanduser().resolve()
    if sys.platform == "darwin":
        return Path.home() / "Library/Application Support/org.inkscape.Inkscape/config/inkscape"
    if sys.platform == "win32":
        return Path(os.environ.get("APPDATA", Path.home() / "AppData/Roaming")) / "inkscape"
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "inkscape"


def digest(data):
    return hashlib.sha256(data).hexdigest()


def read_optional(path):
    if path.is_symlink():
        raise InstallError("Refusing a symbolic link: " + str(path))
    return path.read_bytes() if path.exists() else None


def tree_hashes(path):
    if not path.exists() and not path.is_symlink():
        return None
    if path.is_symlink() or not path.is_dir():
        raise InstallError("Expected a regular directory, not a link: " + str(path))
    result = {}
    for item in sorted(path.rglob("*")):
        if item.is_symlink():
            raise InstallError("Refusing a symbolic link: " + str(item))
        relative = item.relative_to(path).as_posix()
        if item.is_file():
            result[relative] = digest(item.read_bytes())
        elif item.is_dir():
            result[relative + "/"] = None
        else:
            raise InstallError("Unsupported filesystem entry: " + str(item))
    return result


def inkscape_processes():
    """Return command/environment strings, or None if detection is unavailable."""
    try:
        if sys.platform == "win32":
            output = subprocess.check_output(
                ["tasklist", "/FI", "IMAGENAME eq inkscape.exe", "/FO", "CSV", "/NH"],
                text=True, stderr=subprocess.DEVNULL,
            )
            return [line for line in output.splitlines() if '"inkscape.exe"' in line.lower()]
        output = subprocess.check_output(
            ["ps", "-axo", "pid=,comm="], text=True, stderr=subprocess.DEVNULL,
        )
        running = []
        for line in output.splitlines():
            parts = line.strip().split(None, 1)
            if len(parts) == 2 and Path(parts[1]).name.lower() in ("inkscape", "inkscape-bin"):
                try:
                    command = subprocess.check_output(
                        ["ps", "eww", "-p", parts[0], "-o", "command="],
                        text=True, stderr=subprocess.DEVNULL,
                    )
                except subprocess.CalledProcessError:
                    command = parts[1]
                running.append(command)
        return running
    except (OSError, subprocess.CalledProcessError):
        return None


def ensure_closed(profile):
    processes = inkscape_processes()
    alternate = profile.resolve() != default_profile().resolve()
    if processes is None:
        if alternate:
            # --profile explicitly selects an isolated preview directory. On some
            # sandboxes process enumeration is forbidden; do not block that use.
            print("Notice: process inspection unavailable; close any preview using this alternate profile.")
            return
        raise InstallError("Cannot verify that Inkscape is closed. Close it and retry outside the sandbox, or use --files-only.")
    if not alternate and processes:
        raise InstallError("Close Inkscape before changing its preferences. Use --files-only to install just the theme.")
    if alternate:
        marker = "INKSCAPE_PROFILE_DIR=" + str(profile.resolve())
        if any(marker in command for command in processes):
            raise InstallError("Close the Inkscape preview using this profile first.")


def parse_preferences(data):
    try:
        parser = ET.XMLParser(target=ET.TreeBuilder(insert_comments=True))
        root = ET.fromstring(data, parser=parser) if data is not None else ET.Element("inkscape", {"version": "1"})
    except ET.ParseError as exc:
        raise InstallError("preferences.xml is invalid XML; no changes made: " + str(exc)) from exc
    if root.tag != "inkscape":
        raise InstallError("preferences.xml does not contain an Inkscape preferences document.")
    return root


def group(root, ids, create=False):
    element = root
    for name in ids:
        matches = [child for child in element if child.tag == "group" and child.get("id") == name]
        if len(matches) > 1:
            raise InstallError("Ambiguous duplicate preference group: " + "/".join(ids))
        if matches:
            element = matches[0]
        elif create:
            element = ET.SubElement(element, "group", {"id": name})
        else:
            return None
    return element


def xml_bytes(root):
    return ET.tostring(root, encoding="utf-8", xml_declaration=True) + b"\n"


def preference_settings(keep_icons):
    settings = [(["theme"], key, value) for key, value in {
        "gtkTheme": THEME, "preferDarkTheme": "1", "darkTheme": "1",
        "narrowSpinButton": "1", "fontscale": "90", "contrast": "10",
    }.items()]
    if not keep_icons:
        settings.extend((["theme"], key, value) for key, value in {
            "iconTheme": "Dash", "symbolicIcons": "1",
            "symbolicDefaultBaseColors": "0", "symbolicDefaultHighColors": "0",
        }.items())
        settings.extend((["theme", "Dash"], key, LIGHT_ICON) for key in (
            "symbolicBaseColor",
        ))
        settings.extend((["theme", "Dash"], key, str(int(value, 16))) for key, value in {
            "symbolicSuccessColor": "72c9a1ff", "symbolicWarningColor": "efbd68ff",
            "symbolicErrorColor": "ef7979ff",
        }.items())
    settings.extend((["toolbox", "tools"], key, value) for key, value in {
        "iconsize": "16", "width": "32",
    }.items())
    settings.append((["toolbox", "controlbars"], "iconsize", "16"))
    return settings


def prepare_preferences(before, keep_icons):
    root = parse_preferences(before)
    changes = []
    created = []
    for ids, key, value in preference_settings(keep_icons):
        for count in range(1, len(ids) + 1):
            if group(root, ids[:count]) is None:
                created.append(ids[:count])
                group(root, ids[:count], create=True)
        element = group(root, ids)
        old = element.get(key)
        if old != value:
            changes.append({"group": ids, "key": key, "before": old, "after": value})
            element.set(key, value)
    return xml_bytes(root), changes, created


def atomic_write(path, data, expected):
    """Do not overwrite a preferences file changed since it was read."""
    if read_optional(path) != expected:
        raise InstallError("preferences.xml changed during this operation. No preference changes were written.")
    with tempfile.NamedTemporaryFile(prefix=".studio-dark-", dir=path.parent, delete=False) as stream:
        temporary = Path(stream.name)
        stream.write(data)
    try:
        if path.exists():
            shutil.copymode(path, temporary)
        if read_optional(path) != expected:
            raise InstallError("preferences.xml changed during this operation. No preference changes were written.")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def check_profile(profile):
    for path in (profile / "themes", profile / "ui", profile / STATE_DIR, profile / ".studio-dark-backups"):
        if path.is_symlink() or (path.exists() and not path.is_dir()):
            raise InstallError("Expected a regular directory: " + str(path))


def read_state(profile):
    check_profile(profile)
    data = read_optional(profile / STATE_DIR / "state.json")
    if data is None:
        return None
    try:
        state = json.loads(data)
    except (ValueError, TypeError) as exc:
        raise InstallError("Installation record is damaged. Keep its backups and restore manually.") from exc
    if state.get("format") != 1 or state.get("theme") != THEME:
        raise InstallError("Unrecognized installation record; refusing to change it.")
    return state


def install(profile, files_only=False, keep_icons=False, dry_run=False, source=SOURCE):
    check_profile(profile)
    state = read_state(profile)
    if state is not None:
        raise InstallError("Studio Dark is already installed in this profile. Uninstall it before replacing the installation.")
    source_hashes = tree_hashes(source)
    required = {"index.theme", "gtk-3.0/gtk.css", "gtk-3.0/gtk-dark.css", "gtk-3.0/inkscape.css"}
    if source_hashes is None or not required.issubset(source_hashes):
        raise InstallError("Theme assets are missing. Keep install.py beside the complete theme folder.")
    target = theme_target(profile)
    original_hashes = tree_hashes(target)
    prefs = profile / "preferences.xml"
    before = read_optional(prefs)
    user_css = profile / "ui" / UI_CSS
    css_before = read_optional(user_css)
    if css_before and b"Studio Dark: begin managed import" in css_before:
        raise InstallError("A Studio Dark import already exists in ui/Studio-Dark.css; keep its backup and restore it first.")
    managed_block = css_block(profile, target)
    css_after = (css_before or b"") + managed_block
    after, changes, created = (before, [], [])
    if not files_only:
        ensure_closed(profile)
        after, changes, created = prepare_preferences(before, keep_icons)
    print(("Would install: " if dry_run else "Installing: ") + str(target))
    print("Preferences: " + ("unchanged" if files_only else "Studio Dark + dark mode" + ("" if keep_icons else " + monochrome Dash icons")))
    if dry_run:
        return
    profile.mkdir(parents=True, exist_ok=True)
    target.parent.mkdir(parents=True, exist_ok=True)
    state_path = profile / STATE_DIR
    state_path.mkdir()  # A second installer cannot silently replace our journal.
    state = {
        "format": 1, "theme": THEME, "phase": "installing",
        "installed_files": source_hashes, "original_files": original_hashes,
        "preferences_existed": before is not None,
        "preferences_after_hash": digest(after) if after is not None else None,
        "changes": changes, "created_groups": created,
        "files_only": files_only,
        "css_installed": not files_only,
        "css_before_existed": css_before is not None,
        "css_after_hash": digest(css_after),
        "theme_target": str(target), "ui_css": UI_CSS,
        "css_block": managed_block.decode("utf-8"),
    }
    preferences_written = False
    theme_written = False
    css_written = False
    try:
        if original_hashes is not None:
            shutil.copytree(target, state_path / "previous-theme")
        if before is not None:
            (state_path / "preferences-before.xml").write_bytes(before)
        if css_before is not None:
            (state_path / "user-before.css").write_bytes(css_before)
        (state_path / "state.json").write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
        staged = state_path / "new-theme"
        shutil.copytree(source, staged)
        if tree_hashes(target) != original_hashes:
            raise InstallError("The existing theme changed during installation; please retry.")
        theme_written = True
        if target.exists():
            shutil.rmtree(target)
        staged.replace(target)
        if not files_only:
            ensure_closed(profile)
            user_css.parent.mkdir(exist_ok=True)
            atomic_write(user_css, css_after, css_before)
            css_written = True
            atomic_write(prefs, after, before)
            preferences_written = True
        state["phase"] = "installed"
        (state_path / "state.json").write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    except BaseException:
        if css_written and read_optional(user_css) == css_after:
            if css_before is None:
                user_css.unlink()
            else:
                atomic_write(user_css, css_before, css_after)
        if preferences_written and read_optional(prefs) == after:
            if before is None:
                prefs.unlink()
            else:
                atomic_write(prefs, before, after)
        if theme_written:
            if target.exists():
                shutil.rmtree(target)
            if original_hashes is not None:
                shutil.copytree(state_path / "previous-theme", target)
        shutil.rmtree(state_path)
        raise
    print("Installed. Open Inkscape to use the theme.")
    print("Recovery backup: " + str(state_path))


def restored_preferences(before, state, original):
    if state["files_only"]:
        return before, []
    if before is not None and digest(before) == state["preferences_after_hash"]:
        return original, []
    if before is None:
        return None, ["preferences.xml was removed after installation; left absent"]
    root = parse_preferences(before)
    skipped = []
    for change in state["changes"]:
        element = group(root, change["group"])
        key = change["key"]
        current = element.get(key) if element is not None else None
        if current != change["after"]:
            skipped.append("/" + "/".join(change["group"] + [key]))
            continue
        if change["before"] is None:
            del element.attrib[key]
        else:
            element.set(key, change["before"])
    for ids in sorted(state["created_groups"], key=len, reverse=True):
        element = group(root, ids)
        if element is not None and len(element) == 0 and element.attrib == {"id": ids[-1]}:
            parent = group(root, ids[:-1])
            parent.remove(element)
    return xml_bytes(root), skipped


def uninstall(profile, dry_run=False):
    state = read_state(profile)
    if state is None:
        raise InstallError("No Studio Dark installation record exists for this profile.")
    target = theme_target(profile) if state.get("theme_target") else profile / "themes" / THEME
    if state.get("theme_target") and Path(state["theme_target"]) != target:
        raise InstallError("Theme location no longer matches this profile. Keep the recovery backup and restore manually.")
    existing = tree_hashes(target)
    if existing is not None and existing != state["installed_files"]:
        raise InstallError("Studio Dark files were edited after installation. Preserve or move that folder before uninstalling; no changes made.")
    state_path = profile / STATE_DIR
    backup = state_path / "previous-theme"
    if tree_hashes(backup) != state["original_files"]:
        raise InstallError("The original theme backup changed or is missing; no changes made.")
    prefs = profile / "preferences.xml"
    before = read_optional(prefs)
    original = read_optional(state_path / "preferences-before.xml")
    after, skipped = restored_preferences(before, state, original)
    user_css = profile / "ui" / (UI_CSS if state.get("ui_css") else "user.css")
    managed_block = state.get("css_block", '\n/* Studio Dark: begin managed import */\n@import url("../themes/Studio-Dark/gtk-3.0/gtk.css");\n/* Studio Dark: end managed import */\n').encode("utf-8")
    css_before = read_optional(user_css)
    css_after = css_before
    if state.get("css_installed"):
        if css_before is None or managed_block not in css_before:
            raise InstallError("Studio Dark import was changed or removed from its UI CSS. Restore its managed block before uninstalling; no changes made.")
        if digest(css_before) == state["css_after_hash"]:
            css_after = read_optional(state_path / "user-before.css")
        else:
            css_after = css_before.replace(managed_block, b"", 1)
    if not state["files_only"]:
        ensure_closed(profile)
    print(("Would remove: " if dry_run else "Removing: ") + str(target))
    for key in skipped:
        print("Keeping preference changed since installation: " + key)
    if dry_run:
        return
    if not state["files_only"]:
        ensure_closed(profile)
        if after != before:
            if after is None:
                if read_optional(prefs) != before:
                    raise InstallError("preferences.xml changed during uninstall; please retry.")
                prefs.unlink(missing_ok=True)
            else:
                atomic_write(prefs, after, before)
    try:
        if state.get("css_installed"):
            if css_after is None:
                if read_optional(user_css) != css_before:
                    raise InstallError("ui/user.css changed during uninstall; please retry.")
                user_css.unlink()
            else:
                atomic_write(user_css, css_after, css_before)
        if tree_hashes(target) != existing:
            raise InstallError("The theme changed during uninstall; please retry.")
        if target.exists():
            shutil.rmtree(target)
        if state["original_files"] is not None:
            shutil.copytree(backup, target)
    except BaseException:
        if css_after != css_before and read_optional(user_css) == css_after:
            atomic_write(user_css, css_before, css_after)
        if after != before and read_optional(prefs) == after:
            if before is None:
                prefs.unlink(missing_ok=True)
            else:
                atomic_write(prefs, before, after)
        raise
    history = profile / ".studio-dark-backups"
    history.mkdir(exist_ok=True)
    archived = history / uuid.uuid4().hex[:12]
    state_path.replace(archived)
    print("Uninstalled. Earlier preferences and any previous theme were restored where unchanged.")
    print("Recovery backup retained: " + str(archived))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", nargs="?", default="install", choices=("install", "uninstall", "status"))
    parser.add_argument("--profile", type=Path, help="Alternate, isolated Inkscape profile directory")
    parser.add_argument("--dry-run", action="store_true", help="Inspect and print the plan without writing files")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--files-only", action="store_true", help="Install the theme without activating or changing icons")
    mode.add_argument("--activate", action="store_true", help="Activate the theme (the install default)")
    icons = parser.add_mutually_exclusive_group()
    icons.add_argument("--keep-icons", action="store_true", default=True, help="Keep existing icon preferences (default)")
    icons.add_argument("--monochrome-icons", action="store_true", help="Use the bundled symbolic Dash icons")
    args = parser.parse_args(argv)
    if args.action != "install" and (args.files_only or args.activate or args.monochrome_icons):
        parser.error("--files-only, --activate, and --monochrome-icons apply only to install")
    profile = (args.profile or default_profile()).expanduser().resolve()
    try:
        if args.action == "install":
            install(profile, args.files_only, not args.monochrome_icons, args.dry_run)
        elif args.action == "uninstall":
            uninstall(profile, args.dry_run)
        else:
            state = read_state(profile)
            print("Profile: " + str(profile))
            print("Studio Dark: " + ("installed (" + state["phase"] + ")" if state else "not installed by this installer"))
        return 0
    except (InstallError, OSError) as exc:
        print("Error: " + str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
