#!/usr/bin/env python3
"""Install only Color Guide Pro, with an optional known-good local macOS Python."""
import argparse
import hashlib
import json
from pathlib import Path
import shlex
import shutil
import tempfile
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
NS={'inx':'http://www.inkscape.org/namespace/inkscape/extension'}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--extensions-dir',type=Path,required=True)
    parser.add_argument('--record-dir',type=Path,required=True)
    parser.add_argument('--python',type=Path)
    parser.add_argument('--inkscape-app',type=Path)
    parser.add_argument('--apply',action='store_true')
    args=parser.parse_args()
    record=args.record_dir.resolve();record.mkdir(parents=True,exist_ok=True)
    target=args.extensions_dir.resolve()/'Color-Guide-Pro'
    if target.exists(): raise SystemExit('Color-Guide-Pro is already installed. Review the existing folder before updating it.')
    package=next(p for p in json.loads((ROOT/'tools/release_manifest.json').read_text())['packages'] if p['name']=='Color-Guide-Pro')
    payload=record/'payload';payload.mkdir(exist_ok=True)
    files=package['files']+['LICENSE']
    for name in files: shutil.copyfile(ROOT/name,payload/Path(name).name)
    shutil.copyfile(ROOT/package['readme'],payload/'README.md')
    if bool(args.python)!=bool(args.inkscape_app): raise SystemExit('Provide both --python and --inkscape-app for a local runtime launcher.')
    if args.python:
        runtime=args.python.resolve();resources=args.inkscape_app.resolve()/'Contents/Resources'
        inkex=resources/'share/inkscape/extensions'
        extras=next(iter(sorted((resources/'lib').glob('python*/site-packages'))),None)
        executable=args.inkscape_app.resolve()/'Contents/MacOS/inkscape'
        if not runtime.is_file() or not inkex.is_dir() or extras is None or not executable.is_file(): raise SystemExit('The selected Python/Inkscape paths are not valid.')
        bootstrap=('import pathlib,runpy,sys;script=sys.argv.pop(1);sys.argv[0]=script;'
                   'sys.path.insert(0,str(pathlib.Path(script).parent));'
                   f'sys.path.append({str(inkex)!r});sys.path.append({str(extras)!r});'
                   'runpy.run_path(script,run_name="__main__")')
        launcher=('#!/bin/sh\n'
                  'unset PYTHONHOME PYTHONPATH DYLD_LIBRARY_PATH DYLD_FALLBACK_LIBRARY_PATH\n'
                  'export PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1\n'
                  f'export INKSCAPE_COMMAND={shlex.quote(str(executable))}\n'
                  'script_dir=$(CDPATH= cd -P -- "$(dirname -- "$0")" && pwd) || exit 1\n'
                  f'exec {shlex.quote(str(runtime))} -c {shlex.quote(bootstrap)} "$script_dir/color_guide_pro.py" "$@"\n')
        (payload/'run_local.sh').write_text(launcher);(payload/'run_local.sh').chmod(0o755)
        for name in ('color_guide_pro.inx','color_guide_manage.inx'):
            path=payload/name;text=path.read_text()
            text=text.replace('<command location="inx" interpreter="python">color_guide_pro.py</command>',
                              '<command location="inx">run_local.sh</command>')
            path.write_text(text)
        (payload/'LOCAL_RUNTIME.md').write_text('This installation uses an existing working Python runtime. Portable ZIPs retain the standard Inkscape Python command. If the local runtime is removed, reinstall using a working runtime.\n')
    identifiers=set()
    for name in ('color_guide_pro.inx','color_guide_manage.inx'):
        identifiers.add(ET.parse(payload/name).find('inx:id',NS).text)
    for descriptor in args.extensions_dir.rglob('*.inx'):
        try: identifier=ET.parse(descriptor).find('inx:id',NS).text
        except (ET.ParseError,AttributeError): continue
        if identifier in identifiers: raise SystemExit('An extension with the same ID already exists: '+str(descriptor))
    manifest={'version':package['version'],'target':str(target),'files':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in payload.iterdir() if p.is_file()}}
    (record/'installation-plan.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
    if args.apply:
        args.extensions_dir.mkdir(parents=True,exist_ok=True)
        staging=Path(tempfile.mkdtemp(prefix='.color-guide-install-',dir=args.extensions_dir))
        try:
            for p in payload.iterdir(): shutil.copy2(p,staging/p.name)
            staging.rename(target)
        except Exception:
            shutil.rmtree(staging,ignore_errors=True);raise
        (record/'installed.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
        print('Installed Color Guide Pro only:',target)
    else: print('Prepared Color Guide Pro:',payload)


if __name__=='__main__': main()
