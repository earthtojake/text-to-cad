"""Short free-end shoulders clear the unchanged hyperextension tendon curves."""
from cadgen import build123d as bd
from lib.axle import make_driven_axle
from lib.retaining_ring import make_retaining_ring
from lib.finish import finish

def make_compact_mcp_dorsal_axle():
    # Journal starts at -17.72; tip -8.435; ring center -8.60.
    # The pulley face stays -8.75, leaving a real .03 axial ring gap.
    stock=make_driven_axle(length=10.5,radius=1.,flat=.75,head_radius=1.6)
    stock=stock-(bd.Pos(0,0,9.285)*bd.Box(10,10,6,align=(bd.Align.CENTER,bd.Align.CENTER,bd.Align.MIN)))
    stock=stock-bd.Pos(0,0,9.12)*(bd.Cylinder(1.2,.25)-bd.Cylinder(.82,.5))
    edges=[e for e in stock.edges() if e.geom_type==bd.GeomType.CIRCLE and e.bounding_box().min.Z>8.98]
    if edges:stock=bd.fillet(edges,.008)
    # Relieve only the terminal shoulder in the circlip's open sector. The
    # groove and shoulder beneath the retained 280-degree clip remain real;
    # the keyed journal through both unchanged drive pulleys is untouched.
    import json,math,numpy as np
    from pathlib import Path
    from lib.finger_routing import transform_path
    from lib.transport_guide import path_wire
    report=Path(__file__).resolve().parents[3]/'validation/anthropomorphic_hand/secondary_hardware_diagnostic.json'
    row=next(r for r in json.loads(report.read_text()) if r['body']=='index_mcp_abduction_dorsal_drive_stub_keyed_shaft')
    a=math.radians(110);m=np.array([[math.cos(a),-math.sin(a),0,-36],[math.sin(a),math.cos(a),0,101],[0,0,1,-17.72],[0,0,0,1.]])
    wire=path_wire(transform_path(row['path_neutral'],np.linalg.inv(m)))
    cutter=bd.sweep(bd.Plane(origin=wire.position_at(0),z_dir=wire.tangent_at(0))*bd.Circle(.50),path=wire,is_frenet=True)
    stock=stock-cutter
    assert stock.is_valid and len(stock.solids())==1
    return finish(stock,'steel','compact_MCP_dorsal_axle')

def compact_mcp_dorsal_hardware():
    from lib.layout import FINGERS,JOINT_BY_NAME,finger_fan_matrix
    from lib.assembly import matrix_location,joint_location
    axle=make_compact_mcp_dorsal_axle();ring=make_retaining_ring(opening_half_angle=40)
    out=[]
    for f in FINGERS:
        j=JOINT_BY_NAME[f.name+'_mcp_abduction'];base=matrix_location(finger_fan_matrix(f))*joint_location(j)
        for shape,where,kind,suffix in [(axle,bd.Pos(0,0,-17.72),'shaft','keyed_shaft'),
                                      (ring,bd.Pos(0,0,-8.60)*bd.Rot(0,0,275),'retaining_ring','retaining_ring')]:
            p=base*where*shape;p.label=j.name+'_dorsal_drive_stub_'+suffix
            out.append((p,j.name,f.name,kind))
    return out
