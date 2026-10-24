"""Finish the .063 gripper and close the fixed case gap to 0.5 mm.

All dimensions are in millimetres. Servo/camera mounting seats and horn
interfaces are preserved; only the bridge between the cases is shortened.
"""
import math
from dataclasses import asdict
import build123d as b
from lib.mates import revolute, fastened
from lib.booleans import as_single_shape as one
from lib.short_gripper_trial import datums,box
from lib.gripper_063 import THICKNESS as T,RADIUS as RI
from lib.corner_rules import INTERIOR_CORNER_R_MM
R=INTERIOR_CORNER_R_MM
LAND=4.8
CASE_INSET=1.0
WINDOW_HEIGHT=20.622
# The rounded nose removes ~0.70 mm of local die support. 6.2 mm leaves
# >=6.73 mm flat flange at the bend end (SCS ALU-063 minimum: 6.477 mm).
FORMING_NOSE_LAND=6.2
ACCESSORY_RADIUS=1.6
APERTURE_HORIZONTAL_GAP=2.8


def finish(q,p):
 q=one(q).clean();q.label=p.label;q.color=p.color
 assert q.is_valid and len(q.solids())==1,(p.label,len(q.solids()))
 return q


def tidy_finger(p,moving=False,*,extension=0.0,fold_y=None,contact_length=None):
 """Rebuild the web windows and carry both folds to the diagonal nose."""
 _,_,_,d,_=datums(p,moving)
 angle=math.degrees(math.atan2(d.Y,d.X));axis=b.Axis.Z
 q=p.rotate(axis,-angle)
 face,tip,root,_,_=datums(q,moving)
 normal=face.normal_at().Y
 zlo=min(v.center().Z for v in face.outer_wire().vertices())
 zhi=max(v.center().Z for v in face.outer_wire().vertices())
 # Rebuild the whole formed finger up to its mounting header. The previous
 # front-only splice left sliver faces in the bends and a .508 mm edge step.
 fold=tip.Y-normal*(RI+T)
 sample=one(q.intersect(box((root.X-2,-500,zhi+RI+.01),(root.X-1,500,zhi+RI+T-.01))))
 outer=sample.bounding_box().max.Y if moving else sample.bounding_box().min.Y
 # Current-arm jaw alignment is constructed into the complete formed channel.
 # The mounting header stays fixed. Both quarter bends, caps and web share
 # the same transverse shift, so the former step cannot survive at a fold.
 if fold_y is not None:
  assert not moving,'A moving jaw uses its own local bend datum'
  dy=fold_y-fold
  tip=b.Vector(tip.X,tip.Y+dy,tip.Z)
  root=b.Vector(root.X,root.Y+dy,root.Z)
  outer+=dy;fold=fold_y
 tip=b.Vector(tip.X-extension,tip.Y,tip.Z)
 if contact_length is not None:
  # Extend the fixed web at its mounting end; the fingertip and mounting
  # header stay in place. Carry both bends and rails through the same datum.
  assert not moving
  root=b.Vector(tip.X+contact_length,root.Y,root.Z)
 back=one(q.intersect(box((root.X,-500,-500),(500,500,500))))
 pieces=[back]
 if moving:
  # The legacy horn header starts 0.508 mm off the bend tangent. Carry
  # that tangent to the actual horn-mouth corner, rounded with the house
  # R2, rather than retaining a step at the finger/header splice.
  arcs=[e for e in back.edges() if e.geom_type==b.GeomType.CIRCLE
        and abs(e.center().Z-(zhi+RI+T))<1e-4
        and abs(e.bounding_box().min.Y-(fold+.508))<1e-4
        and e.arc_center.X<root.X+20]
  assert len(arcs)==1,('moving header corner',len(arcs))
  corner=arcs[0];end=corner.arc_center.X+corner.radius
  for sign,cz in [(-1,zlo),(1,zhi)]:
   z=cz+sign*RI
   stock=b.Face(b.Wire.make_polygon([(root.X,fold,z),(end,fold,z),
      (end,corner.arc_center.Y+2,z),(root.X,corner.arc_center.Y+2,z)],close=True))
   stock=stock.fillet_2d(R,[v for v in stock.vertices()
      if abs(v.X-end)<1e-5 and abs(v.Y-fold)<1e-5])
   stock=b.Solid.extrude(stock,(0,0,sign*T))
   holes=[]
   for e in back.edges():
    if e.geom_type==b.GeomType.CIRCLE and abs(e.radius-1.6)<1e-5 and e.length>10:
     c=e.arc_center
     holes.append(b.Solid.make_cylinder(1.6,T+.02,b.Plane(origin=(c.X,c.Y,min(z,z+sign*T)-.01))))
   if holes:stock=one(stock.cut(*holes))
   pieces.append(stock)
 for sign,cz in [(-1,zlo),(1,zhi)]:
  nose=tip.X+abs(cz-tip.Z)-2
  z=cz+sign*RI
  cap=fold-normal*FORMING_NOSE_LAND
  knee=nose+abs(outer-cap)
  poly=[(nose,fold),(root.X,fold),(root.X,outer),(knee,outer),(nose,cap)]
  capface=b.Face(b.Wire.make_polygon([(x,y,z) for x,y in poly],close=True))
  capface=capface.fillet_2d(R,[v for v in capface.vertices()
      if v.center().X<root.X-.01 and abs(v.center().Y-fold)>.01])
  pieces.append(b.Solid.extrude(capface,(0,0,sign*T)))
  def pt(r,a):return(nose,fold+normal*r*math.cos(a),cz+sign*r*math.sin(a))
  ri,ro=RI,RI+T
  wire=b.Wire([b.Edge.make_three_point_arc(*[pt(ro,a) for a in (0,math.pi/4,math.pi/2)]),
      b.Edge.make_line(pt(ro,math.pi/2),pt(ri,math.pi/2)),
      b.Edge.make_three_point_arc(*[pt(ri,a) for a in (math.pi/2,math.pi/4,0)]),
      b.Edge.make_line(pt(ri,0),pt(ro,0))])
  pieces.append(b.Solid.extrude(b.Face(wire),(root.X-nose,0,0)))
 lowx=tip.X+(tip.Z-zlo-2);highx=tip.X+(zhi-tip.Z-2)
 poly=[(tip.X,tip.Z-2),(lowx,zlo),(root.X,zlo),(root.X,zhi),(highx,zhi),(tip.X,tip.Z+2)]
 pf=b.Face(b.Wire.make_polygon([(x,tip.Y,z) for x,z in poly],close=True))
 pf=pf.fillet_2d(R,[v for v in pf.vertices() if abs(v.center().X-tip.X)<1e-5])
 pieces.append(b.Solid.extrude(pf,(0,-normal*T,0)))
 q=one(pieces[0].fuse(*pieces[1:])).clean()
 # Both fingers use one pattern measured from the coincident gripping tips.
 bottom,top=tip.Z-WINDOW_HEIGHT/2,tip.Z+WINDOW_HEIGHT/2
 window_mid=(bottom+top)/2
 triangle_radius=R
 # The nose diagonals are 45 degrees. At each base corner the radius
 # shortens the vertical extent by sqrt(2)*r; compensate before rounding.
 h=(top-bottom)/2+math.sqrt(2)*triangle_radius
 # Equal horizontal edge gaps at the hole-row centre lines, including the
 # rounded aperture corners. Both jaws use this same five-hole pattern.
 hr=ACCESSORY_RADIUS;gap=APERTURE_HORIZONTAL_GAP
 apex=tip.X+5+hr+gap-(math.sqrt(2)-1)*triangle_radius
 triangle_base=apex+h
 corner_inset=R-math.sqrt(R*R-(R-hr)**2)
 middle=triangle_base-corner_inset+gap+hr
 rear=root.X-LAND
 x0=middle+hr+gap-corner_inset
 x1=rear-hr-gap+corner_inset
 assert x1-x0>2*R
 def cut_profile(points,r=R):
  f=b.Face(b.Wire.make_polygon([(x,tip.Y+normal*.01,z) for x,z in points],close=True))
  f=f.fillet_2d(r,f.vertices())
  return b.Solid.extrude(f,(0,-normal*(T+.02),0))
 cuts=[cut_profile([(x0,bottom),(x1,bottom),(x1,top),(x0,top)]),
       cut_profile([(apex,window_mid),(triangle_base,window_mid-h),(triangle_base,window_mid+h)],triangle_radius)]
 # The rear accessory outer edges share the window's top/bottom datums.
 for x,z in [(tip.X+5,tip.Z),*[(x,z) for x in (middle,rear) for z in (bottom+hr,top-hr)]]:
  cuts.append(b.Solid.make_cylinder(hr,T+.02,b.Plane(origin=(x,tip.Y+normal*.01,z),z_dir=(0,-normal,0))))
 q=one(q.cut(*cuts)).clean()
 return finish(q.rotate(axis,angle),p)


