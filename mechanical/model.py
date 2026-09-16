"""Aether Orb Rev B parametric mechanical design (CadQuery 2.x).
Millimetres. +Y = operator, -Y = client, +Z = up. Bottom datum Z=0.
Purchased component solids are envelope proxies, NOT vendor-accurate models.
The globe and beamsplitter are optical procurement drawings, not FDM parts.
"""
from pathlib import Path
import json, math, sys
import cadquery as cq
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'mechanical'
P={
 'base_d':148.0, 'wall':3.0, 'base_top':68.0, 'deck_top':72.0,
 'globe_od':120.0, 'globe_wall':2.0, 'globe_center_z':112.0,
 'mirror_w':70.0, 'mirror_h':80.0, 'mirror_t':1.0, 'mirror_angle':55.0,
 'mirror_center_z':112.0, 'pcb_w':100.0, 'pcb_h':90.0, 'pcb_z':9.0,
 'lcd_board_x':81.28, 'lcd_board_y':62.484, 'lcd_hole_x':76.2, 'lcd_hole_y':57.15,
 'lcd_active_x':57.6, 'lcd_active_y':43.2, 'lcd_screen_z':68.5,
 'pd_proxy_x':20.0, 'pd_proxy_y':30.0, 'usb_slot_w':12.0, 'usb_slot_h':7.0,
 'fit_clearance':0.30,
}

def box(x,y,z,center):return cq.Workplane('XY').box(x,y,z).translate(center)
def cyl(r,h,z=0,x=0,y=0):return cq.Workplane('XY').circle(r).extrude(h).translate((x,y,z))
def hole_y(x,y,z,d,length=15):return cq.Workplane('XZ').center(x,z).circle(d/2).extrude(length,both=True).translate((0,y,0))
def hole_x(x,y,z,d,length=10):return cq.Workplane('YZ').center(y,z).circle(d/2).extrude(length,both=True).translate((x,0,0))
def holez(obj,x,y,d,z,h):return obj.cut(cyl(d/2,h,z,x,y))
def ring(ro,ri,h,z=0):return cq.Workplane('XY').circle(ro).circle(ri).extrude(h).translate((0,0,z))
BODY_SCREWS=[(67*math.cos(math.radians(a)),67*math.sin(math.radians(a))) for a in (30,150,210,330)]
PARTS={}; META={}; COLORS={}; ASS=[]
def add(name,obj,material,process,color,position=(0,0,0),explode=(0,0,0),note=''):
    if not obj.val().isValid():raise ValueError('Invalid BREP: '+name)
    PARTS[name]=obj;COLORS[name]=color
    META[name]={'material':material,'process':process,'note':note,'assembly_position_mm':position,'explode_mm':explode}
    ASS.append((name,obj.translate(position),color,explode))

# Body: round shell with integral, flat operator panel (+Y).
outer=cyl(74,65,3).intersect(box(170,170,80,(0,-22,38))) # max Y=63
inner=cyl(71,68,2).intersect(box(166,166,80,(0,-23,38))) # max Y=60
body=outer.cut(inner)
# Four bottom fastener bosses, with pilot holes for M3 heat-set inserts.
for x,y in BODY_SCREWS:
    # Body screws are deliberately independent of PCB support posts.
    # Bridge bosses to the cylindrical wall with a short radial rib.
    rr=math.hypot(x,y);ang=math.degrees(math.atan2(y,x))
    rib=box(74-rr,5,12,((74+rr)/2,0,9)).rotate((0,0,0),(0,0,1),ang)
    boss=cyl(5,12,3,x,y);body=body.union(rib).union(boss)
    body=holez(body,x,y,4.2,3,5.5)
# Deck rests on four wall-connected shelf lugs, screws installed from above.
for a in [45,135,225,315]:
    x=63*math.cos(math.radians(a));y=63*math.sin(math.radians(a))
    body=body.union(cyl(5,9,59,x,y))
    rr=63;rib=box(11,5,9,(68.5,0,63.5)).rotate((0,0,0),(0,0,1),a);body=body.union(rib)
    body=holez(body,x,y,4.2,62.5,5.6)
