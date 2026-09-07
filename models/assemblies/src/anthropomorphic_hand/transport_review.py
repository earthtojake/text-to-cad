"""Exact six-lane MCP-yaw transport prototype; supports remain separate work."""
from cadgen import build123d as bd, step
from lib.axis_transport import crossover
from lib.transport_guide import make_guide, make_tendon


@step(out='../../STEP/anthropomorphic_hand/transport_review.step',
      mesh_tolerance=.006,mesh_angular_tolerance=.035)
def transport_review():
    bodies=[]
    for i in range(6):
        route=crossover(i,6,angle_deg=0,angle_range=(-20,20))
        bodies.append(make_tendon(route['path'],f'channel_{i+1:02d}_continuous_tendon'))
        bodies.append(make_guide(route['path'][0],f'channel_{i+1:02d}_parent_inlet_guide'))
        bodies.append(make_guide(route['path'][2],f'channel_{i+1:02d}_child_outlet_guide'))
    return bd.Compound(label='coaxial_transport_six_lane_geometry_prototype',children=bodies)


if __name__=='__main__':
    transport_review()
