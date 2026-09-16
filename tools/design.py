"""Aether Orb Rev B: single source for the carrier circuit and interfaces.
Units: mm. Board coordinates: x right, y down, viewed from component side.
This file describes OUR carrier, not the internal circuitry of purchased modules.
"""
from dataclasses import dataclass, asdict
from pathlib import Path
import json
ROOT = Path(__file__).resolve().parents[1]
W, H = 100.0, 90.0
PINMAP = {
    'MIC_BCLK':4, 'MIC_WS':5, 'MIC_SD':6,
    'LCD_BL':7, 'LCD_RST':8, 'LCD_DC':9, 'LCD_CS':10,
    'LCD_MOSI':11, 'LCD_SCK':12,
    'NEXT':13, 'PTT':14, 'AMP_SD':15,
    'AMP_BCLK':16, 'AMP_WS':17, 'AMP_DIN':18,
    'LED_DATA':21, 'REC_LED':47,
}
@dataclass
class Pad:
    number: str
    x: float
    y: float
    net: str
    diameter: float = 1.8
    drill: float = 1.0
    sx: float = 0
    sy: float = 0
    shape: str = 'circle'
    kind: str = 'thru_hole'
@dataclass
class Part:
    ref: str
    value: str
    footprint: str
    x: float
    y: float
    pads: list
    body: tuple
    mpn: str
    note: str = ''
    source: str = ''
    fitted: bool = True
    def abs_pads(self):
        return [dict(asdict(p),x=self.x+p.x,y=self.y+p.y,ref=self.ref) for p in self.pads]
PARTS=[]
def part(ref,value,fp,x,y,pads,body,mpn,note='',source='',fitted=True):
    p=Part(ref,value,fp,x,y,pads,body,mpn,note,source,fitted);PARTS.append(p);return p

def header(ref, label, x,y,nets,pitch=2.5, mpn=None):
    n=len(nets)
    return part(ref,label,f'XH_1x{n:02d}_P{pitch:.2f}',x,y,
        [Pad(str(i+1),0,i*pitch,net,1.85,1.0,shape='rect' if i==0 else 'circle') for i,net in enumerate(nets)],
        (-2.4,-2.5,5.0,(n-1)*pitch+5.0),mpn or f'JST B{n}B-XH-A(LF)(SN)',
        'Vertical keyed XH header; pin 1 is square; qualify exact supplier drawing.',
        'https://www.jst-mfg.com/product/pdf/eng/eXH.pdf')

def resistor(ref,x,y,n1,n2,value,mpn):
    return part(ref,value,'R_0805_2012Metric',x,y,
        [Pad('1',-1.0,0,n1,0,0,1.2,1.4,'rect','smd'),Pad('2',1.0,0,n2,0,0,1.2,1.4,'rect','smd')],
        (-1,-.65,2,1.3),mpn)

def cap(ref,x,y,n1,n2,value='100nF',mpn='GRM21BR71H104KA01L'):
    return part(ref,value,'C_0805_2012Metric',x,y,
        [Pad('1',-1,0,n1,0,0,1.2,1.4,'rect','smd'),Pad('2',1,0,n2,0,0,1.2,1.4,'rect','smd')],
        (-1,-.65,2,1.3),mpn)
