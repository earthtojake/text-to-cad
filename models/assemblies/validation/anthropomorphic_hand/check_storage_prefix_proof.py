"""Positive and adversarial checks of the native stored-rope prefix transfer."""
import copy,json,math,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE.parents[1]/'src/anthropomorphic_hand'))
from lib.layout import TENDONS
from lib.forearm_routing import forearm_route
from native_storage_prefix_proof import verify_prefix

def main():
    count=0;maximum=0.
    for tendon in TENDONS:
        for q in (-5*math.pi,-1.2,0.,1.2,5*math.pi):
            route=forearm_route(tendon,q);route['capstan_rotation']=q
            result=verify_prefix(route,tendon);maximum=max(maximum,result['maximum_control_point_residual_mm']);count+=1
    tendon=TENDONS[0];route=forearm_route(tendon,1.2);route['capstan_rotation']=1.2
    rejected=0
    for mutation in ('displaced_control','missing_quarter','wrong_rotation','wrong_bank'):
        bad=copy.deepcopy(route);station=dict(tendon)
        if mutation=='displaced_control':bad['groups'][0]['path'][0]['points'][2][0]+=.001
        elif mutation=='missing_quarter':bad['groups'][0]['path'].pop(1)
        elif mutation=='wrong_rotation':bad['capstan_rotation']+=.001
        else:station['sign']*=-1
        try:verify_prefix(bad,station)
        except AssertionError:rejected+=1
    assert rejected==4
    report=dict(valid_cases=count,adversarial_cases_rejected=rejected,maximum_control_point_residual_mm=maximum,pass_=True)
    (HERE/'storage_prefix_proof_tests.json').write_text(json.dumps(report,indent=2)+'\n');print(report)
if __name__=='__main__':main()
