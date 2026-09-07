import sys,numpy as np,time
sys.path.insert(0,'models/assemblies/src/anthropomorphic_hand')
from cadgen import read_step
from lib.layout import assembled_transforms
from lib.palm_frame_paths import PALM_PATHS
from lib.path_analysis import sample_path
from scipy.spatial import cKDTree
import trimesh
from cadgen import build123d as bd
from lib.thumb_metacarpal import make_thumb_metacarpal
parts=[bd.Pos(-35,36,0)*bd.Rot(0,0,45)*make_thumb_metacarpal()];verts=[]
for p in parts:
 v,f=p.tessellate(.08,.1);v=np.array([tuple(x) for x in v]);v,f=trimesh.remesh.subdivide_to_size(v,np.array(f),max_edge=.30,max_iter=8);verts.append(v);print('MESH',p.label,len(v),flush=True)
q=np.vstack(verts);print('SOURCE_RMAX',np.linalg.norm(q-[-35,36,0],axis=1).max(),flush=True);q=np.unique(np.round(q/.08).astype(np.int32),axis=0)*.08
lo=np.array([-85,10,-28]);spacing=.3;shape=(300,310,300);occ=np.zeros(shape,dtype=bool)
for yaw in range(-25,46):
 for flex in range(-15,66):
  m=assembled_transforms({'thumb_cmc_abduction':yaw,'thumb_cmc_flexion':flex})['thumb_cmc_flexion'];p=q@np.asarray(m)[:3,:3].T+np.asarray(m)[:3,3];ijk=np.round((p-lo)/spacing).astype(np.int32)
  if np.any(ijk<0) or np.any(ijk>=np.array(shape)):raise ValueError(('voxel bounds',yaw,flex,p.min(0),p.max(0)))
  occ[ijk[:,0],ijk[:,1],ijk[:,2]]=True
 if yaw%10==5:print('YAW',yaw,'occupied',occ.sum(),flush=True)
cloud=np.argwhere(occ)*spacing+lo;np.savez_compressed('models/assemblies/validation/anthropomorphic_hand/palm_cmc_metacarpal_envelope_points.npz',points=cloud);tree=cKDTree(cloud)
for row in PALM_PATHS:
 p=sample_path([{'kind':'bezier','points':s} for s in row['segments']],.05);d=tree.query(p)[0]-row['radius']-1.5;print('BRANCH',row['name'],'conservative_gap',d.min(),flush=True)
print('DONE',len(cloud),flush=True)