# PTT and PAGE 12 mm threaded buttons; REC LED 3 mm; master toggle M6.
for x in (-22,0):body=body.cut(hole_y(x,61.5,39,12.2))
body=body.cut(hole_y(18,61.5,39,3.2))
body=body.cut(hole_y(-22,61.5,22,6.4))
body=body.cut(box(P['usb_slot_w'],16,P['usb_slot_h'],(29,62,32.0)))
# Bottom-port microphone is mounted upright, against this operator-facing acoustic port.
body=body.cut(hole_y(-27,61.5,52,2.0))
# Sled mounting pads and carrier-independent bosses.
for x in (19,39):
    body=body.union(box(8,6,10,(x,58,24)))
    body=holez(body,x,57,2.5,26,4.2)
# Passive sound ventilation and convection; no liquid or dust ingress rating claimed.
for a in range(200,341,14):
    cut=box(2.4,10,15,(0,-72,25)).rotate((0,0,0),(0,0,1),a-270)
    body=body.cut(cut)
add('01_base_shell',body,'Black PETG or PA12','FDM/SLS, no optical surfaces',(0.09,.11,.15),explode=(0,0,0),note='3 mm wall; 4.2 mm heat-set pilot must be tuned using fit coupon. No metal-filled finish near antenna.')

bottom=cyl(73.7,3,0).intersect(box(170,170,6,(0,-22,1.5)))
# Locating rim, with clearance to body.
rim=ring(70.65,68.8,2.2,3).intersect(box(165,165,12,(0,-23,5)))
# Reliefs around shell fastener bosses preserve 0.35 mm radial clearance.
for x,y in BODY_SCREWS:
    rim=rim.cut(cyl(5.35,3,2.9,x,y))
bottom=bottom.union(rim)
for x,y in BODY_SCREWS:
    bottom=holez(bottom,x,y,3.4,-1,7)
    bottom=holez(bottom,x,y,6.5,-.1,1.6)
for x,y in [(-46,-41),(46,-41),(-46,41),(46,41)]:
    bottom=bottom.union(cyl(3.6,6,3,x,y))
    bottom=holez(bottom,x,y,2.5,3,6.1)
# Cross hatching below device for convection / acoustic leakage.
for x in range(-18,19,6):bottom=bottom.cut(box(2,20,5,(x,-51,1.5)))
add('02_bottom_cover',bottom,'Black PETG / PA12','FDM/SLS',(.14,.16,.2),explode=(0,0,-30),note='M3 body screws through counterbores; independent PCB M3x6 self-tap screws enter separate posts from above.')

# Deck covers internal electronics, carries optical parts and display standoffs.
deck=cyl(73.7,4,68).intersect(box(170,170,10,(0,-22,70)))
# Optical window; display glass remains below the edge of this aperture.
deck=deck.cut(box(60,46,10,(0,0,70)))
# Globe flange seat: 100.6 mm OD, 84 mm ID; 0.8 mm gasket + 2 mm PMMA flange.
seat=ring(50.3,42,3.0,69.0);deck=deck.cut(seat)
# Retainer fasteners at radius 54, away from LCD corner hardware.
for a in [45,135,225,315]:
    x=54*math.cos(math.radians(a));y=54*math.sin(math.radians(a))
    deck=holez(deck,x,y,2.5,68,4.1)
# Deck screws on shelf lugs at R63.
for a in [45,135,225,315]:
    x=63*math.cos(math.radians(a));y=63*math.sin(math.radians(a))
    deck=holez(deck,x,y,3.4,67,6)
# Adafruit 1770 nominal mounting grid; slots permit ±0.5 mm after measuring the delivered revision.
for x in (-38.1,38.1):
    for y in (-28.575,28.575):
        st=cyl(3.3,4.8,63.2,x,y);deck=deck.union(st)
        deck=holez(deck,x,y,2.5,63,9.2)
# Blind pilot holes for upright feet. Never allow screw tips to touch display PCB below.
for x in (-40,40):
    for y in (-5,5):deck=holez(deck,x,y,1.7,69,3.2)
