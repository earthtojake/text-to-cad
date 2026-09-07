"""Verify authored gear axes and rope terminations under actual payout motion."""
import hashlib,json,math,sys
from pathlib import Path
import numpy as np
HERE=Path(__file__).resolve().parent;SRC=HERE.parents[1]/'src/anthropomorphic_hand'
sys.path.insert(0,str(SRC))
from lib.actuator_kinematics import actuator_transform
from lib.forearm_routing import forearm_route
from lib.layout import TENDONS

def main():
    rows=[]
    for tendon in TENDONS:
        sign=tendon['sign'];basis=np.diag([sign,1.,sign]);origin=np.array([*tendon['actuator_center'][:2],sign*4.])
        def world(p):return np.r_[origin+basis@np.asarray(p),1.]
        for q in (-5*math.pi,-1.2,0.,1.2,5*math.pi):
            neutral=forearm_route(tendon,0.)['inlet'];posed=forearm_route(tendon,q)['inlet']
            spool=actuator_transform(tendon,'capstan',q)
            endpoint_error=float(np.linalg.norm((spool@np.r_[neutral,1.])[:3]-posed))
            assert endpoint_error<1e-10
            errors=[]
            for index in range(3):
                a=index*2*math.pi/3;center=np.array([3*math.cos(a),3*math.sin(a),19.45])
                planet=actuator_transform(tendon,f'gearbox_planet_{index+1}',q)
                pin=actuator_transform(tendon,f'gearbox_planet_pin_{index+1}',q)
                center_error=float(np.linalg.norm(planet@world(center)-pin@world(center)))
                expected=world([3*math.cos(a+q),3*math.sin(a+q),19.45])
                orbit_error=float(np.linalg.norm(planet@world(center)-expected))
                direction=(planet@world(center+[1.,0.,0.])-planet@world(center))[:3]
                rolling_error=float(np.linalg.norm(direction-basis@np.array([math.cos(-2*q),math.sin(-2*q),0.])))
                assert max(center_error,orbit_error,rolling_error)<1e-10
                errors.extend([center_error,orbit_error,rolling_error])
            sun=actuator_transform(tendon,'gearbox_sun',q);shaft=actuator_transform(tendon,'motor_shaft',q)
            input_error=float(np.linalg.norm(sun@world([1,0,19])-shaft@world([1,0,19])))
            assert input_error<1e-10 and actuator_transform(tendon,'gearbox_ring',q) is None
            rows.append(dict(tendon=tendon['name'],rotation_rad=q,spool_endpoint_error_mm=endpoint_error,planet_axis_orbit_rolling_max_error=max(errors),input_key_error_mm=input_error,pass_=True))
    files=[Path(__file__),*[SRC/'lib'/n for n in ('actuator_kinematics.py','forearm_routing.py','capstan_path.py','layout.py')]]
    report=dict(scope=__doc__,input_sha256={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in files},rows=rows,pass_=True)
    (HERE/'actuator_kinematics_gate.json').write_text(json.dumps(report,indent=2)+'\n');print('ACTUATOR KINEMATICS',len(rows),'PASS')
if __name__=='__main__':main()
