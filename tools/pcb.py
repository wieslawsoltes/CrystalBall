"""Deterministic two-layer carrier generator, geometry DRC and fabrication exporter.
No claim is made that this replaces the independent KiCad DRC/ERC release gate.
"""
from __future__ import annotations
import sys, json, math, heapq, uuid, csv, itertools, html
from collections import defaultdict
from pathlib import Path
import numpy as np
from shapely.geometry import Point, LineString, box
from shapely.ops import unary_union
from shapely import intersects_xy
from design import *
STEP=.2; CLEAR=.20; MARGIN=.035
VIA_D=.70; VIA_HOLE=.35
NX=int(W/STEP)+1; NY=int(H/STEP)+1
XX,YY=np.meshgrid(np.arange(NX)*STEP,np.arange(NY)*STEP)
PADS=[p for c in PARTS for p in c.abs_pads()]
TRACKS=[]; VIAS=[]
NAMES=sorted({p['net'] for p in PADS})
NETS={name:i+1 for i,name in enumerate(NAMES)}

def uid(s):return str(uuid.uuid5(uuid.NAMESPACE_URL,'aether-orb/reva/'+s))
def shape(p):
    if p['kind']=='smd' or p['shape']=='rect':
        dx=(p['sx'] or p['diameter'])/2;dy=(p['sy'] or p['diameter'])/2
        return box(p['x']-dx,p['y']-dy,p['x']+dx,p['y']+dy)
    return Point(p['x'],p['y']).buffer(p['diameter']/2,quad_segs=12)
PAD_SHAPES=[shape(p) for p in PADS]

def width(net):
    if net in ('VIN5','FUSED5','5V_SYS','DEV_5V'):return .8
    if net=='GND':return .60
    if net=='3V3':return .5
    return .30

def block(net, rad):
    out=np.zeros((2,NY,NX),dtype=bool)
    obs=[[],[]]
    for p,g in zip(PADS,PAD_SHAPES):
        if p['net']==net:continue
        for z in ([0,1] if p['kind']=='thru_hole' else [0]):obs[z].append(g)
    for t in TRACKS:
        if t['net']!=net:obs[t['z']].append(LineString([t['a'],t['b']]).buffer(t['w']/2,quad_segs=4))
    for v in VIAS:
        if v['net']!=net:
            g=Point(*v['p']).buffer(VIA_D/2,quad_segs=8)
            obs[0].append(g);obs[1].append(g)
    # Copper-to-edge 0.5; NPTH screw copper clearance 0.5; antenna all-layer keepout.
    for z in (0,1):
        obs[z] += [Point(x,y).buffer(1.6+.5-rad-CLEAR) for x,y in HOLES]
        obs[z].append(box(*RF_KEEPOUT))
        for o in obs[z]:
            b=o.buffer(rad+CLEAR+MARGIN,quad_segs=4)
            x0,y0,x1,y1=b.bounds
            a=max(0,int(x0/STEP)-1);c=min(NX,int(x1/STEP)+2)
            d=max(0,int(y0/STEP)-1);e=min(NY,int(y1/STEP)+2)
            if c>a and e>d:out[z,d:e,a:c] |= intersects_xy(b,XX[d:e,a:c],YY[d:e,a:c])
        out[z] |= (XX<rad+.5)|(XX>W-rad-.5)|(YY<rad+.5)|(YY>H-rad-.5)
    return out

def cell(p,z):return (round(p[0]/STEP),round(p[1]/STEP),z)
def pos(n):return [round(n[0]*STEP,4),round(n[1]*STEP,4)]

def astar(starts,goals,blocked,via_block,prefer):
    goalset=set(goals); gx=[n[0] for n in goals];gy=[n[1] for n in goals]
    def heuristic(n):return min(abs(n[0]-g[0])+abs(n[1]-g[1]) for g in goals)
    pq=[];prev={};score={}
    for s in starts:
        if blocked[s[2],s[1],s[0]]:continue
        score[s]=0;heapq.heappush(pq,(heuristic(s),0,s))
    while pq:
        _,cost,n=heapq.heappop(pq)
        if score.get(n)!=cost:continue
        if n in goalset:
            path=[n]
            while n in prev:n=prev[n];path.append(n)
            return list(reversed(path))
        x,y,z=n
        for q in [(x+1,y,z),(x-1,y,z),(x,y+1,z),(x,y-1,z),(x,y,1-z)]:
            a,b,c=q
            if a<0 or b<0 or a>=NX or b>=NY or blocked[c,b,a]:continue
            if c!=z and (via_block[0,b,a] or via_block[1,b,a]):continue
            dc=(32 if c!=z else (1.0 if z==prefer else 1.03))
            nc=cost+dc
            if nc < score.get(q,1e100):
                score[q]=nc;prev[q]=n;heapq.heappush(pq,(nc+heuristic(q),nc,q))
    return None

