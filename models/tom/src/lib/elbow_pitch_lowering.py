"""Remove the lower bend's excess rise and lower its elbow by that amount.

The elbow, roll servo, forearm and wrist translate together in Rest; their
relative geometry and joint alignment are preserved.
The standard yoke outline is locked: no collar, neck, flange or bend changes.
"""
from dataclasses import asdict
from lib.mates import revolute
# Keep this tied to those stock dimensions, not the servo's bottom edge.
# The distal servo mounting flange now shares the lower rail's bottom datum.
DROP=73.187423305501-68.3


def moving_refs(data):
    refs={'elbow_pitch_yoke'}
    while True:
        more=refs|{m.child.lstrip('#') for m in data['mates'] if m.parent.lstrip('#') in refs}
        if more==refs:break
        refs=more
    refs.add('elbow_pitch_servo')
    refs.update(f'elbow_side_m2x6_{i}' for i in range(1,5))
    return refs

def revised_kinematics(data):
    moving=moving_refs(data);mates=[]
    for m in data['mates']:
        r=asdict(m)
        if r['kind']=='revolute' and m.child.lstrip('#') in moving:
            xyz=list(r['axis']['origin']);xyz[2]-=DROP
            m=revolute(m.name,parent=m.parent,child=m.child,origin=xyz,
                       direction=r['axis']['dir'],limits=r['limits']['value'])
        mates.append(m)
    return data|{'mates':mates}
