"""Assert completed housing proofs before issuing its integration certificate."""
import json,hashlib
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[3]
load=lambda n:json.loads((HERE/n).read_text())
files=['forearm_housing_strict.json','forearm_housing_check.json','forearm_housing_actuators.json','forearm_housing_seats.json','forearm_housing_cap_relief.json','forearm_housing_continuous_capstan.json','forearm_housing_presentation_certificate.json']
reports=[load(n) for n in files]
assert all(r['ok'] for r in reports)
strict,fit,act,seat,relief,continuous,render=reports
assert strict['occurrenceCount']==42 and strict['selfIntersectionCheck']=='every-placement'
assert not fit['partial'] and not fit['failures'] and fit['mutual_pairs']==861 and fit['host_pairs']==39228
assert fit['capstan_routes']==1008 and fit['wrist_route_packets']==18 and fit['wrist_hardware_poses']>10
assert len(seat['seats'])==28 and len(seat['removal'])==240
assert len(relief['removal_samples'])==42
assert act['context_step_sha256']==render['step_sha256']
current=hashlib.sha256((ROOT/'models/assemblies/STEP/anthropomorphic_hand/forearm_housing_review.step').read_bytes()).hexdigest()
assert current==render['housing_step_sha256']
out={'ok':True,'occurrences':42,'prototypeCount':strict['prototypeCount'],'housing_step_sha256':current,
     'neutral_mutual_pairs':861,'frame_and_fastener_pairs':39228,'actual_actuator_pairs':act['pairs'],
     'neutral_routes':48,'sampled_capstan_routes':1008,'continuous_capstan_range_rad':continuous['rotation_range_rad'],
     'continuous_capstan_minimum_clearance_lower_bound_mm':continuous['minimum_surface_clearance_bound_mm'],
     'wrist_route_packets':18,'wrist_hardware_poses':fit['wrist_hardware_poses'],
     'bearing_seats':28,'initial_removal_samples':240,'corrected_cap_crossbrace_samples':42,'proof_files':files,'failures':[]}
(HERE/'forearm_housing_certificate.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))