def route_net(net):
    ps=[p for p in PADS if p['net']==net]
    if len(ps)<2:return
    # Connect near pairs via a deterministic minimum spanning tree.
    connected=[ps.pop(0)]
    while ps:
        _,i,j=min((abs(a['x']-b['x'])+abs(a['y']-b['y']),i,j) for i,a in enumerate(connected) for j,b in enumerate(ps))
        a=connected[i];b=ps.pop(j);w=width(net)
        starts=[cell((a['x'],a['y']),z) for z in ([0,1] if a['kind']=='thru_hole' else [0])]
        goals=[cell((b['x'],b['y']),z) for z in ([0,1] if b['kind']=='thru_hole' else [0])]
        blocked=block(net,w/2);vb=block(net,VIA_D/2)
        # Endpoint rounding clearance is validated against exact continuous geometry afterwards.
        for p in starts+goals:blocked[p[2],p[1],p[0]]=False
        path=astar(starts,goals,blocked,vb,1 if net=='GND' else 0)
        if path is None:raise RuntimeError(f'Unroutable {net}: {a["ref"]}.{a["number"]} -> {b["ref"]}.{b["number"]}')
        # Compress collinear runs, preserving layer transitions.
        current=[a['x'],a['y']];layer=path[0][2]
        if current!=pos(path[0]):TRACKS.append(dict(net=net,z=layer,a=current,b=pos(path[0]),w=w))
        start=path[0]
        for k in range(1,len(path)):
            p=path[k-1];q=path[k]
            if p[2]!=q[2]:
                if pos(start)!=pos(p):TRACKS.append(dict(net=net,z=p[2],a=pos(start),b=pos(p),w=w))
                v=dict(net=net,p=pos(p))
                if v not in VIAS:VIAS.append(v)
                start=q
            else:
                nxt=path[k+1] if k+1<len(path) else None
                if nxt is None or nxt[2]!=q[2] or (q[0]-p[0],q[1]-p[1])!=(nxt[0]-q[0],nxt[1]-q[1]):
                    if pos(start)!=pos(q):TRACKS.append(dict(net=net,z=q[2],a=pos(start),b=pos(q),w=w))
                    start=q
        if pos(path[-1])!=[b['x'],b['y']]:TRACKS.append(dict(net=net,z=path[-1][2],a=pos(path[-1]),b=[b['x'],b['y']],w=w))
        connected.append(b)

def validate():
    groups=[defaultdict(list),defaultdict(list)]
    for p,g in zip(PADS,PAD_SHAPES):
        for z in ([0,1] if p['kind']=='thru_hole' else [0]):groups[z][p['net']].append(g)
    for t in TRACKS:groups[t['z']][t['net']].append(LineString([t['a'],t['b']]).buffer(t['w']/2,quad_segs=16))
    for v in VIAS:
        for z in (0,1):groups[z][v['net']].append(Point(*v['p']).buffer(VIA_D/2,quad_segs=16))
    copper=[{n:unary_union(gs) for n,gs in d.items()} for d in groups]
    errors=[];min_clear=1000
    for z in (0,1):
        for (a,g),(b,h) in itertools.combinations(copper[z].items(),2):
            d=g.distance(h);min_clear=min(min_clear,d)
            if d<CLEAR-1e-5:errors.append(dict(type='clearance',layer=z,net_a=a,net_b=b,mm=round(d,6)))
        for n,g in copper[z].items():
            if not box(.499,.499,W-.499,H-.499).covers(g):errors.append(dict(type='copper-edge',net=n,layer=z))
            for x,y in HOLES:
                if g.distance(Point(x,y))<2.1-1e-5:errors.append(dict(type='screw-clearance',net=n,xy=[x,y]))
            if g.intersects(box(*RF_KEEPOUT)):errors.append(dict(type='antenna-keepout',net=n,layer=z))
    # Geometrical connectivity graph includes cross-layer links only at plated pads / vias.
    unconnected=[]
    for n in NAMES:
        if n.startswith('NC_'):continue
        regions=[]
        for z in (0,1):
            g=copper[z].get(n)
            if g is not None:
                for a in (list(g.geoms) if g.geom_type=='MultiPolygon' else [g]):regions.append((z,a))
        parent=list(range(len(regions)))
        def find(i):
            while parent[i]!=i:parent[i]=parent[parent[i]];i=parent[i]
            return i
        for p in [p for p in PADS if p['net']==n and p['kind']=='thru_hole']+[dict(x=v['p'][0],y=v['p'][1]) for v in VIAS if v['net']==n]:
            ids=[i for i,(_,g) in enumerate(regions) if g.buffer(1e-6).covers(Point(p['x'],p['y']))]
            for i in ids[1:]:parent[find(i)]=find(ids[0])
        if len({find(i) for i in range(len(regions))})>1:unconnected.append(n)
    return dict(generator='Aether geometry DRC (not KiCad)',clearance_rule_mm=CLEAR,
                min_measured_clearance_mm=round(min_clear,6),errors=errors,unconnected_nets=unconnected,
                pads=len(PADS),tracks=len(TRACKS),vias=len(VIAS),nets=len(NAMES),
                note='Independent KiCad parsing, ERC/DRC and fab CAM acceptance remain mandatory.')

