"""Compact palmar CMC bearing stack below the carrier hub.

All dimensions are radii. The fixed sleeve occupies Z8.6..10, its flange
Z8.42..8.6. The D journal starts8.38, ring center11.83, tip11.995.
"""
from cadgen import build123d as bd
from lib.bushing import make_bushing
from lib.axle import make_driven_axle
from lib.retaining_ring import make_retaining_ring
from lib.finish import finish

BEARING_CENTER=9.3
BEARING_THICKNESS=1.4
SUPPORT_OUTER_RADIUS=1.85
SUPPORT_BORE_RADIUS=1.58

def make_compact_axle():
 # Original headed D shaft contributes its fully blended head and socket.
 # Its original free-end groove is outside the final tip and removed.
 stock=make_driven_axle(length=5.,radius=1.,flat=.75,head_radius=1.6)
 stock=stock-(bd.Pos(0,0,3.615)*bd.Box(10,10,6,align=(bd.Align.CENTER,bd.Align.CENTER,bd.Align.MIN)))
 # A short, turned retaining recess leaves a 0.04 mm terminal shoulder.
 cutter=bd.Pos(0,0,3.45)*(bd.Cylinder(1.2,.25)-bd.Cylinder(.82,.5))
 stock=stock-cutter
 edges=[e for e in stock.edges() if e.geom_type==bd.GeomType.CIRCLE and e.bounding_box().min.Z>3.30]
 if edges:stock=bd.fillet(edges,.008)
 assert len(stock.solids())==1 and stock.is_valid
 return finish(stock,'steel','thumb_cmc_abduction_palmar_stub_keyed_shaft')

def compact_cmc_hardware():
 from lib.assembly import joint_location
 from lib.layout import JOINT_BY_NAME
 j=JOINT_BY_NAME['thumb_cmc_abduction'];base=joint_location(j)
 out=[]
 def add(shape,p,name,frame,kind):
  s=p*shape;s.label=name;out.append((s,frame,'thumb',kind))
 add(make_bushing(outer_radius=1.55,bore_radius=1.03,length=1.4,flange_radius=1.76),base*bd.Pos(0,0,10)*bd.Rot(180,0,0),j.name+'_positive_bushing',j.parent,'bushing')
 add(make_compact_axle(),base*bd.Pos(0,0,8.38),j.name+'_palmar_stub_keyed_shaft',j.name,'shaft')
 add(make_retaining_ring(),base*bd.Pos(0,0,11.83),j.name+'_palmar_stub_retaining_ring',j.name,'retaining_ring')
 return out
