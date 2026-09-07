"""Full-route self-spacing at all225 static poses, including same-tendon groups.

Every curve has certified curvature radius>=3.5mm. Schur's chord comparison
excludes local-neighbour contacts on subarcs of length<=pi*3.5: the tube's
radius<=0.45 is below its local focal radius. All remaining close pairs use
bounded-arclength point clouds and a0.10mm two-sided sampling reserve.
"""
import sys,json,gzip,hashlib,multiprocessing,math
from pathlib import Path
import numpy as np
from scipy.spatial import cKDTree
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'src/anthropomorphic_hand'))
from lib.path_analysis import sample_path
from check_hand_route_pairs import group_radius
ROOT=Path(__file__).parent
STEP=.1;RMIN=3.5
CHORD_RATIO=math.sin(STEP/(2*RMIN))/(STEP/(2*RMIN))

def check_route(route):
    points=[];radii=[]
    for group in route['groups']:
        p=sample_path(group['path'],STEP)
        # Retain both coincident join samples: their radii may differ where
        # an exposed rope enters its reaction liner.
        points.extend(p);radii.extend([group_radius(group)]*len(p))
    p=np.asarray(points);r=np.asarray(radii)
    arc_upper=np.r_[0.,np.cumsum(np.linalg.norm(np.diff(p,axis=0),axis=1))/CHORD_RATIO]
    pairs=cKDTree(p).query_pairs(2*float(r.max())+STEP+1e-6,output_type='ndarray')
    if not len(pairs):return {'tendon':route['name'],'sample_points':len(p),'nonlocal_close_pairs':0,'minimum_checked_gap_mm':None,'pass':True}
    pairs=pairs[(arc_upper[pairs[:,1]]-arc_upper[pairs[:,0]])>math.pi*RMIN]
    gap=np.linalg.norm(p[pairs[:,0]]-p[pairs[:,1]],axis=1)-r[pairs[:,0]]-r[pairs[:,1]]-STEP if len(pairs) else np.array([])
    failures=[]
    for i in np.flatnonzero(gap<0)[:20]:
        a,b=pairs[i];failures.append({'point_a':p[a].tolist(),'point_b':p[b].tolist(),'surface_gap_lower_bound_mm':float(gap[i]),'arclength_upper_separation_mm':float(arc_upper[b]-arc_upper[a])})
    return {'tendon':route['name'],'sample_points':len(p),'nonlocal_close_pairs':len(pairs),'minimum_checked_gap_mm':float(gap.min()) if len(gap) else None,'failures':failures,'pass':not failures}


def partition(index):
    manifest=json.loads((ROOT/'static_route_packet_manifest.json').read_text());cache={};rows=[]
    file=ROOT/f'tendon_self_spacing_partition_{index}.json'
    for sample in manifest['rows']:
        packet=json.loads(gzip.decompress(Path(sample['file']).read_bytes()));assert packet['source_sha256']==manifest['source_sha256']
        results=[]
        for route in packet['routes'][index::4]:
            key=hashlib.sha256(json.dumps([(g['path'],group_radius(g)) for g in route['groups']],sort_keys=True).encode()).digest()
            if key not in cache:cache[key]=check_route(route)
            results.append(cache[key])
        rows.append({'sample':sample['label'],'tendons':results,'pass':all(r['pass'] for r in results)})
        file.write_text(json.dumps({'source_sha256':manifest['source_sha256'],'complete':len(rows)==225,'rows':rows},indent=2)+'\n')
        print('SELF SPACING',index,len(rows),sample['label'],rows[-1]['pass'],flush=True)
    return str(file)

if __name__=='__main__':
    gate=json.loads((ROOT/'static_full_tendon_curve_gate.json').read_text());assert gate['pass'] and gate['complete']
    with multiprocessing.get_context('spawn').Pool(4) as pool:files=pool.map(partition,range(4))
    parts=[json.loads(Path(p).read_text()) for p in files];rows=[]
    for i in range(225):
        names={p['rows'][i]['sample'] for p in parts};assert len(names)==1
        tendons=[r for p in parts for r in p['rows'][i]['tendons']];assert len(tendons)==48 and len({r['tendon'] for r in tendons})==48
        rows.append({'sample':names.pop(),'tendons':tendons,'pass':all(r['pass'] for r in tendons)})
    report={'source_sha256':gate['source_sha256'],'sample_count':225,'tendon_count':48,'sampling_reserve_mm':STEP,'local_curvature_certificate':'static_full_tendon_curve_gate.json','rows':rows,'pass':all(r['pass'] for r in rows)}
    (ROOT/'static_tendon_self_spacing_gate.json').write_text(json.dumps(report,indent=2)+'\n')
    print('225POSE SELF SPACING',report['pass'],flush=True)
    if not report['pass']:raise SystemExit(1)