def pcb():
    out=['(kicad_pcb (version 20221018) (generator aether_orb)',
         '  (general (thickness 1.6)) (paper "A4")',
         '  (layers (0 "F.Cu" signal) (31 "B.Cu" signal) (36 "B.SilkS" user "b.silkscreen") (37 "F.SilkS" user "f.silkscreen") (38 "B.Mask" user) (39 "F.Mask" user) (40 "Dwgs.User" user) (44 "Edge.Cuts" user) (46 "B.CrtYd" user) (47 "F.CrtYd" user) (48 "B.Fab" user) (49 "F.Fab" user))',
         '  (setup (pad_to_mask_clearance 0.05) (solder_mask_min_width 0.10))',
         '  (net 0 "")']
    for n,i in NETS.items():out.append(f'  (net {i} "{n}")')
    schroot=uid('schematic-root')
    controller_refs={'J1','J2','JP1','TP3'}
    power_refs={'J3','F1','Q1','R1','C1','U1','C2','R5','R6','J7','TP1','TP2','TP4'}
    for c in PARTS:
        sheet='controller' if c.ref in controller_refs else 'power-led' if c.ref in power_refs else 'interfaces'
        path=f'/{schroot}/{uid(sheet+"-instance")}/{uid(c.ref+"-sch")}'
        out.append(f'  (footprint "Aether:{c.footprint}" (layer "F.Cu") (tstamp {uid(c.ref+"-fp")}) (at {c.x} {c.y}) (path "{path}") (attr {"smd" if all(p.kind=="smd" for p in c.pads) else "through_hole"})')
        out.append(f'    (fp_text reference "{c.ref}" (at 0 -3.5) (layer "F.SilkS") (effects (font (size 1 1) (thickness .15))))')
        out.append(f'    (fp_text value "{c.value}" (at 0 0) (layer "F.Fab") (effects (font (size .8 .8) (thickness .12))))')
        x,y,w,h=c.body
        out.append(f'    (fp_rect (start {x} {y}) (end {x+w} {y+h}) (stroke (width .12) (type default)) (fill none) (layer "F.Fab"))')
        out.append(f'    (fp_rect (start {x-.25} {y-.25}) (end {x+w+.25} {y+h+.25}) (stroke (width .05) (type default)) (fill none) (layer "F.CrtYd"))')
        for p in c.pads:
            sz=f'{p.sx} {p.sy}' if p.kind=='smd' else f'{p.diameter} {p.diameter}'
            drill=f'(drill {p.drill})' if p.drill else ''
            layers='"F.Cu" "F.Mask"' if p.kind=='smd' else '"*.Cu" "*.Mask"'
            out.append(f'    (pad "{p.number}" {p.kind} {p.shape} (at {p.x} {p.y}) (size {sz}) {drill} (layers {layers}) (net {NETS[p.net]} "{p.net}"))')
        out.append('  )')
    for i,(x,y) in enumerate(HOLES,1):
        out.append(f'  (footprint "Aether:MountingHole_3.2" (layer "F.Cu") (at {x} {y}) (attr exclude_from_pos_files exclude_from_bom) (fp_text reference "H{i}" (at 0 0) (layer "F.Fab") hide (effects (font (size 1 1) (thickness .15)))) (pad "" np_thru_hole circle (at 0 0) (size 3.2 3.2) (drill 3.2) (layers "*.Cu" "*.Mask")))')
    corners=[(0,0),(W,0),(W,H),(0,H),(0,0)]
    for a,b in zip(corners,corners[1:]):out.append(f'  (gr_line (start {a[0]} {a[1]}) (end {b[0]} {b[1]}) (stroke (width .05) (type default)) (layer "Edge.Cuts") (tstamp {uid(str((a,b)))}))')
    for i,t in enumerate(TRACKS):
        a,b=t['a'],t['b'];out.append(f'  (segment (start {a[0]} {a[1]}) (end {b[0]} {b[1]}) (width {t["w"]}) (layer "{["F.Cu","B.Cu"][t["z"]]}") (net {NETS[t["net"]]}) (tstamp {uid("t"+str(i))}))')
    for i,v in enumerate(VIAS):out.append(f'  (via (at {v["p"][0]} {v["p"][1]}) (size {VIA_D}) (drill {VIA_HOLE}) (layers "F.Cu" "B.Cu") (net {NETS[v["net"]]}) (tstamp {uid("v"+str(i))}))')
    x0,y0,x1,y1=RF_KEEPOUT
    out.append(f''' (zone (net 0) (net_name "") (layers "F.Cu" "B.Cu") (tstamp {uid('rf-zone')}) (hatch edge .5)
      (connect_pads (clearance .2)) (min_thickness .25) (keepout (tracks not_allowed) (vias not_allowed) (pads not_allowed) (copperpour not_allowed) (footprints allowed))
      (fill (thermal_gap .3) (thermal_bridge_width .3))
      (polygon (pts (xy {x0} {y0}) (xy {x1} {y0}) (xy {x1} {y1}) (xy {x0} {y1}))))''')
    out.append(' (gr_text "AETHER ORB / REV A" (at 69 6) (layer "F.SilkS") (effects (font (size 1.4 1.4) (thickness .2))))')
    out.append(' (gr_text "5V ONLY - PROTOTYPE" (at 69 10) (layer "F.SilkS") (effects (font (size 1 1) (thickness .15))))')
    out.append(')')
    (ROOT/'hardware/aether-carrier.kicad_pcb').write_text('\n'.join(out))
    (ROOT/'hardware/aether-carrier.kicad_pro').write_text(json.dumps({
        'meta':{'filename':'aether-carrier.kicad_pro','version':1},
        'board':{'design_settings':{'rules':{'min_clearance':.2,'min_track_width':.25,'min_via_annular_width':.15,'min_via_diameter':.65,'min_through_hole_diameter':.3,'min_copper_edge_clearance':.5}}},
        'net_settings':{'classes':[{'name':'Default','clearance':.2,'track_width':.3,'via_diameter':.7,'via_drill':.35}],'meta':{'version':3}}
    },indent=2))
    (ROOT/'hardware/aether-carrier.kicad_dru').write_text('(version 1)\n(rule "All copper clearance" (constraint clearance (min 0.20mm)))\n(rule "Copper to edge" (constraint edge_clearance (min 0.50mm)))\n')

