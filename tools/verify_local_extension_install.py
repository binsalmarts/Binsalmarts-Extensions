#!/usr/bin/env python3
"""Exercise the nine local INX commands through their actual executable launchers."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile
from lxml import etree

NS = {'inx': 'http://www.inkscape.org/namespace/inkscape/extension'}
ROOT = Path(__file__).resolve().parents[1]
SCHEMA = Path('/Applications/Inkscape.app/Contents/Resources/share/inkscape/extensions/inkex/tester/inkscape.extension.rng')
SOURCE = b'''<svg xmlns="http://www.w3.org/2000/svg" width="400" height="200" viewBox="0 0 400 200">
<g id="logo"><rect id="ref" x="30" y="40" width="100" height="50" fill="#635bff"/>
<rect id="part" x="150" y="40" width="100" height="50" fill="#ff744f"/></g>
<circle id="a" cx="60" cy="150" r="15" fill="#635bff"/>
<circle id="b" cx="270" cy="150" r="22" fill="#ff744f"/>
<path id="spine" d="M60,150 Q170,80 270,150" fill="none" stroke="black"/>
</svg>'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--packages-dir', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    schema = etree.RelaxNG(etree.parse(str(SCHEMA)))
    results = []
    env = os.environ.copy()
    # Simulate the bundled application's Python environment. The launcher must
    # sanitize these before starting the independent, working interpreter.
    env.update(PYTHONHOME='/Applications/Inkscape.app/Contents/Resources',
               PYTHONPATH='/Applications/Inkscape.app/Contents/Resources/lib/python3.10/site-packages')
    with tempfile.TemporaryDirectory(prefix='inkscape-install-qa-') as td:
        source = Path(td) / 'source.svg'
        source.write_bytes(SOURCE)

        def run(folder, descriptor, data=SOURCE, extra=()):
            path = args.packages_dir / folder / descriptor
            tree = etree.parse(str(path))
            if not schema.validate(tree):
                raise RuntimeError(str(schema.error_log))
            command = tree.find('inx:script/inx:command', NS)
            assert command.get('interpreter') is None
            executable = path.parent / command.text
            assert executable.is_file() and os.access(executable, os.X_OK)
            parameters = []
            for param in tree.findall('.//inx:param', NS):
                if param.get('type') == 'notebook':
                    continue
                value = param[0].get('value') if param.get('type') == 'optiongroup' else param.text or ''
                parameters.append('--' + param.get('name') + '=' + value)
            source.write_bytes(data)
            result = subprocess.run([str(executable), str(source), *parameters, *extra],
                                    env=env, capture_output=True, timeout=40)
            if result.returncode or not result.stdout.strip():
                raise RuntimeError(f'{descriptor}: exit {result.returncode}: {result.stderr.decode()}')
            root = etree.fromstring(result.stdout)
            assert root.tag == '{http://www.w3.org/2000/svg}svg'
            assert not result.stderr.strip(), (descriptor, result.stderr.decode())
            results.append({'id': tree.find('inx:id', NS).text, 'descriptor': str(path),
                            'exit_code': result.returncode, 'valid_svg': True, 'schema_valid': True})
            return result.stdout, root

        data, root = run('Logo-Construction', 'logo_construction_reference.inx', extra=['--id=ref'])
        assert root.get('data-logo-construction-reference') == 'ref'
        data, root = run('Logo-Construction', 'logo_construction.inx', data, ['--id=logo'])
        assert root.xpath('//*[@data-logo-construction and @data-lc-role="diagram"]')
        data, root = run('Blend-Tool-Pro', 'blend_tool_spine.inx', extra=['--id=spine'])
        assert root.get('data-blend-spine-reference') == 'spine'
        data, root = run('Blend-Tool-Pro', 'blend_tool_pro.inx', data,
                         ['--id=a', '--id=b', '--steps=4', '--shading_mode=tube'])
        blend = root.xpath('//*[@data-blend-tool-pro]')[0]
        assert root.xpath('//*[@data-blend-shading="tube"]')
        data, root = run('Blend-Tool-Pro', 'blend_tool_manage.inx', data, ['--id=' + blend.get('id')])
        assert len(root.xpath('//*[@data-blend-tool-pro]')) == 1
        data, root = run('Vector-Effects-Pro', 'vector_effects_pro.inx', extra=['--id=logo'])
        effect = root.xpath('//*[@data-vector-effects-pro]')[0]
        data, root = run('Vector-Effects-Pro', 'vector_effects_manage.inx', data, ['--id=' + effect.get('id')])
        assert len(root.xpath('//*[@data-vector-effects-pro]')) == 1
        for filename, setting in [('vector_effects_grain.inx', 'grain'), ('vector_effects_noise.inx', 'noise')]:
            data, root = run('Vector-Effects-Pro', filename, extra=['--id=logo'])
            effect = root.xpath('//*[@data-vector-effects-pro]')[0]
            assert json.loads(effect.get('data-vep-settings'))[setting]
            assert root.xpath('//*[local-name()="feTurbulence"]')
    assert len(results) == 9
    args.output.write_text(json.dumps({'status': 'passed', 'commands': results,
                                      'environment': 'bundled PYTHONHOME and PYTHONPATH simulated'},
                                     ensure_ascii=False, indent=2))
    print(f'PASS: {len(results)} INX commands executed; valid editable SVG, local launchers and 3D shading verified.')


if __name__ == '__main__':
    main()
