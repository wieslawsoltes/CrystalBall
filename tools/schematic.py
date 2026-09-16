"""Generate a self-contained, hierarchical KiCad 7+ schematic and review sheets.
Every terminal is explicitly net-labelled; module internals remain vendor-owned designs.
"""
from pathlib import Path
import math, json, uuid, html
from design import *

def uid(s):return str(uuid.uuid5(uuid.NAMESPACE_URL,'aether-orb/reva/'+s))
def q(s):return json.dumps(str(s))
root_id=uid('schematic-root')

def symbol_definition(name,names,ref='J'):
    n=len(names);h=max(5.08,(n+1)*2.54)
    s=[f'(symbol "Aether:{name}" (pin_names (offset .8)) (in_bom yes) (on_board yes)',
       f'(property "Reference" "{ref}" (at 0 4 0) (effects (font (size 1.27 1.27))))',
       f'(property "Value" "{name}" (at 0 1.5 0) (effects (font (size 1.27 1.27))))',
       f'(symbol "{name}_0_1" (rectangle (start 0 0) (end 28 {-h}) (stroke (width .254) (type default)) (fill (type background))))',
       f'(symbol "{name}_1_1"']
    for i,pn in enumerate(names,1):
        s.append(f'(pin passive line (at -5.08 {-i*2.54} 0) (length 5.08) (name {q(pn)} (effects (font (size 1.0 1.0)))) (number "{i}" (effects (font (size 1.0 1.0)))))')
    s+=[')',')'];return '\n'.join(s)

def names(c):
    if c.ref=='Q1':return ['GATE','SOURCE','DRAIN']
    if c.ref=='U1':return ['/OE','A','GND','Y','VCC']
    if c.ref.startswith('R'):return ['1','2']
    if c.ref.startswith('C'):return ['+' if c.ref=='C1' else '1','-' if c.ref=='C1' else '2']
    return [p.net.replace('NC_','NC ') for p in c.pads]