def gerber():
    dest=ROOT/'hardware/fabrication';dest.mkdir(exist_ok=True)
    def export(name,function,flashes,lines):
        # Coordinates converted from board y-down to CAM y-up. Same origin for ALL layers/drills.
        aps={}
        for shape_,sx,sy,*_ in flashes:aps.setdefault((shape_,sx,sy),len(aps)+10)
        for w,a,b in lines:aps.setdefault(('C',w,w),len(aps)+10)
        s=['G04 Aether Orb Rev A; independently CAM-review before ordering*',
           '%FSLAX46Y46*%','%MOMM*%',f'%TF.FileFunction,{function}*%','%TF.FilePolarity,Positive*%','%LPD*%']
        for (sh,sx,sy),a in aps.items():s.append(f'%ADD{a}{sh},{sx:.6f}'+(f'X{sy:.6f}' if sh=='R' else '')+'*%')
        def xy(x,y):return f'X{round(x*1e6)}Y{round((H-y)*1e6)}'
        for sh,sx,sy,x,y in flashes:s += [f'D{aps[sh,sx,sy]}*',xy(x,y)+'D03*']
        for w,a,b in lines:s += [f'D{aps["C",w,w]}*',xy(*a)+'D02*',xy(*b)+'D01*']
        s.append('M02*');(dest/name).write_text('\n'.join(s)+'\n')
    for z,name in [(0,'F_Cu'),(1,'B_Cu')]:
        flashes=[]
        for p in PADS:
            if z==1 and p['kind']=='smd':continue
            sx=p['sx'] or p['diameter'];sy=p['sy'] or p['diameter']
            flashes.append(('R' if p['shape']=='rect' else 'C',sx,sy,p['x'],p['y']))
        for v in VIAS:flashes.append(('C',VIA_D,VIA_D,*v['p']))
        export(f'aether-{name}.gbr',f'Copper,L{z+1},{"Top" if z==0 else "Bot"}',flashes,[(t['w'],t['a'],t['b']) for t in TRACKS if t['z']==z])
    for z,name in [(0,'F_Mask'),(1,'B_Mask')]:
        flashes=[]
        for p in PADS:
            if z==1 and p['kind']=='smd':continue
            flashes.append(('R' if p['shape']=='rect' else 'C',(p['sx'] or p['diameter'])+.1,(p['sy'] or p['diameter'])+.1,p['x'],p['y']))
        # Vias tented on both sides. NPTH holes get no surrounding mask opening.
        export(f'aether-{name}.gbr',f'Soldermask,{"Top" if z==0 else "Bot"}',flashes,[])
    corners=[(0,0),(W,0),(W,H),(0,H),(0,0)]
    export('aether-Edge_Cuts.gbr','Profile,NP',[],[(.05,a,b) for a,b in zip(corners,corners[1:])])
    # Simple silkscreen: component designators with our own stroke glyphs, square pin-1 marker.
    from stroke import text_lines
    lines=text_lines('AETHER ORB REV A',47,3,1.1)+text_lines('5V ONLY PROTOTYPE',47,7,.8)
    for c in PARTS:
        lines+=text_lines(c.ref,c.x-1.0,c.y-3.7,.7)
    # Clip silk to mask clearances (CAM positive geometry, then draw surviving line pieces).
    masks=unary_union([g.buffer(.15) for g in PAD_SHAPES])
    filtered=[]
    for w,a,b in lines:
        gs=LineString([a,b]).difference(masks.buffer(w/2))
        for g in (list(gs.geoms) if hasattr(gs,'geoms') else [gs]):
            if g.geom_type=='LineString' and not g.is_empty:
                coords=list(g.coords)
                for x,y in zip(coords,coords[1:]):filtered.append((w,x,y))
    export('aether-F_Silkscreen.gbr','Legend,Top',[],filtered)
    for name,drills in [('PTH',[(p['drill'],p['x'],p['y']) for p in PADS if p['drill']]+[(VIA_HOLE,*v['p']) for v in VIAS]),('NPTH',[(3.2,x,y) for x,y in HOLES])]:
        sizes=sorted({d for d,x,y in drills});s=['M48',f';TYPE={name}','METRIC,TZ']
        for i,d in enumerate(sizes,1):s.append(f'T{i:02d}C{d:.3f}')
        s+=['%','G90','G05']
        for i,d in enumerate(sizes,1):
            s.append(f'T{i:02d}')
            for dd,x,y in drills:
                if dd==d:s.append(f'X{x:.4f}Y{H-y:.4f}')
        s+=['M30'];(dest/f'aether-{name}.drl').write_text('\n'.join(s)+'\n')
    # No solder paste stencil: all eight-passives and two semiconductors are hand assembled for EVT.
    (dest/'README.txt').write_text('ENGINEERING FABRICATION CANDIDATE - NOT PRODUCTION RELEASED\n100 x 90 mm, 1.60 mm FR-4, 2 layers, 2 oz (70 um) finished outer copper.\nLead-free HASL or ENIG; green mask both sides; white top legend.\nProfile is nominal finished outline. Drill units mm, decimal format, common origin lower-left.\nPTH holes plated; four 3.20 mm NPTH mounting holes NOT plated. Vias tented.\nNo controlled impedance. Smallest route 0.30 mm, clearance 0.20 mm.\nNo stencil included: Rev A is hand-assembled. No panelization or tooling rails authorized.\nRun independent KiCad DRC/ERC, supplier footprint review and CAM review before releasing even a prototype order.\n')

