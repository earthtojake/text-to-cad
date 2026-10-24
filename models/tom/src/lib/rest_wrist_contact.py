"""Shorten the forearm until its unchanged wrist yoke just touches the shoulder.

The shift is the first zero-distance contact of the selected R6.35 yoke bend
with the supplier shoulder case in Rest. The yoke is never reshaped.
"""
from dataclasses import asdict
from lib.mates import revolute
SHIFT=5.1375567


def wrist_refs(data):
 refs={'wrist_pitch_servo','temporary_wrist_yoke'}
 while True:
  more=refs|{m.child.lstrip('#') for m in data['mates'] if m.parent.lstrip('#') in refs}
  if more==refs:break
  refs=more
 # Case hardware is fastened to the link, outside the movable wrist subtree.
 refs.update(f'elbow_roll_link_plate_pair__hex_socket_m2x6__{i:02}' for i in (3,4,5,6))
 return refs


def revised_kinematics(data):
 refs=wrist_refs(data);mates=[]
 for m in data['mates']:
  d=asdict(m)
  if d['kind']=='revolute' and m.child.lstrip('#') in refs:
   xyz=list(d['axis']['origin']);xyz[0]+=SHIFT
   m=revolute(m.name,parent=m.parent,child=m.child,origin=xyz,direction=d['axis']['dir'],limits=d['limits']['value'])
  mates.append(m)
 return data|{'mates':mates}
