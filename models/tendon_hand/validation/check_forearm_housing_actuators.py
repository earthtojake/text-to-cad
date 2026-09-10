"""Actual motor, gearbox, sensor and capstan solids against housing."""
import json,time,sys,os,hashlib
from pathlib import Path
from check_forearm_housing import read_step,leaves,overlap,STEP,HERE
start=time.monotonic()
if len(sys.argv)>1:
    while True:
        try:os.kill(int(sys.argv[1]),0)
        except ProcessLookupError:break
        time.sleep(2)
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
input_sha=sha(STEP/'forearm_housing_context.step')
housing=leaves(read_step(STEP/'forearm_housing_review.step'))
actuators=[s for s in leaves(read_step(STEP/'forearm_housing_context.step')) if '_context_' in s.label]
assert len(housing)==42 and len(actuators)>700
report={'ok':False,'housing_bodies':42,'actuator_bodies':len(actuators),'pairs':0,'failures':[]}
for a in housing:
    for b in actuators:
        report['pairs']+=1;v=overlap(a,b)
        if v>1e-7:report['failures'].append({'a':a.label,'actuator':b.label,'overlap':v})
report['ok']=not report['failures'];report['seconds']=time.monotonic()-start
report['context_step_sha256']=input_sha
assert input_sha==sha(STEP/'forearm_housing_context.step'),'Context changed during actuator audit'
(HERE/'forearm_housing_actuators.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report))
raise SystemExit(0 if report['ok'] else 1)