# Speaker cradle: two M3 self-tapping fasteners from below into blind deck holes.
for x,y in ((-8,-40),(37,-38)):
    deck=holez(deck,x,y,2.5,67.8,3.5)
# Halo power cable route outside globe flange.
deck=deck.cut(box(5,4,8,(53,0,70)))
add('03_optical_deck',deck,'Black PETG / PA12','FDM/SLS',(.13,.15,.19),explode=(0,0,45),note='Screen plane nominal Z68.5. Display stand-off length is adjustable using washers; measure actual LCD revision.')

# Optical shell: custom hollow PMMA, open lower spherical cap removed.
outer=cq.Workplane('XY').sphere(60).translate((0,0,112))
inner=cq.Workplane('XY').sphere(58).translate((0,0,112))
shell=outer.cut(inner).intersect(box(150,150,110,(0,0,127))) # bottom cut Z=72
# Bonded flange is modeled separately; adhesive process must be qualified by optical vendor.
add('04_optical_globe',shell,'Optical PMMA, clear, UV-stabilized','Optical forming/polishing - NOT FDM',(.62,.85,.97),explode=(0,0,110),note='120 OD, 2 nominal wall, cut at 40 mm below centre. Opening OD89.443 / ID84.000. Supplier optical qualification required.')
flange=ring(50,42,2,70)
add('05_globe_bond_flange',flange,'Clear cast PMMA','CNC/laser cut; supplier-bond to globe',(.58,.82,.94),explode=(0,0,80),note='100 OD / 84 ID / 2 thick. Bond is structural: test pull-off. No cyanoacrylate vapour near clear surfaces.')
gasket=ring(50,42,.8,69.2)
add('06_globe_gasket',gasket,'Black silicone, 40-50 Shore A','Die-cut 0.8 mm sheet',(.18,.20,.23),explode=(0,0,62))
# Split retainer can be fitted AFTER the 120 mm globe is seated.
ret=ring(56,48,2,72)
for a in [45,135,225,315]:
    x=54*math.cos(math.radians(a));y=54*math.sin(math.radians(a));ret=holez(ret,x,y,3.3,71,4)
for name,sign in [('07_retainer_left',-1),('08_retainer_right',1)]:
    half=ret.intersect(box(100,150,8,(sign*50.15,0,73)))
    add(name,half,'Gold-painted PETG / PA12','FDM/SLS then nonconductive finish',(.58,.39,.15),explode=(sign*20,0,65))

# Mirror frame lies in local XY and rotates about X. Coating faces down/toward incident LCD.
frame=box(74,84,2,(0,0,0)).cut(box(66,76,5,(0,0,0)))
# 1.2 mm recessed pocket for 70x80x1 glass; lip gives 2 mm edge support.
frame=frame.cut(box(70.3,80.3,1.3,(0,0,.45)))
# Edge hinge eyes; bores lie on the X axis through the frame centre.
for x in (-36.4,36.4):
    eye=hole_x(x,0,0,5,.6).cut(hole_x(x,0,0,3.3,4))
    frame=frame.union(eye)
# Hard stops create a 1.9 mm compliant upper-pad gap above the glass.
for x in (-36.15,36.15):
    for y in (-36,36):
        frame=frame.union(box(1.7,5,1.9,(x,y,1.95)))
# Clamp tabs for glass retainer (M2); avoid optical clear aperture.
for x in (-35.8,35.8):
    for y in (-36,36):frame=holez(frame,x,y,1.7,-1.2,3)
frame=frame.rotate((0,0,0),(1,0,0),P['mirror_angle']).translate((0,0,112))
add('09_mirror_frame',frame,'Matte black PA12 / PETG','FDM/SLS; smooth glass-contact pads',(.055,.065,.08),explode=(0,0,75),note='Glass rests on edge lip with 0.2 mm silicone pads. Rotation 45-55 deg normal use; clamp with M3 pivot screws.')
back=box(74,84,1.2,(0,0,0)).cut(box(68,78,4,(0,0,0)))
for x in (-35.8,35.8):
    for y in (-36,36):back=holez(back,x,y,2.2,-2,4)
