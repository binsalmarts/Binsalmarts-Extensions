#!/usr/bin/env python3
"""Stage/install only the three extension packages created in this conversation.

The local macOS launchers avoid a broken bundled Python without changing the
Inkscape application, its preferences, or the portable release ZIPs.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
PACKAGES = {
    'Logo-Construction': ('1.0.0', 'logo_construction.py', ['logo_construction.inx', 'logo_construction_reference.inx']),
    'Blend-Tool-Pro': ('1.1.0', 'blend_tool_pro.py', ['blend_tool_pro.inx', 'blend_tool_manage.inx', 'blend_tool_spine.inx']),
    'Vector-Effects-Pro': ('1.2.0', 'vector_effects_pro.py', ['vector_effects_pro.inx', 'vector_effects_manage.inx',
                                                          'vector_effects_grain.inx', 'vector_effects_noise.inx']),
}
NS = {'inx': 'http://www.inkscape.org/namespace/inkscape/extension'}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--extensions-dir', type=Path, required=True)
    parser.add_argument('--python', type=Path, required=True)
    parser.add_argument('--inkscape-app', type=Path, required=True)
    parser.add_argument('--record-dir', type=Path, required=True)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    target, record = args.extensions_dir.resolve(), args.record_dir.resolve()
    runtime = args.python.resolve()
    resources = args.inkscape_app.resolve() / 'Contents/Resources'
    inkex = resources / 'share/inkscape/extensions'
    extras = resources / 'lib/python3.10/site-packages'
    inkscape = args.inkscape_app.resolve() / 'Contents/MacOS/inkscape'
    if not runtime.is_file() or not inkex.is_dir() or not extras.is_dir() or not inkscape.is_file():
        raise SystemExit('Missing local Python, Inkex or Inkscape runtime.')
    payload = record / 'packages'
    payload.mkdir(parents=True, exist_ok=True)
    plan, ids = [], {}
    for folder, (version, module, descriptors) in PACKAGES.items():
        staged = payload / folder
        staged.mkdir(exist_ok=True)
        shutil.copy2(ROOT / module, staged / module)
        shutil.copy2(ROOT / 'LICENSE', staged / 'LICENSE')
        bootstrap = ('import pathlib,runpy,sys;script=sys.argv.pop(1);sys.argv[0]=script;'
                     'sys.path.insert(0,str(pathlib.Path(script).parent));'
                     f'sys.path.append({str(inkex)!r});sys.path.append({str(extras)!r});'
                     'runpy.run_path(script,run_name="__main__")')
        launcher = ('#!/bin/sh\n'
                    'unset PYTHONHOME PYTHONPATH DYLD_LIBRARY_PATH DYLD_FALLBACK_LIBRARY_PATH\n'
                    'export PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1\n'
                    f'export INKSCAPE_COMMAND={shlex.quote(str(inkscape))}\n'
                    'script_dir=$(CDPATH= cd -P -- "$(dirname -- "$0")" && pwd) || exit 1\n'
                    f'exec {shlex.quote(str(runtime))} -c {shlex.quote(bootstrap)} '
                    f'"$script_dir/{module}" "$@"\n')
        (staged / 'run_local.sh').write_text(launcher)
        (staged / 'run_local.sh').chmod(0o755)
        for filename in descriptors:
            text = (ROOT / filename).read_text()
            old = f'<command location="inx" interpreter="python">{module}</command>'
            if text.count(old) != 1:
                raise SystemExit(f'Unexpected script descriptor: {filename}')
            text = text.replace(old, '<command location="inx">run_local.sh</command>')
            tree = ET.fromstring(text)
            extension_id = tree.find('inx:id', NS).text
            if extension_id in ids:
                raise SystemExit(f'Duplicate staged extension ID: {extension_id}')
            ids[extension_id] = target / folder / filename
            (staged / filename).write_text(text)
        (staged / 'LOCAL_INSTALL.md').write_text(
            f'# {folder} {version} — local macOS installation\n\n'
            'Installed on 26 October 2026 at the user’s request.\n\n'
            'The INX commands use run_local.sh to run the unchanged extension '
            'with a working Python. No Inkscape application files or global preferences are changed.\n\n'
            f'Python: `{runtime}`\n\nInkex: `{inkex}`\n\n'
            'This launcher depends on those existing local runtime paths. If Python or Inkscape '
            'is moved/removed, rerun tools/install_created_extensions.py with the new paths. '
            'Portable release ZIPs still use Inkscape’s normal Python interpreter.\n')
        for file in sorted(staged.iterdir()):
            plan.append({'source': str(file), 'target': str(target / folder / file.name),
                         'sha256': digest(file), 'existed': (target / folder / file.name).exists()})
    for filename in target.rglob('*.inx') if target.exists() else []:
        try:
            extension_id = ET.parse(filename).getroot().find('inx:id', NS).text
        except (ET.ParseError, AttributeError):
            continue
        if extension_id in ids and filename.resolve() != ids[extension_id].resolve():
            raise SystemExit(f'Another copy of this extension ID exists: {filename}')
    manifest = {'status': 'prepared', 'profile_extensions': str(target), 'python': str(runtime),
                'packages': {name: item[0] for name, item in PACKAGES.items()}, 'files': plan}
    (record / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
    if not args.apply:
        print(f'Prepared {len(plan)} files, {len(ids)} commands: {record}')
        return
    if (record / 'installation.json').exists():
        raise SystemExit('Installation record already exists; use a new record directory.')
    backup = record / 'backup'
    written = []
    try:
        for item in plan:
            src, dst = Path(item['source']), Path(item['target'])
            relative = dst.relative_to(target)
            saved = backup / relative
            if dst.exists():
                saved.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(dst, saved)
            dst.parent.mkdir(parents=True, exist_ok=True)
            temp = dst.with_name(dst.name + '.codex-install-tmp')
            written.append((dst, saved, item['existed']))
            shutil.copy2(src, temp)
            os.replace(temp, dst)
            if digest(dst) != item['sha256']:
                raise RuntimeError(f'Installed content mismatch: {dst}')
    except BaseException:
        for dst, saved, existed in reversed(written):
            if existed and saved.exists():
                shutil.copy2(saved, dst)
            elif not existed:
                dst.unlink(missing_ok=True)
            dst.with_name(dst.name + '.codex-install-tmp').unlink(missing_ok=True)
        raise
    manifest['status'] = 'installed'
    manifest['backup_files'] = sum(item['existed'] for item in plan)
    (record / 'installation.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
    print(f'Installed {len(plan)} files / {len(ids)} commands in {target}')
    print(f'Backed up {manifest["backup_files"]} pre-existing files. Record: {record / "installation.json"}')


if __name__ == '__main__':
    main()