# Socket geometry from the official Espressif v1.1 mechanical drawing:
# 25.40 mm PCB width, 1.27 mm edge-to-row offset => 22.86 mm row spacing.
left=['3V3','3V3','NC_EN','MIC_BCLK','MIC_WS','MIC_SD','LCD_BL','AMP_SD','AMP_BCLK','AMP_WS','AMP_DIN','NC_GPIO8_DUP']
# GPIO8 is LCD_RST (header position 12); positions 15+ are GPIO9..14.
left[11]='LCD_RST'
left += ['NC_GPIO3','NC_GPIO46','LCD_DC','LCD_CS','LCD_MOSI','LCD_SCK','NEXT','PTT','DEV_5V','GND']
right=['GND','NC_TX43','NC_RX44','NC_GPIO1','NC_GPIO2','NC_GPIO42','NC_GPIO41','NC_GPIO40','NC_GPIO39','NC_GPIO38','NC_GPIO37','NC_GPIO36','NC_GPIO35','NC_GPIO0','NC_GPIO45','NC_GPIO48','REC_LED','LED_DATA','NC_USB20','NC_USB19','GND','GND']
for ref,x,nets in [('J1',14.0,left),('J2',36.86,right)]:
    part(ref,'DevKitC-1 socket '+('J1' if ref=='J1' else 'J3'),'Socket_1x22_P2.54',x,16,
        [Pad(str(i+1),0,2.54*i,n,1.8,1.0,shape='rect' if i==0 else 'circle') for i,n in enumerate(nets)],
        (-1.4,-1.4,2.8,56.14),'Samtec SSQ-122-03-G-S',
        'Use genuine ESP32-S3-DevKitC-1-N8R8 v1.1. Remove module before USB flashing.',
        'https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32s3/esp32-s3-devkitc-1/user_guide_v1.1.html')
# External PD module supplies only 5 V. Manual master switch is in its output harness.
part('J3','5V INPUT','Terminal_1x02_P5.08',72,82,
     [Pad('1',0,0,'VIN5',2.8,1.3,shape='rect'),Pad('2',5.08,0,'GND',2.8,1.3)],
     (-2.6,-4,10.3,8),'Phoenix Contact 1729128',
     '5.08 mm 2-position terminal; 5 V only. + pin 1; - pin 2. Verify exact holder body.',
     'https://www.phoenixcontact.com/en-us/products/pcb-terminal-block-mkds-15-2-508-1729128')
part('F1','PTC 2.5A','PTC_P5.08',57,78,
     [Pad('1',0,0,'VIN5',2.4,1.0),Pad('2',5.08,0,'FUSED5',2.4,1.0)],
     (-5.6,-2.1,16.2,4.2),'Littelfuse RXEF250',
     'Thermal resettable fuse, not a precise electronic current limiter. Check hold-current derating.',
     'https://www.littelfuse.com/products/polyswitch-resettable-ptcs/radial-leaded/rxef')
# Reverse-input PMOS: D=input, S=protected output, G=ground via R1.
part('Q1','AO3401A','SOT-23',59,67,
     [Pad('1',-.95,1,'Q_GATE',0,0,.9,1.1,'rect','smd'),
      Pad('2',.95,1,'5V_SYS',0,0,.9,1.1,'rect','smd'),
      Pad('3',0,-1,'FUSED5',0,0,.9,1.1,'rect','smd')],
     (-1.5,-.65,3,1.3),'AO3401A',
     'P-channel reverse-input protection. Pin 1 G, pin 2 S, pin 3 D. NOT reverse-current blocking while on.',
     'https://www.aosmd.com/res/data_sheets/AO3401A.pdf')
resistor('R1',54,67,'Q_GATE','GND','100k','RC0805FR-07100KL')
part('C1','1000uF 10V','CP_Radial_D10_P5',80,70,
     [Pad('1',0,0,'5V_SYS',2.4,1.0,shape='rect'),Pad('2',5,0,'GND',2.4,1.0)],
     (-2.5,-5,10,10),'Panasonic EEU-FR1A102',
     'Polarized; + pin 1. Measure PD startup/inrush with this bulk capacitance.',
     'https://industrial.panasonic.com/ww/products/pt/aluminum-cap/models/EEUFR1A102')
part('JP1','RUN POWER','PinHeader_1x02_P2.54',42,77,
     [Pad('1',0,0,'5V_SYS'),Pad('2',2.54,0,'DEV_5V')],
     (-1.4,-1.4,5.34,2.8),'Samtec TSW-102-07-G-S + 2.54mm shunt',
     'Fitted shunt for RUN. Remove DevKit completely for USB flashing; do not dual-power.')
