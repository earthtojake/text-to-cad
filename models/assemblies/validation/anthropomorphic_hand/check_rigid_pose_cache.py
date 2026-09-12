"""Verify symbolic reuse against every frame pair in every authored static pose."""
import json
import sys
from itertools import combinations_with_replacement
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / 'src/anthropomorphic_hand'))
from lib.layout import JOINT_BY_NAME, assembled_transforms
from rigid_pose_cache import relative_pose_key

samples = json.loads((HERE/'static_route_packet_manifest.json').read_text())['rows']
frames = ['forearm', *JOINT_BY_NAME]
pairs = list(combinations_with_replacement(frames, 2))
cached = {}
reuse = 0
maximum_error = 0.
for sample in samples:
    pose = sample['pose']
    transforms = assembled_transforms(pose)
    inverses = {frame: np.linalg.inv(matrix) for frame, matrix in transforms.items()}
    for a, b in pairs:
        key = relative_pose_key(a, a, b, b, pose)
        relative = inverses[a] @ transforms[b]
        if key in cached:
            error = float(np.max(np.abs(relative-cached[key])))
            maximum_error = max(maximum_error, error)
            assert error < 1e-11, (sample['label'], a, b, key, error)
            reuse += 1
        else:
            cached[key] = relative
assert relative_pose_key('a','wrist_flexion','b','thumb_ip',{'thumb_ip':20.}) != relative_pose_key(
    'a','wrist_flexion','b','thumb_ip',{'thumb_ip':20.00000000001})
report = {'pass':True, 'poses':len(samples), 'frame_pairs':len(pairs),
          'unique_relative_poses':len(cached), 'exact_symbolic_reuses':reuse,
          'largest_floating_point_matrix_residual':maximum_error}
(HERE/'rigid_pose_cache_check.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report))
