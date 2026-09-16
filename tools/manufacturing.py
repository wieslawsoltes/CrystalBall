"""Generate traceable manufacturing tables and handbook. Does not approve manufacture."""
from __future__ import annotations
import csv
import hashlib
import html
import json
from pathlib import Path
import re
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'manufacturing/generated'

# Carrier pin order is checked against the generated circuit contract at generation time.
HARNESS={
 'J4':('W04','Adafruit 1770',['VIN','GND','CLK','MOSI','CS','D/C','RST','LITE'],['5V_SYS','GND','LCD_SCK_R','LCD_MOSI_R','LCD_CS','LCD_DC','LCD_RST','LCD_BL'],130,26),
 'J5':('W05','Adafruit 3421',['3V','GND','BCLK','LRCL','DOUT','SEL'],['3V3','GND','MIC_BCLK','MIC_WS','MIC_SD','GND'],130,26),
 'J6':('W06','Adafruit 3006',['VIN','GND','BCLK','LRC','DIN','SD'],['5V_SYS','GND','AMP_BCLK','AMP_WS','AMP_DIN','AMP_SD'],100,26),
 'J7':('W07','16-pixel WS2812B strip',['5V','GND','DIN'],['5V_SYS','GND','LED_DIN'],120,24),
 'J8':('W08','TALK normally-open momentary',['NO contact','other contact'],['PTT','GND'],140,26),
 'J9':('W09','PAGE normally-open momentary',['NO contact','other contact'],['NEXT','GND'],130,26),
 'J10':('W10','Red recording LED',['anode','cathode'],['REC_ANODE','GND'],130,26)
}
PURCHASED=[
 ['M01',1,'ESP32-S3-DevKitC-1-N8R8 v1.1','Espressif','Verify board revision, PSRAM, pinout and seating height'],
 ['M02',1,'1770 ILI9341 2.8-inch TFT breakout','Adafruit','IM1/IM2/IM3 closed; IM0 open; verify active optical plane'],
 ['M03',1,'3421 SPH0645 I2S microphone','Adafruit','SEL to ground; microphone port unobstructed'],
 ['M04',1,'3006 MAX98357A amplifier','Adafruit','BTL speaker pair; neither lead to ground'],
 ['M05',1,'5807 HUSB238 PD breakout','Adafruit','5 V jumper closed; 3 A current request; verify unloaded voltage'],
 ['M06',1,'16 x WS2812B on flexible strip','Supplier selection required','Pitch, width, bend radius and power qualification required'],
 ['M07',1,'40 mm envelope / 8 ohm / 2 W speaker','Supplier selection required','Exact part, depth, lugs and acoustic response unqualified'],
 ['M08',1,'USB-C external 5 V / 3 A capable supply','Supplier selection required','Market-compliant finished adapter; PD/cable qualification'],
 ['M09',1,'USB-C cable for selected supply','Supplier selection required','Connector, current, bend and strain relief qualification'],
 ['M10',2,'12 mm nominal panel momentary NO switch','Supplier selection required','Hole 12.2; rear depth and contact quality unqualified'],
 ['M11',1,'M6 nominal panel master switch','Supplier selection required','DC switching rating and contact heating qualification'],
 ['M12',1,'3 mm red panel recording LED','Supplier selection required','3.2 hole; colour/current/retention qualification'],
 ['M13',1,'120 mm OD / 2 mm wall optical PMMA globe','Custom optical supplier','Open-bottom sphere; flange bond and optical quality qualification'],
 ['M14',1,'70 x 80 x 1 mm visible beamsplitter','Custom optical supplier','Nominal 70R/30T front coating; rear AR; angle/polarization review'],
 ['M15',1,'Optical edge pads / gasket / non-shedding foam','Supplier selection required','Compatibility, compression, ageing and retention qualification']
]
FASTENERS=[
 ['F01','Bottom cover to shell',4,'M3 machine screw, initial M3x8','4 x M3 heat-set inserts','Verify 4.2 mm pilot and blind engagement'],
 ['F02','Optical deck to shell',4,'M3 machine screw, initial M3x8','4 x M3 heat-set inserts','Verify 4.2 mm pilot; no screw bottoming'],
 ['F03','Carrier to standoffs',4,'M3 plastic-thread screw, initial x6','2.5 mm pilot','Do not use metal-thread torque assumptions'],
 ['F04','LCD to standoffs',4,'M3 plastic-thread screw, initial x6','2.5 mm pilot','Real board hole diameter/stack must be measured'],
 ['F05','Speaker cradle to deck',2,'M3 plastic-thread screw, initial x6','2.5 mm blind pilots','Locations (-8,-40), (37,-38)'],
 ['F06','PD sled to supports',2,'M3 plastic-thread screw, initial x6','2.5 mm pilots','Verify PCB retention separately'],
 ['F07','Mirror upright feet',4,'M2 plastic-thread screw, initial x6','1.7 mm pilots','Do not break through deck'],
 ['F08','Mirror pivot pair',2,'M3 screw, initial x12 + nylon washer + locknut','3.3 mm pivot bores','Set friction without bending frame or loading glass'],
 ['F09','Split globe retainer',4,'M3 plastic-thread screw, initial x6','2.5 mm pilots / 3.3 mm clearance','Verify flange compression and pull-out'],
 ['F10','Mirror retainer',4,'M2 plastic-thread screw, initial x6','Match modeled pilots','Qualified compliant pads; no glass contact'],
 ['F11','Speaker/harness retention','as routed','Nonconductive ties and mounts','Supplier selection required','No load transmitted to acoustic/optical parts']
]
ACCEPTANCE=[
 ['A01','PCB','Bare board electrical test','Released IPC-D-356 continuity/isolation','Every bare board','Unpowered'],
 ['A02','PCB','Profile / thickness / hole plating','Supplier-approved drawing and stackup','Incoming lot / FAI','Unpowered'],
 ['A03','Assembly','Polarity / connector numbering / solder','No bridges, wrong polarity, incomplete latch or cold joints','Every unit','Unpowered'],
 ['A04','Power','PD output before carrier connection','PROPOSED 4.75..5.25 V; approved adapter and cable','Every unit','Isolated low-voltage supply'],
 ['A05','Power','3V3 operating rail','PROPOSED 3.135..3.465 V plus module transient limits','Every unit / detailed FAI','Suitable probe ground'],
 ['A06','Power','Inrush, droop, fault, reverse-input','Reviewed waveform and protected fault-test procedure','Design qualification','Reviewed bench setup'],
 ['A07','Thermal','Worst permitted radio/LED/audio duty','PROPOSED case <=45 C at 25 C ambient; final applicable limits govern','Design qualification / soak','Measure stabilized temperatures'],
 ['A08','Input','TALK/PAGE held and released','Single capture; <=8 s; no held-button erase starvation','Every unit','No live credentials in report'],
 ['A09','Privacy','Mic/REC status / idle I2S clocks','No capture or microphone clocks outside requested recording','FAI / every-unit functional','Logic analyzer + acoustic stimulus'],
 ['A10','Display','Calibration / full text / orientation','All intended operator glyphs legible and correctly oriented','Every unit','Calibration firmware'],
 ['A11','Optics','Viewing-volume recognition grid','PROPOSED operator >=95%, client <=5%; zones approved first','Design qualification / sampled audit','Distances, angles and lux recorded'],
 ['A12','Audio','I2S sample shift / clipping / gain','Known stimulus; no clipping at approved level; correct sample alignment','Design qualification','Differential BTL measurements only'],
 ['A13','Privacy','Erase / offline / cancellation','Browser 90 s; firmware configured 120 s default; disconnect hides old answer','Every unit / software regression','Test held controls and network loss'],
 ['A14','Network','TLS trust, bad cert and bad token','Valid request succeeds; invalid cert/token fails closed','Every deployment','Never disable TLS'],
 ['A15','Security','Provisioning / boot / recovery / revocation','Owner-approved signed/encrypted production process','Production qualification','No automatic eFuse operations'],
 ['A16','API','Paid text / STT / TTS / optional Realtime','Owner key, approved account models, bounded failure recovery','Commissioning / regression','Explicit spend authorization'],
 ['A17','Mechanical','Fits / retention / cable routing','No hard optical contact, pinched cable or insecure globe','Every unit / FAI','Real parts, not envelope proxies'],
 ['A18','Compliance','Radio, EMC, ESD, market safety','Competent assessment and applicable test evidence','Design qualification','Accredited/competent lab as required'],
 ['A19','Transport','Globe restraint and pack integrity','Owner-approved packaging/drop/transport plan','Packaging qualification','No point load on optical globe'],
 ['A20','Visual','Mobile / desktop / physical appearance','Owner-approved comparison; no 100% identity claim without acceptance','Design acceptance','Actual Safari/iPhone and hardware']
]