def make_sheet(name,title,parts,positions,notes):
    sid=uid(name);sheetinst=uid(name+'-instance')
    defs={c.ref:symbol_definition(c.ref,names(c),c.ref.rstrip('0123456789')) for c in parts}
    s=[f'(kicad_sch (version 20230121) (generator aether_orb) (uuid {sid}) (paper "A3")',
       f'(title_block (title {q(title)}) (date "2026-09-16") (rev "A - engineering") (company "Aether Orb") (comment 1 "PROTOTYPE; vendor-module internals not reproduced"))',
       '(lib_symbols '+'\n'.join(defs.values())+')']
    svg=['<svg xmlns="http://www.w3.org/2000/svg" width="1680" height="1188" viewBox="0 0 420 297">',
         '<rect width="420" height="297" fill="#f8fafc"/>',
         f'<text x="16" y="17" font-family="sans-serif" font-size="6" fill="#132538">{html.escape(title)}</text>',
         '<text x="16" y="25" font-family="sans-serif" font-size="3" fill="#536675">AETHER ORB / REV A · Net labels connect globally across sheets · Engineering prototype</text>']
    for c in parts:
        x,y=positions[c.ref];h=max(5.08,(len(c.pads)+1)*2.54)
        # Positions below are symbol origin (top-left of body).
        s.append(f'''(symbol (lib_id "Aether:{c.ref}") (at {x} {y} 0) (unit 1) (in_bom yes) (on_board yes) (dnp no) (uuid {uid(c.ref+'-sch')})
           (property "Reference" {q(c.ref)} (at {x+14} {y-5} 0) (effects (font (size 1.27 1.27))))
           (property "Value" {q(c.value)} (at {x+14} {y-2.5} 0) (effects (font (size 1.05 1.05))))
           (property "Footprint" {q('Aether:'+c.footprint)} (at {x} {y} 0) (effects (font (size 1.27 1.27)) hide))
           (property "Datasheet" {q(c.source)} (at {x} {y} 0) (effects (font (size 1.27 1.27)) hide))
           (instances (project "aether-carrier" (path "/{root_id}/{sheetinst}" (reference {q(c.ref)}) (unit 1)))) )''')
        svg.append(f'<rect x="{x}" y="{y}" width="28" height="{h}" rx="1" fill="#e9f0f4" stroke="#23465b" stroke-width=".35"/>')
        svg.append(f'<text x="{x+14}" y="{y-5}" text-anchor="middle" font-family="sans-serif" font-weight="bold" font-size="3.3" fill="#142e40">{html.escape(c.ref)}</text>')
        svg.append(f'<text x="{x+14}" y="{y-1.8}" text-anchor="middle" font-family="sans-serif" font-size="2.6" fill="#415e6c">{html.escape(c.value)}</text>')
        for i,p in enumerate(c.pads,1):
            px=x-5.08;py=y+i*2.54
            if p.net.startswith('NC_'):
                s.append(f'(no_connect (at {px} {py}) (uuid {uid(c.ref+"-nc"+str(i))}))')
                svg.append(f'<path d="M {px-.7} {py-.7} l 1.4 1.4 m -1.4 0 l 1.4 -1.4" stroke="#78858c" stroke-width=".25"/>')
            else:
                s.append(f'(wire (pts (xy {px} {py}) (xy {px-6.35} {py})) (stroke (width 0) (type default)) (uuid {uid(c.ref+"-wire"+str(i))}))')
                s.append(f'(global_label {q(p.net)} (shape input) (at {px-6.35} {py} 0) (effects (font (size 1.0 1.0)) (justify left)) (uuid {uid(c.ref+"-label"+str(i))}) (property "Intersheetrefs" "${{INTERSHEET_REFS}}" (at {px-6.35} {py} 0) (effects (font (size 1.0 1.0)) hide)))')
                svg.append(f'<text x="{px-1}" y="{py+.65}" text-anchor="end" font-family="monospace" font-size="2.2" fill="#0e665c">{html.escape(p.net)}</text>')
            svg.append(f'<path d="M {px} {py} H{x}" stroke="#2b5060" stroke-width=".25"/><text x="{x+.8}" y="{py+.65}" font-family="monospace" font-size="2.05" fill="#163849">{i}: {html.escape(names(c)[i-1])}</text>')
    for i,n in enumerate(notes):
        y=255+i*5
        s.append(f'(text {q(n)} (at 18 {y} 0) (effects (font (size 1.25 1.25)) (justify left bottom)) (uuid {uid(name+"-note"+str(i))}))')
        svg.append(f'<text x="16" y="{y}" font-family="sans-serif" font-size="2.9" fill="#3b4b57">{html.escape(n)}</text>')
    s.append(')');svg.append('</svg>')
    (ROOT/f'hardware/{name}.kicad_sch').write_text('\n'.join(s))
    (ROOT/f'preview/{name}.svg').write_text('\n'.join(svg))
    return sheetinst

