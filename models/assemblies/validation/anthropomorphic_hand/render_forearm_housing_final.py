"""Wait for the owned final build, then hash and render exactly its bytes."""
import hashlib,json,os,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[4];HERE=Path(__file__).resolve().parent
if len(sys.argv)>1:
    pid=int(sys.argv[1])
    while True:
        try:os.kill(pid,0)
        except ProcessLookupError:break
        time.sleep(2)
build=json.loads((HERE/'forearm_housing_context_build.json').read_text())
assert build['ok']
target=ROOT/'models/assemblies/STEP/anthropomorphic_hand/forearm_housing_context.step'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
before=sha(target)
command=[sys.executable,'-m','cadgen.cli','step','snapshot','--job',str(HERE/'forearm_housing_context_render_job.json'),'--json']
r=subprocess.run(command,cwd=ROOT,capture_output=True,text=True)
(HERE/'forearm_housing_context_snapshot.json').write_text(r.stdout)
(HERE/'forearm_housing_context_snapshot.log').write_text(r.stderr)
assert r.returncode==0,r.stderr
after=sha(target);assert before==after,'Context STEP changed during snapshot'
report={'ok':True,'build':build,'step':str(target),'step_sha256':before,'render_input_sha256':before,'render_input_sha256_after':after,
        'image_sha256':sha(HERE/'forearm_housing_context.png'),'render_job_sha256':sha(HERE/'forearm_housing_context_render_job.json'),
        'housing_step_sha256':sha(target.with_name('forearm_housing_review.step')),
        'factory_sha256':sha(ROOT/'models/assemblies/src/anthropomorphic_hand/lib/forearm_housing.py')}
(HERE/'forearm_housing_presentation_certificate.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report),flush=True)
