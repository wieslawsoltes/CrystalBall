"""Project-local custom footprints. Library parity is not supplier qualification."""
from pathlib import Path
import re
ROOT = Path(__file__).resolve().parents[1]

def blocks(text: str, tag: str):
    for match in re.finditer(r'\(' + re.escape(tag) + r'\s', text):
        depth = 0
        quoted = escaped = False
        for i in range(match.start(), len(text)):
            c = text[i]
            if escaped:
                escaped = False
            elif quoted and c == '\\':
                escaped = True
            elif c == '"':
                quoted = not quoted
            elif not quoted:
                if c == '(':
                    depth += 1
                elif c == ')':
                    depth -= 1
                    if depth == 0:
                        yield text[match.start():i+1]
                        break
        else:
            raise ValueError('Unbalanced KiCad expression')

def main():
    folder = ROOT / 'hardware/Aether.pretty'
    folder.mkdir(exist_ok=True)
    text = (ROOT/'hardware/aether-carrier.kicad_pcb').read_text()
    for block in blocks(text, 'footprint'):
        name = re.match(r'\(footprint "Aether:([^"\n]+)"', block).group(1)
        fp = block.replace(f'"Aether:{name}"', f'"{name}" (version 20221018) (generator aether_orb)', 1)
        fp = re.sub(r'\(at [^()]+\)', '', fp, count=1)
        fp = re.sub(r'\(path "[^"]*"\)|\(tstamp [^()]+\)|\(net \d+ "(?:\\.|[^"\\])*"\)', '', fp)
        fp = re.sub(r'\(fp_text reference "[^"]*"', '(fp_text reference "REF**"', fp)
        (folder / (name+'.kicad_mod')).write_text(fp+'\n')
    (ROOT/'hardware/fp-lib-table').write_text('(fp_lib_table (lib (name "Aether") (type "KiCad") (uri "${KIPRJMOD}/Aether.pretty") (options "") (descr "CrystalBall custom carrier land patterns")))\n')

if __name__ == '__main__':
    main()
