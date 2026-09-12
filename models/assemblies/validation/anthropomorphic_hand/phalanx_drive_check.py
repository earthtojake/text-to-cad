"""Verify every actual phalanx's integral D drive faces and shaft clearance."""
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'src'/'anthropomorphic_hand'))
from cadgen import build123d as bd
from lib.layout import FINGERS
from lib.phalanx import make_phalanx, _drive_bore


def main():
    variants=[(f'{f.name}_{i}',length,width,i==2)
              for f in FINGERS for i,(length,width) in enumerate(zip(f.lengths,f.widths))]
    variants.extend((f'thumb_{i}',length,width,i==2)
                    for i,(length,width) in enumerate(zip((36.,27.,21.),(19.,16.,13.))))
    rows=[]
    for name,length,width,distal in variants:
        part=make_phalanx(length,width,distal,name)
        faces=[f for f in part.faces() if f.geom_type==bd.GeomType.PLANE
               and abs(f.center().Y-.75)<1e-7 and f.normal_at().Y<-.999999]
        assert len(faces)==2,(name,'D contact face count',len(faces))
        centers=[-(width/2-.725),width/2-.725]
        overlaps=[]
        for center_x in centers:
            assert part.is_inside((center_x,.90,0)),(name,'material beyond D flat')
            assert not part.is_inside((center_x,.70,0)),(name,'D interior must be open')
            shaft=(bd.Pos(center_x-.725,0,0)*bd.Rot(0,0,90)*bd.Rot(90,0,0)
                   *_drive_bore(1.,.75))
            common=part.intersect(shaft)
            volume=0. if common is None else common.volume
            assert volume<1e-8,(name,'keyed shaft interpenetration',volume)
            overlaps.append(volume)
            if not distal:
                assert not part.is_inside((center_x,length+2.40,0)),(name,'bearing seat void')
                assert part.is_inside((center_x,length+2.70,0)),(name,'bearing annulus material')
        row={'name':name,'length':length,'width':width,'valid':part.is_valid,
             'contact_flat_y':.75,'contact_face_solid_normal':[0,-1,0],
             'shaft_axis':[1,0,0],'bore_radius':1.03,'shaft_radius':1.,
             'flat_face_areas':[f.area for f in faces],
             'shaft_overlap_volumes':overlaps,'distal_bearing_radius':None if distal else 2.53}
        rows.append(row)
        print(name,'PASS',flush=True)
    report={'ok':True,'variant_count':len(rows),'native_sketch_to_finger':'(u,v,w) -> (y,z,x)',
            'drive_flat_native_sketch':'u=+0.75','variants':rows}
    Path(__file__).with_suffix('.json').write_text(json.dumps(report,indent=2)+'\n')

if __name__=='__main__':
    main()