back=back.translate((0,0,3.5)).rotate((0,0,0),(1,0,0),P['mirror_angle']).translate((0,0,112))
add('10_mirror_retainer',back,'Matte black PA12 / PETG','FDM/SLS',(.07,.08,.1),explode=(0,10,87))
mirror=box(70,80,1,(0,0,.5)).rotate((0,0,0),(1,0,0),P['mirror_angle']).translate((0,0,112))
add('11_beamsplitter_OPTICAL',mirror,'70R/30T coated optical glass, rear AR','Optical fabrication - NOT FDM',(.45,.76,.88),explode=(0,5,81),note='70x80x1 mm, visible band, specify usable incidence 45-55 degrees. Coating uniformity, wedge/ghosting and polarization to vendor review.')
for sign in (-1,1):
    x=40*sign
    foot=box(5,14,3,(x,0,73.5)).intersect(cyl(41.5,6,71))
    post=box(3,7,39,(x,0,93.5)).union(cyl(1,1,0)) if False else box(3,7,39,(x,0,93.5))
    # Rounded upper bearing with 8 mm diameter, 3 mm thick along X.
    post=post.union(hole_x(x,0,112,8,1.5));post=post.union(foot)
    post=post.cut(hole_x(x,0,112,3.3,5))
    for y in (-5,5):post=holez(post,x,y,2.2,71,5)
    add('12_upright_'+('left' if sign<0 else 'right'),post,'Matte black PA12 / PETG','FDM/SLS',(.08,.10,.13),explode=(sign*8,0,50),note='M2x6 foot screws, M3 pivot clamp. No overlong screws into LCD envelope.')

# Halo: 16 pixels of 60 LED/m strip, 266.7 mm arc around R57.0; 90-degree operator gap.
rail=ring(59.0,56.8,10,72).cut(box(90,100,14,(0,75,77)))
# Low annular floor gives mounting spots; cut away optical throat.
rail=rail.union(ring(59,56,1.5,72))
add('13_halo_rail',rail,'Black PETG / PA12','FDM/SLS',(.08,.1,.14),explode=(0,0,48),note='Use flexible strip, not a 60 mm rigid ring: that would obstruct the display. Locate the no-LED gap on +Y.')
diff=ring(56.2,54.8,8,74)
add('14_halo_diffuser',diff,'Opal silicone or translucent TPU','Cast/mould or FDM optical trial',(.71,.57,.95),explode=(0,0,58),note='Only peripheral glow; no mist, lasers or true volumetric image. Black out operator-facing quadrant after optical calibration.')

# Speaker cradle above carrier tall components, not on the PCB itself.
sp=ring(22,17,3,35).translate((16,-40,0))
# Two long tabs to deck underside, with elongated fastener access holes.
for x in (-8,40):
    leg=box(5,8,30,(x,-40,51));sp=sp.union(leg)
    tx,ty=(-8,-40) if x<0 else (37,-38)
    sp=sp.union(box(8,6,3,(tx,ty,66.5)))
    sp=holez(sp,tx,ty,3.2,64,5)
# Relief around the southeast optical-deck support lug (0.5 mm nominal).
sp=sp.cut(cyl(5.5,12,58.5,63/math.sqrt(2),-63/math.sqrt(2)))
# Add slim bridges from ring to supporting legs.
for x in (-6,38):sp=sp.union(box(8,6,3,(x,-40,36.5)))
add('15_speaker_cradle',sp,'Black PETG / PA12','FDM/SLS',(.1,.13,.17),explode=(18,-15,20),note='40 mm speaker envelope; strap retention. Mount to matching blind deck holes at (-8,-40) and (37,-38) with M3x6 self-tapping screws. Strap through cradle secures speaker; qualify purchased speaker envelope.')
# PD board mounting sled, screw to case only after verifying module USB mouth alignment.
pd=box(26,31,2,(29,43.5,30))
for x in (17,41):pd=pd.union(box(2,31,6,(x,43.5,32)))
for y in (34,57):
    for x in (19,39):pd=holez(pd,x,y,2.5,28,6)