def table_csv(name,headers,rows):
    with (OUT/name).open('w',newline='',encoding='utf-8') as stream:
        w=csv.writer(stream);w.writerow(headers);w.writerows(rows)


def pdf(text, tables):
    styles=getSampleStyleSheet()
    styles.add(ParagraphStyle('BodyOrb',fontName='Helvetica',fontSize=9.2,leading=13.5,spaceAfter=7,textColor=colors.HexColor('#233244')))
    styles.add(ParagraphStyle('SmallOrb',parent=styles['BodyOrb'],fontSize=7,leading=9.5,spaceAfter=3,wordWrap='CJK'))
    styles.add(ParagraphStyle('HeadOrb',fontName='Helvetica-Bold',fontSize=16,leading=20,spaceBefore=15,spaceAfter=9,textColor=colors.HexColor('#202338'),keepWithNext=True))
    styles.add(ParagraphStyle('CoverOrb',fontName='Helvetica-Bold',fontSize=35,leading=40,spaceAfter=16,textColor=colors.HexColor('#202338')))
    story=[Spacer(1,55),Paragraph('CRYSTALBALL',styles['CoverOrb']),Paragraph('Aether Orb / Rev B',styles['HeadOrb']),Paragraph('Manufacturing engineering handoff',styles['Title']),Spacer(1,22),Paragraph('ENGINEERING CANDIDATE<br/>NOT APPROVED FOR PRODUCTION',styles['HeadOrb']),Paragraph('Editable ECAD and mechanical sources. Firmware and browser implementation. Assembly, commissioning, verification and release-control records.',styles['BodyOrb']),Spacer(1,25),Paragraph('Read the release gates before ordering components or manufacturing parts. Physical measurements, optical performance and authorized sign-off remain mandatory.',styles['BodyOrb']),Spacer(1,45),Paragraph('Document date: 16 September 2026<br/>Units: millimetres unless specified<br/>Audience: electrical, mechanical, optical and manufacturing reviewers',styles['BodyOrb']),PageBreak()]
    paragraph=[]
    def flush():
        if paragraph:
            content=html.escape(' '.join(paragraph));content=re.sub(r'\*\*(.*?)\*\*',r'<b>\1</b>',content)
            story.append(Paragraph(content,styles['BodyOrb']));paragraph.clear()
    for line in text.splitlines()[2:]:
        if line.startswith('## '):
            flush();story.append(Paragraph(html.escape(line[3:]),styles['HeadOrb']))
        elif line.startswith('- '):
            flush();story.append(Paragraph(html.escape(line[2:]),styles['SmallOrb']))
        elif not line.strip():flush()
        else:paragraph.append(line)
    flush()
    for title,heads,rows,widths in tables:
        story.extend([PageBreak(),Paragraph(title,styles['HeadOrb']),Paragraph('Engineering selections. Supplier and first-article approval required. Full machine-readable tables are supplied as CSV.',styles['BodyOrb'])])
        cells=[[Paragraph(html.escape(str(x)),styles['SmallOrb']) for x in row] for row in [heads]+rows]
        t=Table(cells,colWidths=widths,repeatRows=1,hAlign='LEFT')
        t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#e9e4f1')),('VALIGN',(0,0),(-1,-1),'TOP'),('LINEBELOW',(0,0),(-1,0),.6,colors.HexColor('#807191')),('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,colors.HexColor('#f5f7fa')]),('LEFTPADDING',(0,0),(-1,-1),5),('RIGHTPADDING',(0,0),(-1,-1),5),('TOPPADDING',(0,0),(-1,-1),5),('BOTTOMPADDING',(0,0),(-1,-1),5)]));story.append(t)
    def footer(canvas,doc):
        canvas.saveState();w,h=A4;canvas.setStrokeColor(colors.HexColor('#d6dbe2'));canvas.line(42,38,w-42,38);canvas.setFont('Helvetica',7);canvas.setFillColor(colors.HexColor('#526171'));canvas.drawString(42,26,'CRYSTALBALL / REV B  |  ENGINEERING CANDIDATE - NOT PRODUCTION RELEASED');canvas.drawRightString(w-42,26,str(doc.page));canvas.restoreState()
    SimpleDocTemplate(str(OUT/'CrystalBall-RevB-Handbook.pdf'),pagesize=A4,rightMargin=42,leftMargin=42,topMargin=42,bottomMargin=50,title='CrystalBall Rev B manufacturing engineering handoff',author='CrystalBall engineering',pageCompression=1).build(story,onFirstPage=footer,onLaterPages=footer)


