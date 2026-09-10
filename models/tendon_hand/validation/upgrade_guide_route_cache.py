import sys,json,io,hashlib
from pathlib import Path
from cadgen import read_step,build123d as bd
from check_guide_mount_mutual import leaves
HERE=Path(__file__).parent;file=HERE/(sys.argv[1]+'_route_distance_cache.json');step=Path(sys.argv[2]);saved=json.loads(file.read_text())
if saved.get('schema')==2:print('already current');raise SystemExit
assert hashlib.sha256(step.read_bytes()).hexdigest()==saved['step_sha256']
parts=leaves(read_step(step));hashes=[]
for p in parts:
 stream=io.BytesIO();bd.export_brep(p,stream);hashes.append(hashlib.sha256(stream.getvalue()).hexdigest())
values={hashes[int(k.split(':',1)[0])]+':'+k.split(':',1)[1]:v for k,v in saved['values'].items()}
file.write_text(json.dumps({'schema':2,'step_sha256':saved['step_sha256'],'body_brep_sha256':dict(zip((p.label for p in parts),hashes)),'values':values})+'\n');print('upgraded',len(parts),'bodies',len(values),'exact cached distances')