# Trim rear tray corners to the enclosure's inner radius with 0.4 mm clearance.
pd=pd.intersect(cyl(70.6,12,27))
# Two ears form a support that may be screwed to deck-side mounting brackets.
add('16_pd_module_sled',pd,'Black PETG / PA12','FDM/SLS',(.1,.13,.17),explode=(20,15,15),note='Tray screws at (19/39,57) to case bosses. Foam tape plus cable tie retains PD board; adjust strip thickness to align USB centre Z32.0 with 12x7 case slot. Vendor PCB hole pattern is NOT claimed exact.')
# Printable fit coupon contains connector slot, screw pilot sizes, and sheet slots.
coupon=box(68,28,6,(0,0,3))
for i,d in enumerate([1.7,2.2,2.5,3.2,4.0,4.2,4.4]):coupon=holez(coupon,-27+i*9,0,d,-1,8)
for i,t in enumerate([.8,1.0,1.2,1.4]):coupon=coupon.cut(box(9,t,5,(-22+i*14,10,4)))
add('17_fit_coupon',coupon,'Same material and print profile as enclosure','FDM/SLS',(.55,.57,.61),position=(0,0,-100),note='Not an assembly part. Print first. Verify inserts, M2/M3 holes and beamsplitter thickness slots.')

# Component envelopes, included only in the assembled STEP and viewer.
board=box(100,90,1.6,(0,0,9.8))
for x,y in [(-46,-41),(46,-41),(-46,41),(46,41)]:board=holez(board,x,y,3.2,8,4)
add('REF_carrier_PCB',board,'FR-4 2 oz copper','Purchased PCB',(.04,.36,.25),explode=(0,0,10),note='Board outline/mounting holes only. Pads and copper in KiCad/Gerbers.')
controller=box(25.4,62.74,1.6,(-24.57,-1.10,20.0)).union(box(18,24,3,(-24.57,18.2,22.3)))
add('REF_esp32_devkit',controller,'Purchased module','Envelope proxy',(.13,.17,.2),explode=(0,0,25),note='Envelope orientation only; board antenna keepout is authoritative in PCB files.')
lcd=box(81.28,62.484,1.6,(0,0,62.4)).union(box(60,45,4.5,(0,0,65.45)))
add('REF_LCD_1770',lcd,'Adafruit 1770','Envelope proxy',(.1,.25,.33),explode=(0,0,36),note='LCD optical plane and connector clearance require measurement. Display is 320x240 landscape.')
screen=box(57.6,43.2,.2,(0,0,68.5))
add('REF_LCD_active',screen,'TFT active area','Envelope proxy',(.035,.065,.19),explode=(0,0,36))
speaker=cyl(20,15,38,16,-40).union(cyl(12,5,53,16,-40))
add('REF_speaker_40mm',speaker,'8 ohm 2W speaker','Envelope proxy',(.08,.08,.09),explode=(18,-15,25))
# Optional little electronics modules fitted using insulating standoffs / straps.
amp=box(20,18,2,(42,-10,42));add('REF_amp_module',amp,'Adafruit 3006','Envelope proxy',(.08,.31,.35),explode=(20,0,15))
mic=box(16.7,2,12.7,(-27,57.7,52));add('REF_mic_module',mic,'Adafruit 3421','Envelope proxy',(.08,.31,.35),explode=(-15,12,15),note='Mount bottom acoustic port facing +Y at (-27,60,52), using a 1.3 mm closed-cell foam gasket to panel. Do not cover port with adhesive. Secure board with nonconductive tie through carrier.')

