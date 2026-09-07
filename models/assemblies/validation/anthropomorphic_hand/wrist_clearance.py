import json,sys,itertools
from pathlib import Path
root=Path(__file__).resolve().parents[4]
sys.path.insert(0,str(root/'models/assemblies/src/anthropomorphic_hand'))
from cadgen import build123d as bd
from lib.wrist import make_wrist_fixed_fork,make_wrist_yaw_carrier,make_wrist_palm_cradle,make_wrist_bushings,_bore
from lib.pulley import make_pulley
from lib.palm_frame import make_palm_frame
from lib.layout import rotation_matrix
from lib.assembly import matrix_location
from OCP.BRepAlgoAPI import BRepAlgoAPI_Common
from OCP.BRepGProp import BRepGProp
from OCP.GProp import GProp_GProps
fixed=make_wrist_fixed_fork(); yaw=make_wrist_yaw_carrier(); cradle=make_wrist_palm_cradle()
print('Built wrist frames',flush=True)
palm=None if '--wrist-only' in sys.argv else make_palm_frame();print('Palm omitted explicitly for internal gate' if palm is None else 'Built palm',flush=True)
yaw_d=[bd.Pos(0,-9,s*5.5)*make_pulley(11,bore_radius=3.03,label=f'yaw_driven_{s}') for s in (-1,1)]
flex_d=[bd.Pos(s*14,0,0)*bd.Rot(0,90,0)*bd.Rot(0,0,90)*make_pulley(11,bore_radius=3.03,label=f'flex_driven_{s}') for s in (-1,1)]
# D journals reproduce the envelope of the actual continuous drive shafts.
yaw_shaft=_bore((0,-9,0),3.,24.,'z',True);yaw_shaft.label='yaw_shaft_envelope'
flex_shaft=_bore((0,0,0),3.,45.,'x',True);flex_shaft.label='flex_shaft_envelope'
bushings=make_wrist_bushings()
rows=[];cache={}
def volume(a,b):
    boxa=a.bounding_box();boxb=b.bounding_box()
    if any(getattr(boxa.max,k)<getattr(boxb.min,k) or getattr(boxb.max,k)<getattr(boxa.min,k) for k in 'XYZ'):return 0.
    common=BRepAlgoAPI_Common(a.wrapped,b.wrapped);common.Build()
    if not common.IsDone():raise ValueError('Boolean failed')
    props=GProp_GProps();BRepGProp.VolumeProperties_s(common.Shape(),props)
    return props.Mass()
poses=[(a,0.) for a in (-20.,-10.,0.,10.,20.)]+[(0.,a) for a in (-45.,-40.,-30.,-20.,-10.,0.,10.,20.,30.,40.,50.,60.)]+[(a,b) for a in (-20.,20.) for b in (-45.,60.)]
for ya,fl in poses:
    yl=matrix_location(rotation_matrix((0,0,1),ya,(0,-9,0)))
    floc=matrix_location(rotation_matrix((0,0,1),ya,(0,-9,0))@rotation_matrix((1,0,0),fl,(0,0,0)))
    parts=[fixed,yl*yaw,floc*cradle,*([] if palm is None else [floc*palm]),*[yl*d for d in yaw_d],*[floc*d for d in flex_d],yl*yaw_shaft,floc*flex_shaft]
    groups=[0,1,2,*([] if palm is None else [2]),1,1,2,2,1,2]
    parts += [b if frame=="fixed" else yl*b for frame,b in bushings]
    groups += [0 if frame=="fixed" else 1 for frame,b in bushings]
    clashes=[];maxvol=0
    for (i,a),(j,b) in itertools.combinations(enumerate(parts),2):
        ga,gb=sorted((groups[i],groups[j]))
        relative=() if ga==gb else (fl,) if ga==1 else (ya,) if gb==1 else (ya,fl)
        key=(i,j,relative)
        if key not in cache:cache[key]=volume(a,b)
        v=cache[key];maxvol=max(maxvol,v)
        if v>1e-6:clashes.append([a.label,b.label,v])
    row={'yaw_degrees':ya,'flex_degrees':fl,'pairs':len(parts)*(len(parts)-1)//2,'max_intersection_volume':maxvol,'clashes':clashes,'clear':not clashes}
    rows.append(row);print(json.dumps(row),flush=True)
out={'scope':('Actual wrist frames, four driven pulleys, full D-shaft envelopes; palm excluded and remains pending' if palm is None else 'Actual wrist frames, actual palm, four driven pulleys, full D-shaft envelopes')+'; every independent 10-degree wrist range plus simultaneous extrema; invariant rigid-relative pairs cached exactly','all_clear':all(r['clear'] for r in rows),'poses':rows}
Path(__file__).with_name('wrist_internal_clearance.json' if palm is None else 'wrist_clearance.json').write_text(json.dumps(out,indent=2))
raise SystemExit(0 if out['all_clear'] else 2)
