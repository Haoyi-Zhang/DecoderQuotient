"""Check the actual Python schematic consumers in a two-folder package."""
from pathlib import Path
import re
NAMES = ('evidence-flow', 'quotient-layer')
def check_schematics(paper, artifact):
    paper, artifact = Path(paper), Path(artifact)
    for name in NAMES:
        pdf = artifact/'figures'/(name+'.pdf')
        if not pdf.is_file() or not pdf.read_bytes().startswith(b'%PDF-'):
            raise ValueError('Missing or invalid schematic PDF: '+name)
        wrapper = re.sub(r'%[^\n]*', '', (paper/'figures'/(name+'.tex')).read_text(encoding='utf-8')).strip()
        if wrapper != r'\includegraphics{../artifact/figures/'+name+'.pdf}':
            raise ValueError('Schematic wrapper must consume the generated PDF: '+name)
    if not (artifact/'figures/draw_schematics.py').is_file():
        raise ValueError('Missing independent Python schematic generator')
    return {'schematics': list(NAMES), 'consumer_paths_checked': 2}
