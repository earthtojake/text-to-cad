"""Prove the original +Y inlet cannot clear the CMC carrier at yaw45.

For any unit-speed path with curvature <=1/R, integrating |t(s)-t(0)|<=s/R
bounds its displacement from its initial tangent by s²/(2R). At s=2.45mm
that complete reachable ball is covered by the .45mm dilation of a real
annular core of the carrier. The distance-to-core function is1-Lipschitz;
the sampled boundary maximum includes a conservative half-interval bound.
The radial/axial distance is convex, so the disk maximum is on its boundary.
"""
import json,sys
from pathlib import Path
import numpy as np
sys.path.insert(0,'models/assemblies/src/anthropomorphic_hand')
from cadgen import build123d as bd
from lib.universal_carrier import make_universal_carrier
R=3.5;s=2.45;liner_radius=.45;yaw=np.pi/4
rot=np.array([[np.cos(yaw),np.sin(yaw),0],[-np.sin(yaw),np.cos(yaw),0],[0,0,1]])
straight=rot@(np.array([-5.4,-12.25,0])+s*np.array([0,1,0]))
ball=s*s/(2*R)
t=np.linspace(0,2*np.pi,100001)
x=straight[0]+10.5+ball*np.cos(t)
r=np.linalg.norm(straight[1:])+ball*np.sin(t)
d=np.hypot(np.maximum(abs(x)-.76,0),np.maximum.reduce([2.53-r,r-3.56,np.zeros(len(t))]))
bound=ball*np.pi/100000
carrier=make_universal_carrier(phalanx_width=19,yaw_plane=9.5)
core=bd.Pos(-10.5,0,0)*bd.Rot(0,90,0)*(bd.Cylinder(3.56,1.52)-bd.Cylinder(2.53,2.0))
outside=sum(z.volume for z in core.cut(carrier).solids())
report={'original_inlet':[-5.4,-12.25,0],'original_tangent':[0,1,0],'yaw_deg':45,'minimum_radius_mm':R,'arclength_mm':s,'straight_reference_in_yaw_frame':straight.tolist(),'reachable_ball_radius_mm':ball,'guaranteed_annular_core':{'center_x':-10.5,'inner_radius':2.53,'outer_radius':3.56,'half_thickness':.76},'core_outside_actual_carrier_volume_mm3':outside,'maximum_ball_distance_to_core_mm':float(d.max()),'sampling_lipschitz_bound_mm':bound,'liner_radius_mm':liner_radius,'positive_coverage_margin_mm':float(liner_radius-d.max()-bound),'proven_impossible':outside<1e-10 and d.max()+bound<liner_radius}
Path(__file__).with_name('thumb_cmc_inlet_reachability.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
assert report['proven_impossible']