def svg():
    s=[f'<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="1110" viewBox="-5 -10 110 102">',
       '<rect x="-5" y="-10" width="110" height="102" fill="#111922"/>',
       '<text x="0" y="-4" fill="#eef6ff" font-family="sans-serif" font-size="3">AETHER ORB · Rev A carrier / component-side view</text>',
       f'<rect x="0" y="0" width="{W}" height="{H}" rx="1" fill="#114f48" stroke="#eee" stroke-width=".3"/>']
    x0,y0,x1,y1=RF_KEEPOUT
    s.append(f'<rect x="{x0}" y="{y0}" width="{x1-x0}" height="{y1-y0}" fill="#122b29"/>')
    s.append('<text x="9" y="6" fill="#f7d794" font-size="2">ANTENNA / NO COPPER</text>')
    for z in (1,0):
        for t in TRACKS:
            if t['z']!=z:continue
            a,b=t['a'],t['b'];s.append(f'<path d="M{a[0]} {a[1]} L{b[0]} {b[1]}" stroke="{["#dfa953","#60a3d9"][z]}" stroke-width="{t["w"]}" stroke-linecap="round"/>')
    for c in PARTS:
        x,y,w,h=c.body;s.append(f'<rect x="{c.x+x}" y="{c.y+y}" width="{w}" height="{h}" fill="none" stroke="#f1eee1" stroke-width=".12"/>')
        s.append(f'<text x="{c.x-1}" y="{c.y-2.8}" fill="#fff" font-family="sans-serif" font-size="1.6">{c.ref}</text>')
    for p in PADS:
        if p['shape']=='rect':
            sx=p['sx'] or p['diameter'];sy=p['sy'] or p['diameter']
            s.append(f'<rect x="{p["x"]-sx/2}" y="{p["y"]-sy/2}" width="{sx}" height="{sy}" fill="#e4c87a"/>')
        else:s.append(f'<circle cx="{p["x"]}" cy="{p["y"]}" r="{p["diameter"]/2}" fill="#e4c87a"/>')
        if p['drill']:s.append(f'<circle cx="{p["x"]}" cy="{p["y"]}" r="{p["drill"]/2}" fill="#17222a"/>')
    for v in VIAS:
        s.append(f'<circle cx="{v["p"][0]}" cy="{v["p"][1]}" r="{VIA_D/2}" fill="#d1c394"/><circle cx="{v["p"][0]}" cy="{v["p"][1]}" r="{VIA_HOLE/2}" fill="#111"/>')
    for x,y in HOLES:s.append(f'<circle cx="{x}" cy="{y}" r="1.6" fill="#111922" stroke="#aaa" stroke-width=".2"/>')
    s.append('<text x="1" y="95" fill="#ccd7e0" font-family="sans-serif" font-size="2.1">100 × 90 mm · 2-layer / 2 oz · generated routing; independent EDA/CAM review pending</text></svg>')
    (ROOT/'preview/pcb.svg').write_text('\n'.join(s))

