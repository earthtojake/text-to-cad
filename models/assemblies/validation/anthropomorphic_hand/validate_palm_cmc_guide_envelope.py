import sys,numpy as np,json
from pathlib import Path
sys.path.insert(0,'models/assemblies/src/anthropomorphic_hand')
from scipy.spatial import cKDTree
from lib.palm_frame_paths import PALM_PATHS
from lib.path_analysis import sample_path
q=np.load('models/assemblies/validation/anthropomorphic_hand/palm_cmc_guide_envelope_points.npz')['points'];G=cKDTree(q);rows=[]
for p in PALM_PATHS:
 a=sample_path([{'kind':'bezier','points':x} for x in p['segments']],.03);d=G.query(a)[0].min()-p['radius']-1.1-.015;rows.append({'branch':p['name'],'conservative_swept_mount_gap_mm':float(d)})
result={'scope':'all 17 full-radius frame ribs versus18 moving CMC mounts over5751 yaw/flex poses, with1.1mm surface/voxel/angular reserve plus0.015mm rib sampling reserve','mesh_chord_tolerance_mm':.08,'max_mesh_edge_mm':.30,'base_vertex_quantization_mm':.08,'voxel_spacing_mm':.30,'angle_step_degrees':1,'point_count':len(q),'radial_extent_mm':float(np.linalg.norm(q-[-35,36,0],axis=1).max()),'bound_mm':1.1,'rows':rows,'failures':[r for r in rows if r['conservative_swept_mount_gap_mm']<0]}
Path('models/assemblies/validation/anthropomorphic_hand/palm_cmc_guide_envelope.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