def main():
    byref={c.ref:c for c in PARTS}
    groups=[
      ('controller','01 / Controller sockets and reserved pins',['J1','J2','JP1','TP3'],
       {'J1':92,'J2':210,'JP1':326,'TP3':326},
       ['Socket pin numbering is the module top view: antenna at the top, USB connectors at the bottom.',
        'Only genuine DevKitC-1 v1.1 N8R8 geometry is qualified by this drawing. No generic ESP32 boards.',
        'GPIO0/3/45/46 (straps), GPIO19/20 (USB), GPIO35/36/37 (PSRAM), GPIO38/48 (RGB variants) are not used.',
        'Remove the controller module from BOTH sockets before USB flashing. Never connect USB and carrier power together.']),
      ('power-led','02 / Protected power and 5 V LED interface',['J3','F1','Q1','R1','C1','U1','C2','R5','R6','J7','TP1','TP2','TP4'],{},
       ['External HUSB238: keep 5V jumper CLOSED; cut 1A and leave 2A OPEN to request 3A. Verify unloaded output first.',
        'Q1: drain = FUSED5, source = 5V_SYS, gate = R1 to GND. Reverse-polarity protection, NOT an eFuse or OVP.',
        'Use only the qualified 5 V / 3 A PD adapter. Test C1 inrush; F1 derates with enclosure temperature.',
        'SN74AHCT1G125 is TTL-compatible. Do not substitute an HC buffer. Keep the LED cable under 100 mm.']),
      ('interfaces','03 / Display, audio and operator harnesses',['J4','J5','J6','R2','R3','R4','C3','J8','J9','J10','R7','R8','R9'],{},
       ['J4 goes to Adafruit 1770 ILI9341 in SPI mode: close IM1/IM2/IM3 as specified in the module guide.',
        'J5: SPH0645 microphone; 3.3 V ONLY. SEL to GND, left slot. Unplug the whole harness for hardware isolation.',
        'J6: Adafruit 3006 MAX98357A. Speaker connects directly to amp +/-. Neither output may connect to ground.',
        'J8/J9 momentary NO to GND. J10 LED anode pin 1, cathode pin 2. R7 is already on the carrier.'])]
    root=[f'(kicad_sch (version 20230121) (generator aether_orb) (uuid {root_id}) (paper "A4") (lib_symbols)',
          '(title_block (title "Aether Orb - Rev A carrier") (date "2026-09-16") (rev "A / ENGINEERING") (company "Aether Orb"))']
    for k,(name,title,refs,xs,notes) in enumerate(groups):
        parts=[byref[r] for r in refs];positions={}
        if name=='controller':positions={'J1':(92,55),'J2':(210,55),'JP1':(326,60),'TP3':(326,105)}
        elif name=='power-led':
            positions={r:p for r,p in zip(refs,[(72,50),(164,50),(256,50),(348,50),(72,110),(164,110),(256,110),(348,110),(72,180),(164,180),(256,180),(302,180),(348,180)])}
        else:
            positions={r:p for r,p in zip(refs,[(72,50),(164,50),(256,50),(348,50),(348,95),(256,130),(164,130),(72,165),(164,185),(256,185),(348,145),(72,220),(348,215)])}
        sid=make_sheet(name,title,parts,positions,notes)
        y=45+k*45
        root.append(f'''(sheet (at 40 {y}) (size 205 27) (stroke (width .254) (type default)) (fill (color 0 0 0 0)) (uuid {sid})
          (property "Sheetname" {q(title)} (at 40 {y-.8} 0) (effects (font (size 1.27 1.27)) (justify left bottom)))
          (property "Sheetfile" "{name}.kicad_sch" (at 40 {y+27.8} 0) (effects (font (size 1.27 1.27)) (justify left top)))
          (instances (project "aether-carrier" (path "/{root_id}" (page "{k+2}")))))''')
    root.append(f'(sheet_instances (path "/" (page "1"))) (text "ENGINEERING PROTOTYPE - INDEPENDENT ERC/DRC, FOOTPRINT AND CAM REVIEW REQUIRED" (at 25 190 0) (effects (font (size 1.2 1.2)) (justify left))) )')
    (ROOT/'hardware/aether-carrier.kicad_sch').write_text('\n'.join(root))
    # Human / machine readable electrical netlist in KiCad XML interchange form.
    import xml.etree.ElementTree as ET
    r=ET.Element('export',version='D');cs=ET.SubElement(r,'components');ns=ET.SubElement(r,'nets')
    for c in PARTS:
        comp=ET.SubElement(cs,'comp',ref=c.ref);ET.SubElement(comp,'value').text=c.value;ET.SubElement(comp,'footprint').text='Aether:'+c.footprint
    nets=sorted({p.net for c in PARTS for p in c.pads if not p.net.startswith('NC_')})
    for i,n in enumerate(nets,1):
        net=ET.SubElement(ns,'net',code=str(i),name=n)
        for c in PARTS:
            for p in c.pads:
                if p.net==n:ET.SubElement(net,'node',ref=c.ref,pin=p.number)
    ET.indent(r);ET.ElementTree(r).write(ROOT/'hardware/aether-carrier.net',encoding='utf-8',xml_declaration=True)
if __name__=='__main__':main()
