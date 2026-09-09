"""Hand-side inlet datums for wrist/palm routing, in millimetres.

These are interface positions, not a claim that every downstream thumb and
cup reaction span has passed its geometry gate. Fixed neutral fan rotations
are applied here without modifying joint ranges. The caller then applies the
named attachment frame's articulated transform.
"""
from math import radians,cos,sin
from lib.layout import FINGERS,THUMB_CMC,THUMB_CROSS_AXIS,THUMB_DIRECTION

DEFAULT_NEUTRAL_FAN={'index':20.,'middle':5.,'ring':-5.,'little':-25.}
INLET_Y=-35.


def hand_inlets(neutral_fan=None):
    fan=DEFAULT_NEUTRAL_FAN if neutral_fan is None else neutral_fan
    rows=[]
    def add(name,point,tangent,frame,local):
        rows.append({'tendon':name,'point':list(point),'tangent':list(tangent),
                     'frame':frame,'local_point':list(local)})
    for finger in FINGERS:
        theta=radians(fan.get(finger.name,0.));c,s=cos(theta),sin(theta)
        specs=[('mcp_abduction',1,-5.5,-9.5),('mcp_abduction',-1,5.5,-12.),
               ('mcp_flexion',1,.9,5.5),('mcp_flexion',-1,-.9,-5.5),
               ('pip',1,3.,0.),('pip',-1,-3.,0.),('dip',1,4.2,0.),('dip',-1,-4.2,0.)]
        for joint,sign,x,z in specs:
            suffix='positive' if sign>0 else 'negative'
            splice_y=-12.25 if finger.name=='little' and joint in('pip','dip') else INLET_Y
            point=[finger.x+c*x-s*splice_y,finger.base_y+s*x+c*splice_y,z]
            add(f'{finger.name}_{joint}_{suffix}',point,[-s,c,0.],
                'palm_cup' if finger.name=='little' else 'wrist_flexion',[x,splice_y,z])
    from lib.thumb_cmc_transport import cmc_inlet_contract
    thumb_contract={row['tendon']:row for row in cmc_inlet_contract()}
    specs=[('cmc_abduction',1,-7.,-11.),('cmc_abduction',-1,7.,-13.5),
           ('cmc_flexion',1,.9,7.),('cmc_flexion',-1,-.9,-7.),
           ('mcp_abduction',1,3.,0.),('mcp_abduction',-1,-3.,0.),
           ('mcp_flexion',1,4.2,0.),('mcp_flexion',-1,-4.2,0.),
           ('ip',1,5.4,0.),('ip',-1,-5.4,0.)]
    for joint,sign,x,z in specs:
        suffix='positive' if sign>0 else 'negative'
        splice_x=x
        if joint in('cmc_abduction','cmc_flexion'):
            splice_y=-3. if joint=='cmc_abduction' else -24.
            local_tangent=(0.,1.,0.)
        else:
            datum=thumb_contract[f'thumb_{joint}_{suffix}']
            local_tangent=datum['tangent']
            splice_x,splice_y,z=datum['splice_point']
        point=[THUMB_CMC[i]+splice_x*THUMB_CROSS_AXIS[i]+splice_y*THUMB_DIRECTION[i]+(z if i==2 else 0.) for i in range(3)]
        tangent=[local_tangent[0]*THUMB_CROSS_AXIS[i]+local_tangent[1]*THUMB_DIRECTION[i] for i in range(3)]
        add(f'thumb_{joint}_{suffix}',point,tangent,'wrist_flexion',[splice_x,splice_y,z])
    assert len(rows)==42 and len({r['tendon'] for r in rows})==42
    return rows
