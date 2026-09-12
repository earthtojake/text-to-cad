"""Complete the15-body native gate and full-hand context presentation."""
import json,subprocess,sys,time,hashlib,shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parents[4];HERE=Path(__file__).resolve().parent
SRC=ROOT/'models/assemblies/src/anthropomorphic_hand';STEP=ROOT/'models/assemblies/STEP/anthropomorphic_hand'
report=HERE/'phalanx_beauty_subset.json'
while not report.exists():time.sleep(2)
r=json.loads(report.read_text());assert r['pass']
# The generic36-mm factory probe was deliberately extra coverage. The actual
# thumb metacarpal is a different, unchanged curved factory, kept in the15-body gate.
r['extra_factory_probe']=[x for x in r['rows'] if x['name']=='thumb_metacarpal_frame']
r['rows']=[x for x in r['rows'] if x['name']!='thumb_metacarpal_frame']
r['unchanged_actual_thumb_metacarpal']={'source':'lib/thumb_metacarpal.py','sha256':hashlib.sha256((SRC/'lib/thumb_metacarpal.py').read_bytes()).hexdigest(),'basis':'No changes to the actual separate metacarpal factory or imported native STEP.'}
(HERE/'phalanx_beauty_actual_subset.json').write_text(json.dumps(r,indent=2)+'\n')
def run(args,stem):
    print(stem,flush=True)
    with (HERE/(stem+'.log')).open('w') as stream:
        result=subprocess.run([sys.executable,*args],cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT)
    assert result.returncode==0,(stem,result.returncode)
run([str(SRC/'phalanx_beauty_review.py')],'phalanx_beauty_build')
run(['-m','cadgen.cli','step','inspect','validate',str(STEP/'phalanx_beauty_review.step'),'--every-placement','--out',str(HERE/'phalanx_beauty_strict.json')],'phalanx_beauty_strict')
run([str(SRC/'phalanx_beauty_context.py')],'phalanx_beauty_context_build')
shutil.copyfile(STEP/'hand_progress_review.step.js',STEP/'phalanx_beauty_context.step.js')
run(['-m','cadgen.cli','step','snapshot','--job',str(SRC/'phalanx_beauty_render_job.json'),'--json'],'phalanx_beauty_render')
print('DONE',flush=True)