header('J4','LCD',92,15,['5V_SYS','GND','LCD_SCK_R','LCD_MOSI_R','LCD_CS','LCD_DC','LCD_RST','LCD_BL'])
resistor('R2',72,21,'LCD_SCK','LCD_SCK_R','33R','RC0805FR-0733RL')
resistor('R3',72,27,'LCD_MOSI','LCD_MOSI_R','33R','RC0805FR-0733RL')
header('J5','MIC 3V3',53,16,['3V3','GND','MIC_BCLK','MIC_WS','MIC_SD','GND'])
header('J6','AMP 5V',92,44,['5V_SYS','GND','AMP_BCLK','AMP_WS','AMP_DIN','AMP_SD'])
resistor('R4',81,54,'AMP_SD','GND','10k','RC0805FR-0710KL')
# Gate uses TTL-compatible input thresholds at 5V, not an HC part.
part('U1','SN74AHCT1G125','SOT-23-5',63,44,
    [Pad('1',-.95,1.1,'GND',0,0,.65,1.2,'rect','smd'),
     Pad('2',0,1.1,'LED_DATA',0,0,.65,1.2,'rect','smd'),
     Pad('3',.95,1.1,'GND',0,0,.65,1.2,'rect','smd'),
     Pad('4',.95,-1.1,'LED_5V_BUF',0,0,.65,1.2,'rect','smd'),
     Pad('5',-.95,-1.1,'5V_SYS',0,0,.65,1.2,'rect','smd')],
    (-1.5,-.8,3,1.6),'SN74AHCT1G125DBVR',
    '5V TTL input buffer; /OE grounded. Qualify TI DBV footprint before ordering.',
    'https://www.ti.com/lit/ds/symlink/sn74ahct1g125.pdf')
cap('C2',59,40,'5V_SYS','GND')
resistor('R5',57,48,'LED_DATA','GND','100k','RC0805FR-07100KL')
resistor('R6',70,42,'LED_5V_BUF','LED_DIN','330R','RC0805FR-07330RL')
header('J7','RING 5V',77,40,['5V_SYS','GND','LED_DIN'])
header('J8','PTT',9,77,['PTT','GND'])
header('J9','PAGE',20,77,['NEXT','GND'])
header('J10','REC LED',31,77,['REC_ANODE','GND'])
resistor('R7',48,62,'REC_LED','REC_ANODE','1k','RC0805FR-071KL')
resistor('R8',46,53,'PTT','3V3','10k','RC0805FR-0710KL')
resistor('R9',46,58,'NEXT','3V3','10k','RC0805FR-0710KL')
cap('C3',54,35,'3V3','GND')
# Accessible through-hole test points; no metal enclosure connections.
for i,(x,y,n) in enumerate([(69,61,'5V_SYS'),(76,61,'GND'),(46,36,'3V3'),(71,49,'LED_DIN')],1):
    part(f'TP{i}',n,'TestPoint_THT_D2',x,y,[Pad('1',0,0,n,2.0,1.0)],(-1,-1,2,2),'Keystone 5000 test loop')
HOLES=[(4,4),(96,4),(4,86),(96,86)]
RF_KEEPOUT=(7,0,44,13.5)

def export():
    data={'project':'Aether Orb','revision':'B','board_mm':[W,H],'pinmap':PINMAP,
          'parts':[asdict(p) for p in PARTS], 'holes':HOLES, 'rf_keepout':RF_KEEPOUT,
          'release':'ENGINEERING PROTOTYPE - NOT PRODUCTION RELEASED'}
    (ROOT/'hardware/design.json').write_text(json.dumps(data,indent=2))
    (ROOT/'firmware/main/pins.h').write_text('#pragma once\n// Generated by tools/design.py; do not hand-edit.\n'+
        ''.join(f'#define PIN_{k} {v}\n' for k,v in PINMAP.items()))
    return data
if __name__=='__main__': export()