def camera_corners(p):
 # The two width-step corners at the base of the inclined camera panel.
 panel=min((f for f in p.faces() if f.geom_type==b.GeomType.PLANE
            and f.center().Z>150 and f.area>900
            and f.normal_at().X*f.normal_at().Z>0),key=lambda f:f.center().Z)
 from end_effector.servo6_gripper_concept import CAMERA_PANEL_BOTTOM_LAND_MM, CAMERA_PANEL_PITCH_DEG
 panel_bottom=panel.bounding_box().min.Z+CAMERA_PANEL_BOTTOM_LAND_MM*math.cos(math.radians(CAMERA_PANEL_PITCH_DEG))
 candidates=[]
 for e in p.edges():
  if e.geom_type==b.GeomType.LINE and abs(e.length-T)<1e-4:
   c=e.center()
   if abs(abs(c.Y)-20)<1e-5 and abs(c.Z-panel_bottom)<3:candidates.append(c)
 assert len(candidates)==2,len(candidates)
 for c in candidates:
  edges=[e for e in p.edges() if (e.center()-c).length<1e-5 and abs(e.length-T)<1e-4]
  p=finish(p.fillet(R,edges),p)
 # The inherited camera-tip corners were R1. Apply the same R2 outline
 # on both sides without changing the panel, its bores, or its bends.
 for side in (-1,1):
  arcs=[e for e in p.edges() if e.geom_type==b.GeomType.CIRCLE
        and abs(e.radius-1)<1e-5 and abs(e.arc_center.Y-side*19)<1e-5
        and e.arc_center.Z>180 and abs(e.length-math.pi/2)<1e-5]
  assert len(arcs)==2,(side,len(arcs))
  e=max(arcs,key=lambda e:e.arc_center.Z)
  u=(e@0)-e.arc_center;v=(e@1)-e.arc_center
  sharp=e.arc_center+u+v
  center=sharp-(u+v)*R
  a=sharp-u*R;c=sharp-v*R
  mid=center+(u+v)*(R/math.sqrt(2))
  wire=b.Wire([b.Edge.make_line(sharp,a),b.Edge.make_three_point_arc(a,mid,c),b.Edge.make_line(c,sharp)])
  normal=u.cross(v).normalized()
  face=b.Face(wire).moved(b.Pos(*tuple(normal*-5)))
  p=finish(p.cut(b.Solid.extrude(face,normal*10)),p)
 return p


