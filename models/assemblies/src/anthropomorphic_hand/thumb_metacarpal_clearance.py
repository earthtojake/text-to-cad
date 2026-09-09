"""Exact component-level clearance, separate from the full assembly gate."""
import json
from pathlib import Path
from cadgen import build123d as bd
from lib.thumb_metacarpal import make_thumb_metacarpal
from lib.universal_carrier import make_universal_carrier
from lib.phalanx import make_phalanx

def volume(a,b):
    c=a.intersect(b)
    return 0. if c is None else sum(s.volume for s in c.solids())

def run():
    m=make_thumb_metacarpal()
    c=make_universal_carrier(phalanx_width=16.,yaw_plane=8.)
    p=make_phalanx(27,16.)
    rows=[]
    cmc=make_universal_carrier(phalanx_width=19.,yaw_plane=9.5)
    for flex in (-15,-10,0,10,20,30,40,50,60,65):
        rows.append({'part':'cmc_carrier','yaw':None,'flex':flex,'common_mm3':volume(bd.Rot(flex,0,0)*m,cmc)})
    for yaw in range(-15,16,5):
        carrier=bd.Pos(0,36,0)*bd.Rot(0,0,yaw)*c
        rows.append({'part':'mcp_carrier','yaw':yaw,'flex':None,'common_mm3':volume(m,carrier)})
        for flex in range(0,71,10):
            proximal=bd.Pos(0,36,0)*bd.Rot(0,0,yaw)*bd.Rot(flex,0,0)*p
            rows.append({'part':'thumb_proximal','yaw':yaw,'flex':flex,'common_mm3':volume(m,proximal)})
    result={'scope':'Metacarpal versus current MCP carrier and proximal phalanx only; tendon and remaining-body checks belong to full assembly gate.',
            'max_common_mm3':max(r['common_mm3'] for r in rows),'rows':rows}
    out=Path('models/assemblies/validation/anthropomorphic_hand/thumb_metacarpal_clearance.json')
    out.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k!='rows'}))
    assert result['max_common_mm3']<1e-6

if __name__=='__main__':run()
