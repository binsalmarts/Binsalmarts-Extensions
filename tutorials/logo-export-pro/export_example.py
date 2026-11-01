"""Export the actual tutorial kit with the local extension and Inkscape."""
import os
import runpy
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[2]
here = Path(__file__).resolve().parent
sys.path.append('/Applications/Inkscape.app/Contents/Resources/share/inkscape/extensions')
sys.path.append('/Applications/Inkscape.app/Contents/Resources/lib/python3.10/site-packages')
os.environ['INKSCAPE_COMMAND'] = '/private/tmp/logo-inkscape-test-wrapper.py'
sys.argv = [str(root / 'logo_export_pro.py'),
    '--id=tutorial-horizontal', '--id=tutorial-vertical', '--id=tutorial-icon',
    '--source_mode=ready', '--brand_name=النخاله',
    '--preserve_white_cutouts=false', '--open_folder=false',
    '--background_color=0x6b7280ff',
    '--output_dir=' + str(here / 'output'),
    '--output=/private/tmp/logo-tutorial-result.svg',
    str(here / 'Logo-Export-Tutorial.svg')]
runpy.run_path(str(root / 'logo_export_pro.py'), run_name='__main__')