def compact_frame(p,*,outer_y=-24.0238,outer_corner_radius=R):
 # Full mounting patterns lie outside this plain bridging strip.
 split=-112.0
 left=one(p.intersect(box((-500,-500,-500),(split,500,500)))).moved(b.Pos(CASE_INSET,0,0))
 right=one(p.intersect(box((split+CASE_INSET,-500,-500),(500,500,500))))
 q=one(left.fuse(right)).clean()
 # The shortening seam crossed the two old, unequal rear diagonals.
 # Replace both outer borders with the same 45-degree projected line.
 outer=outer_y
 intercept=86.9145766945
 start=outer-intercept
 rail_start=datums(q,False)[2].X if outer_y!=-24.0238 else -120
 for z,end_y in [(102.6373766945,-14.6828),(136.2375766945,-16.0)]:
  end_x=end_y-intercept
  q=one(q.cut(box((rail_start,-50,z-.00001),(end_x,end_y,z+T+.00001))))
  border=b.Face(b.Wire.make_polygon([(rail_start,outer,z),(start,outer,z),
      (end_x,end_y,z),(rail_start,end_y,z)],close=True))
  q=one(q.fuse(b.Solid.extrude(border,(0,0,T)))).clean()
  # Only the two exposed diagonal knees; their sheet/bend joins stay exact.
  for x,y in [(start,outer),(end_x,end_y)]:
   edges=[e for e in q.edges() if e.geom_type==b.GeomType.LINE
          and abs(e.length-T)<1e-5 and abs(e.center().X-x)<1e-5
          and abs(e.center().Y-y)<1e-5 and abs(e.center().Z-(z+T/2))<1e-5]
   assert len(edges)==1,('gripper diagonal knee',x,y,z,len(edges))
   radius=outer_corner_radius if abs(y-outer)<1e-6 else R
   q=one(q.fillet(radius,edges)).clean()
 return finish(q,p)


def gripper_refs(data):
 refs={'gripper_jaw_servo','gripper_right_claw'}
 while True:
  more=refs|{m.child.lstrip('#') for m in data['mates'] if m.parent.lstrip('#') in refs}
  if more==refs:break
  refs=more
 refs.update(['inline_jaw_drive_horn','inline_jaw_idler_horn'])
 refs.update(f'gripper_frame__hex_socket_m2x6__{i:02}' for i in (1,2,6,7))
 refs.add('gripper_left_claw__hex_socket_m2x6__01')
 return refs


def revised_kinematics(data):
 mates=[]
 for m in data['mates']:
  d=asdict(m)
  if m.name=='gripperJaw':
   xyz=list(d['axis']['origin']);xyz[0]+=CASE_INSET
   m=revolute(m.name,parent=m.parent,child=m.child,origin=xyz,direction=d['axis']['dir'],limits=d['limits']['value'])
  mates.append(m)
 mates.append(fastened('gripper_lower_case_screw',parent='#servo6_fixed_gripper_frame',child='#gripper_lower_case_m2x6'))
 return data|{'mates':mates}