# A vertical mic clip attaches to the flat panel without extending into the LCD.
micclip=box(21,1.5,17,(-27,55.5,52)).cut(box(12,5,9,(-27,55.5,52)))
for x in (-37,-17):micclip=micclip.union(box(2,4.5,17,(x,57,52)))
add('18_microphone_clip',micclip,'Black PETG / PA12','FDM/SLS',(.12,.15,.19),explode=(-12,12,18),note='Foam tape to panel; guide the microphone port to the 2 mm panel bore. Clip supports board edges, not MEMS package. Insulate back side; no conductive screws near microphone pins.')
# Module tray envelope: exact supplier port overhang is intentionally a fit qualification.
pdref=box(18,28,1.6,(29,44,32.0)).union(box(9,7,3.2,(29,58,33.0)))
add('REF_PD_HUSB238',pdref,'Adafruit 5807','Envelope proxy',(.08,.31,.35),explode=(20,15,20),note='USB mouth centre is adjusted to the case Z32 slot with thin foam shims after measuring delivered module. No assumed mounting-hole pattern.')


def export_all():
    OUT.mkdir(exist_ok=True);(OUT/'stl').mkdir(exist_ok=True);(OUT/'step').mkdir(exist_ok=True);(OUT/'dxf').mkdir(exist_ok=True)
    report=[];assembly=cq.Assembly(name='Aether_Orb_RevB')
    meshes=[]
    for name,obj,color,exp in ASS:
        if name=='17_fit_coupon':continue
        assembly.add(obj,name=name,color=cq.Color(*color, .16 if name=='04_optical_globe' else .4 if name=='11_beamsplitter_OPTICAL' else 1))
        vs,ts=obj.val().tessellate(.3,.15)
        verts=[[v.x,v.y,v.z] for v in vs]
        meshes.append({'name':name,'vertices':verts,'triangles':ts,'color':color,'opacity':.16 if name=='04_optical_globe' else .5 if name=='11_beamsplitter_OPTICAL' else 1,'explode':exp})
    for name,obj in PARTS.items():
        bb=obj.val().BoundingBox()
        row={'name':name,'valid_brep':obj.val().isValid(),'solid_count':len(obj.solids().vals()),'volume_mm3':round(obj.val().Volume(),3),'bbox_mm':[round(bb.xlen,3),round(bb.ylen,3),round(bb.zlen,3)],**META[name]}
        report.append(row)
        cq.exporters.export(obj,str(OUT/'step'/f'{name}.step'))
        print_obj=obj
        if name in ('09_mirror_frame','10_mirror_retainer'):
            print_obj=obj.translate((0,0,-112)).rotate((0,0,0),(1,0,0),-P['mirror_angle'])
        bbp=print_obj.val().BoundingBox()
        print_obj=print_obj.translate((-(bbp.xmin+bbp.xmax)/2,-(bbp.ymin+bbp.ymax)/2,-bbp.zmin))
        cq.exporters.export(print_obj,str(OUT/'stl'/f'{name}.stl'),tolerance=.06,angularTolerance=.10)
        # Sew coincident periodic-surface vertices only; do not fill missing faces.
        import trimesh
        mesh=trimesh.load(OUT/'stl'/f'{name}.stl',force='mesh')
        mesh.merge_vertices(digits_vertex=5)
        mesh.update_faces(mesh.nondegenerate_faces())
        mesh.remove_unreferenced_vertices()
        mesh.export(OUT/'stl'/f'{name}.stl')
        print(name,row['valid_brep'],row['solid_count'],row['bbox_mm'],flush=True)
    assembly.save(str(OUT/'Aether_Orb_RevB_Assembly.step'))
    (OUT/'parameters.json').write_text(json.dumps(P,indent=2))
    (OUT/'parts.json').write_text(json.dumps(report,indent=2))
    (ROOT/'preview/assembly-meshes.json').write_text(json.dumps(meshes,separators=(',',':')))
    # Layered 2D outlines for the optical supplier (mm, no kerf allowance).
    def dxf(name,sh):cq.exporters.export(sh,str(OUT/'dxf'/name))
    dxf('globe_flange_100-84-2mm.dxf',cq.Workplane('XY').circle(50).circle(42))
    dxf('globe_gasket_100-84-0.8mm.dxf',cq.Workplane('XY').circle(50).circle(42))
    dxf('beamsplitter_70x80x1mm.dxf',cq.Workplane('XY').rect(70,80))
    dxf('LCD_privacy_film_58x44mm.dxf',cq.Workplane('XY').rect(58,44))
if __name__=='__main__':export_all()
