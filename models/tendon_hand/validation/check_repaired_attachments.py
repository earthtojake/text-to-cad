"""Native same-frame attachment graph from repaired supports to their hosts.

A0.025mm seating/fastener clearance matches the existing attachment contract.
This graph is complementary to strict solids and zero-interference checks.
"""
import heapq,itertools,json
import numpy as np
from scipy.spatial import cKDTree
from native_hand_registry import native_current_bodies,sha,HERE
from check_full_route_bodies import placed_bounds

def main():
    bodies,inputs=native_current_bodies(include_reliefs=True)
    proof_path=HERE/'static_clearance_relief_build.json';proof=json.loads(proof_path.read_text());targets=set(proof['body_frames'])
    inputs[str(__file__)]=sha(__file__);inputs[str(proof_path)]=sha(proof_path)
    rows=[]
    for frame in sorted(set(proof['body_frames'].values())):
        selected=[b for b in bodies if b.frame==frame];by_name={b.name:b for b in selected}
        if frame=='wrist_flexion':anchors={'wrist_palm_cradle'}
        elif frame=='palm_cup':anchors={'palm_cup_keyed_shaft'}
        else:anchors={b.name for b in selected if b.kind in ('frame','phalanx','carrier') and b.name not in targets}
        assert anchors and anchors<=set(by_name),(frame,anchors)
        bounds=placed_bounds(selected);edges=[];solids={};vertices={};trees={};graph={n:{} for n in by_name};proven={}
        expected=targets&set(by_name)
        for a,b in itertools.combinations(selected,2):
            ba,bb=bounds[a.name],bounds[b.name]
            lo=np.array(tuple(ba.min));hi=np.array(tuple(ba.max));blo=np.array(tuple(bb.min));bhi=np.array(tuple(bb.max))
            lower=float(np.linalg.norm(np.maximum(np.maximum(lo-bhi,blo-hi),0.)))
            if lower>.025001:continue
            for body in (a,b):
                if body.name not in solids:
                    ss=body.shape.solids();assert len(ss)==1,body.name;solids[body.name]=ss[0]
                    vertices[body.name]=np.asarray([tuple(v.center()) for v in ss[0].vertices()])
                    trees[body.name]=cKDTree(vertices[body.name])
            distances,indices=trees[a.name].query(vertices[b.name]);index=int(np.argmin(distances));upper=float(distances[index])
            key=tuple(sorted((a.name,b.name)))
            if upper<=.025:
                edge=dict(a=a.name,b=b.name,distance_upper_bound_mm=upper,method='native_vertex_pair',points_mm=[vertices[a.name][indices[index]].tolist(),vertices[b.name][index].tolist()])
                proven[key]=edge;edges.append(edge);weight=0.
            else:weight=1.+min(upper,100.)/10000.
            graph[a.name][b.name]=weight;graph[b.name][a.name]=weight
        # Acceptance needs a verified path for each repaired support. Explore
        # candidate paths lazily instead of testing unrelated same-frame pairs.
        # Bounds propose edges; only a native point pair or actual solid
        # distance can certify an edge. Rejected edges are removed entirely.
        exact_checks=0;reached=set()
        for target in sorted(expected):
            while True:
                queue=[(0.,n) for n in anchors];heapq.heapify(queue);cost={n:0. for n in anchors};previous={}
                while queue:
                    d,n=heapq.heappop(queue)
                    if d!=cost[n]:continue
                    if n==target:break
                    for peer,w in graph[n].items():
                        nd=d+w
                        if nd<cost.get(peer,float('inf')):
                            cost[peer]=nd;previous[peer]=n;heapq.heappush(queue,(nd,peer))
                if target not in cost:break
                path=[];n=target
                while n not in anchors:
                    peer=previous[n];path.append((n,peer));n=peer
                pending=[(a,b) for a,b in path if tuple(sorted((a,b))) not in proven]
                if not pending:reached.add(target);break
                a,b=pending[0];distance=solids[a].distance_to(solids[b]);exact_checks+=1
                print('ATTACHMENT EDGE',frame,a,b,distance,flush=True)
                if distance<=.025:
                    edge=dict(a=a,b=b,distance_mm=distance,method='native_single_solid_distance');proven[tuple(sorted((a,b)))]=edge;edges.append(edge)
                    graph[a][b]=graph[b][a]=0.
                else:del graph[a][b];del graph[b][a]
        missing=sorted(expected-reached)
        row=dict(frame=frame,anchors=sorted(anchors),repaired_supports=sorted(expected),unattached=missing,contact_edges=edges,exact_distance_checks=exact_checks,pass_=not missing)
        rows.append(row);print('ATTACHMENTS',frame,'missing',missing,flush=True)
    changed=[p for p,h in inputs.items() if sha(p)!=h]
    report=dict(scope=__doc__,input_sha256=inputs,rows=rows,contact_tolerance_mm=.025,changed_during_audit=changed,complete=not changed,pass_=not changed and all(r['pass_'] for r in rows))
    report['pass']=report.pop('pass_');(HERE/'repaired_attachment_gate.json').write_text(json.dumps(report,indent=2)+'\n');assert report['pass']
if __name__=='__main__':main()