def fixture_dxf(parts):
    # 2D alignment template only: not a complete force-controlled powered fixture.
    entities=[]
    def line(x,y,a,b):entities.extend(['0','LINE','8','OUTLINE','10',str(x),'20',str(y),'11',str(a),'21',str(b)])
    def circle(x,y,r):entities.extend(['0','CIRCLE','8','HOLES','10',str(x),'20',str(y),'40',str(r)])
    for a,b in [((0,0),(120,0)),((120,0),(120,110)),((120,110),(0,110)),((0,110),(0,0))]:line(*a,*b)
    for x,y in [(4,4),(96,4),(4,86),(96,86)]:circle(x+10,100-y,1.6)
    # Crosshairs at test loops. No unqualified probe sleeve diameter is fabricated.
    for p in parts:
        if p['ref'].startswith('TP'):
            x,y=p['x']+10,100-p['y'];line(x-2,y,x+2,y);line(x,y-2,x,y+2)
    (OUT/'fixture-alignment-only.dxf').write_text('\n'.join(['0','SECTION','2','HEADER','9','$INSUNITS','70','4','0','ENDSEC','0','SECTION','2','ENTITIES']+entities+['0','ENDSEC','0','EOF'])+'\n')


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    design=json.loads((ROOT/'hardware/design.json').read_text());parts=design['parts']
    mechanical=json.loads((ROOT/'mechanical/parts.json').read_text())
    table_csv('carrier-bom.csv',['Reference','Qty','Value','Candidate ordering code','Fitted','Footprint','Qualification','Notes','Source'],[[p['ref'],1,p['value'],p['mpn'],p['fitted'],'Aether:'+p['footprint']+'_'+p['ref'],'CANDIDATE; supplier drawing/FAI required',p['note'],p['source']] for p in parts])
    table_csv('purchased-modules.csv',['ID','Qty','Candidate part/specification','Supplier','Qualification notes'],PURCHASED)
    table_csv('component-placements.csv',['Reference','X_mm','Y_mm','Rotation_deg','Side','Coordinate convention'],[[p['ref'],p['x'],p['y'],0,'TOP','PCB origin upper-left; X right; Y down']for p in parts])
    table_csv('all-pad-nets.csv',['Reference','Pin','Net','X_mm','Y_mm','Technology'],[[p['ref'],pad['number'],pad['net'],round(p['x']+pad['x'],4),round(p['y']+pad['y'],4),pad['kind']]for p in parts for pad in p['pads']])
    harness=[]
    for ref,(wid,dest,labels,nets,length,awg) in HARNESS.items():
        pads=next(p['pads']for p in parts if p['ref']==ref)
        actual=[p['net']for p in pads]
        if actual!=nets:raise ValueError(f'Harness pin contract drift at {ref}: {actual}')
        for i,(net,label) in enumerate(zip(nets,labels),1):
            colour='black' if net=='GND' else 'red' if net in ('5V_SYS','3V3') else ['white','yellow','green','blue','orange','violet','grey','brown'][i-1]
            harness.append([wid,ref,i,net,dest,label,awg,colour,length,'PROPOSED cut length; validate on FAI'])
    harness.extend([['W01','PD OUT+',1,'VIN_5V','master switch','input lug',22,'red',80,'Verify switch DC rating'],['W02','master switch',2,'VIN_5V','J3','pin 1',22,'red',120,'5 V only; no USB dual-power'],['W03','PD OUT-',1,'GND','J3','pin 2',22,'black',160,'Route beside positive supply'],['W11','amplifier SPK+',1,'BTL+','8 ohm speaker','positive',26,'white',100,'Twisted pair; neither wire grounded'],['W11','amplifier SPK-',2,'BTL-','8 ohm speaker','negative',26,'white/black',100,'Twisted pair; neither wire grounded']])
    table_csv('harness.csv',['Harness','From','Pin','Net','To','Labelled pad','AWG','Colour','Initial_length_mm','Status/notes'],harness)
    table_csv('mechanical-inventory.csv',['Part','Modeled_qty','Role','Material','Process','BBox_mm','Notes'],[[p['name'],1,'REFERENCE ONLY; procure via electrical/module BOM' if p['name'].startswith('REF_') else 'PROCESS COUPON; not an assembly part' if 'coupon' in p['name'] else 'FABRICATED/OPTICAL PART',p['material'],p['process'],' x '.join(map(str,p['bbox_mm'])),p['note']]for p in mechanical])
    table_csv('fasteners-initial.csv',['ID','Joint','Qty','Candidate screw','Mating feature','Qualification'],FASTENERS)
    table_csv('acceptance-plan.csv',['ID','Domain','Test','Criterion','Sampling','Precaution'],ACCEPTANCE)
    table_csv('first-article-record-BLANK.csv',['ID','Unit_serial','Source_commit','Operator','UTC','Instrument/calibration','Measured_result','Evidence_file','Disposition'],[[r[0],'','','','','','','','NOT TESTED'] for r in ACCEPTANCE])
    probes=[[p['ref'],p['pads'][0]['net'],p['x'],p['y'],p['x']+10,100-p['y'],'Loop contact; fixture/sleeve selection unqualified']for p in parts if p['ref'].startswith('TP')]
    table_csv('fixture-testpoint-coordinates.csv',['TP','Net','PCB_X','PCB_Y_down','Template_X','Template_Y_up','Interface'],probes);fixture_dxf(parts)
    text=(ROOT/'manufacturing/handbook.md').read_text()
    blocks=[]
    for para in text.split('\n\n'):
        tag='h1'if para.startswith('# ')else'h2'if para.startswith('## ')else'p'
        para=re.sub(r'^#{1,2} ','',para)
        blocks.append(f'<{tag}>{html.escape(para)}</{tag}>')
    (OUT/'handbook.html').write_text('<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>CrystalBall Rev B manufacturing handoff</title><style>body{max-width:850px;margin:4rem auto;padding:0 2rem;color:#233244;font:16px/1.65 system-ui}h1,h2{color:#202338}h2{margin-top:2.5rem}p{overflow-wrap:anywhere;white-space:pre-line}@media print{body{margin:0;font-size:10pt}h2{break-after:avoid}}</style><body>'+''.join(blocks)+'</body></html>')
    pdf(text,[('Appendix A / Carrier BOM',['Ref','Value','Candidate ordering code'],[[p['ref'],p['value'],p['mpn']]for p in parts],[45,175,291]),('Appendix B / Purchased modules',['ID','Qty','Part/specification','Qualification'],[[r[0],r[1],r[2],r[4]]for r in PURCHASED],[32,25,205,249]),('Appendix C / Harness contract',['ID','From/pin','Net','To / labelled pad','AWG / initial mm'],[[r[0],str(r[1])+'/'+str(r[2]),r[3],str(r[4])+' / '+str(r[5]),str(r[6])+' / '+str(r[8])]for r in harness],[36,70,90,240,75]),('Appendix D / Initial fastener schedule',['ID','Joint / qty','Initial selection','Qualification'],[[r[0],r[1]+' / '+str(r[2]),r[3]+'; '+r[4],r[5]]for r in FASTENERS],[30,120,200,161]),('Appendix E / Acceptance plan',['ID','Test','Criterion','Sampling / precautions'],[[r[0],r[2],r[3],r[4]+'; '+r[5]]for r in ACCEPTANCE],[30,110,220,151])])
    files={p.name:hashlib.sha256(p.read_bytes()).hexdigest()for p in sorted(OUT.iterdir())if p.is_file() and p.name!='SHA256.json'}
    (OUT/'SHA256.json').write_text(json.dumps(files,indent=2)+'\n')
    print(json.dumps({'carrier_parts':len(parts),'mechanical_parts':len(mechanical),'harness_conductors':len(harness),'release':'ENGINEERING_CANDIDATE','files':list(files)},indent=2))

if __name__=='__main__':main()
