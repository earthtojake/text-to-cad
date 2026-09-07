import sys,numpy as np,json
from pathlib import Path
from scipy.spatial import cKDTree
sys.path.insert(0,'models/assemblies/src/anthropomorphic_hand')
from lib.palm_frame_paths import PALM_PATHS
from lib.path_analysis import sample_path
cloud=np.load('models/assemblies/validation/anthropomorphic_hand/palm_cmc_metacarpal_envelope_points.npz')['points'];tree=cKDTree(cloud);rows=[]
for row in PALM_PATHS:
 p=sample_path([{'kind':'bezier','points':s} for s in row['segments']],.03)
 reserve=.61+.017454*np.minimum(np.linalg.norm(p-[-35,36,0],axis=1)+2,43.8)
 d=tree.query(p)[0]-row['radius']-reserve-.015
 rows.append({'branch':row['name'],'conservative_swept_metacarpal_gap_mm':float(d.min())})
result={'scope':'17 full-radius frame ribs versus thumb metacarpal surface swept through 5751 yaw/flex poses. Full rib sample coverage and conservative mesh, voxel, vertex quantization and angular reserves. This certificate does not include separate bearing bosses.','poses':5751,'mesh_chord_mm':.08,'triangle_max_edge_mm':.30,'vertex_quantization_mm':.08,'voxel_spacing_mm':.30,'angular_step_degrees':1,'rib_sample_step_mm':.03,'reserve_formula_mm':'.61 + .017454 * min(distance_from_CMC_axis_origin + 2, 43.8) + .015','point_count':len(cloud),'rows':rows,'failures':[r for r in rows if r['conservative_swept_metacarpal_gap_mm']<0]}
Path('models/assemblies/validation/anthropomorphic_hand/palm_cmc_metacarpal_envelope.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))