def main():
    export()
    cache=ROOT/'hardware/routes.json'
    if '--reroute' not in sys.argv and cache.exists():
        d=json.loads(cache.read_text());TRACKS.extend(d['tracks']);VIAS.extend(d['vias'])
    else:
        # Route fine-pitch LED buffer first, then high-current distribution, then remaining signals.
        powers=['VIN5','FUSED5','5V_SYS','DEV_5V','GND','3V3']
        ordered=['LED_DATA','LED_5V_BUF','LED_DIN','Q_GATE']
        ordered += [n for n in NAMES if n not in ordered+powers and not n.startswith('NC_')]
        ordered += powers
        failed=[]
        for attempt in range(16):
            TRACKS.clear(); VIAS.clear()
            print('ATTEMPT',attempt+1,ordered,flush=True)
            bad=None
            for n in ordered:
                print('Routing',n,flush=True)
                try:route_net(n)
                except RuntimeError as ex:
                    print(ex,flush=True);bad=n;break
            if bad is None:break
            failed.append(bad)
            ordered.remove(bad)
            ordered.insert(0,bad)
            if len(failed)>3 and failed[-1]==failed[-3]:
                import random
                random.Random(attempt).shuffle(ordered)
        else:
            (ROOT/'hardware/partial-routes.json').write_text(json.dumps({'tracks':TRACKS,'vias':VIAS}))
            svg();raise RuntimeError('Routing failed after 16 deterministic orderings')
        cache.write_text(json.dumps({'tracks':TRACKS,'vias':VIAS},indent=2))
    report=validate();(ROOT/'hardware/reports/geometry-drc.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(report,indent=2),flush=True)
    pcb();gerber();svg()
    if report['errors'] or report['unconnected_nets']:sys.exit(2)
if __name__=='__main__':main()
