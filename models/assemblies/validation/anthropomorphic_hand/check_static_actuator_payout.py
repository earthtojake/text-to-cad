"""Payout capacity for every already evaluated static pose, without choreography."""
import sys,json,gzip,hashlib,time
from pathlib import Path
HERE=Path(__file__).parent
sys.path.insert(0,str(HERE.parents[1]/'src/anthropomorphic_hand'))
from lib.actuator_payout import solve_rotation,neutral_forearm_length,_BY_NAME
from lib.forearm_routing import forearm_route
from lib.path_analysis import path_length
manifest=json.loads((HERE/'static_route_packet_manifest.json').read_text())
assert manifest['complete'] and manifest['sample_count']==225
neutral=json.loads(gzip.decompress(Path(manifest['rows'][0]['file']).read_bytes()))['routes']
base={r['name']:path_length(r['path']) for r in neutral}
report={'complete':False,'pass':False,'routing_manifest_sha256':manifest['source_sha256'],'rows':[],'scope':'Actual changing spool storage and free-lead lengths; downstream geometry is the unchanged static route packet. Collision checks at these corrected capstan angles remain required.'}
cache={};start=time.monotonic()
for entry in manifest['rows']:
 routes=json.loads(gzip.decompress(Path(entry['file']).read_bytes()))['routes'];rows=[]
 for r in routes:
  name=r['name'];change=path_length(r['path'])-base[name]
  key=(name,round(change,10))
  if key not in cache:cache[key]=solve_rotation(name,change)
  q=cache[key]
  residual=path_length(forearm_route(_BY_NAME[name],q)['path'])-neutral_forearm_length(name)+change
  rows.append({'tendon':name,'downstream_change_mm':change,'capstan_rotation_rad':q,'total_length_residual_mm':residual,'pass':abs(residual)<1e-7})
 report['rows'].append({'label':entry['label'],'tendons':rows,'pass':all(r['pass'] for r in rows)})
 (HERE/'static_actuator_payout.json').write_text(json.dumps(report,indent=2)+'\n')
 print(len(report['rows']),entry['label'],max(abs(r['capstan_rotation_rad']) for r in rows),flush=True)
report['complete']=True;report['pass']=all(r['pass'] for r in report['rows']);report['elapsed_seconds']=time.monotonic()-start
(HERE/'static_actuator_payout.json').write_text(json.dumps(report,indent=2)+'\n')
assert report['pass']
