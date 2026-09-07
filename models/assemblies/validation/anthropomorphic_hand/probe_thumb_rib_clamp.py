import sys,json
from pathlib import Path
import numpy as np
from scipy.spatial import cKDTree
HERE=Path(__file__).parent;sys.path.insert(0,str(HERE.parents[1]/'src/anthropomorphic_hand'))
from cadgen import build123d as bd
from lib.palm_frame import make_palm_frame_bodies
from lib.layout import THUMB_CMC
from lib.thumb_cmc_mounts import _host_clamp
from check_guide_combs import common_volume
base=bd.Pos(*THUMB_CMC)*bd.Rot(0,0,45);host=base.inverse()*make_palm_frame_bodies()[0];q=np.array([-1.512673403,-9.118275723,-15.000175788]);cloud=np.load(HERE/'remaining_support_route_cloud.npz')['thumb']
for side in(1,-1):
 lo=q+[-1.9,-.5,-2];hi=q+[1.9,.5,2]
 if side>0:hi[0]=q[0]+3.12
 else:lo[0]=q[0]-3.12
 gaps=np.linalg.norm(np.maximum(np.maximum(lo-cloud,cloud-hi),0),axis=1);print('BOX',side,float(gaps.min()),flush=True)
 hl,hu,hb,foot=_host_clamp(host,*q,side,'probe',width=3.8,height=4)
 print(side,'FOOT',foot,'LOWER',[(s.volume,s.bounding_box()) for s in hl.solids()],'UPPER',len(hu.solids()),'SCREW_HOST',common_volume(hb,host),'FOOT_GAP',bd.Vertex(*foot).distance_to(hl),flush=True)
