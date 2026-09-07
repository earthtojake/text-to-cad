"""Universal-joint guide local geometry gate; no hand hardware exemption."""
import json
from pathlib import Path
import numpy as np
from scipy.spatial import cKDTree
from lib.bowden_universal import bowden_universal,SIX_LANES,LINER_OUTER_RADIUS
from lib.bowden_transport import cubic_point
from check_bowden_transport import metrics


def cloud(route):
    points=[];bound=0
    for segment in route['path']:
        c=np.array(segment['points']);steps=1000
        # Derivative lies in convex hull of3 delta controlpoints.
        bound=max(bound,3*np.linalg.norm(np.diff(c,axis=0),axis=1).max()/steps)
        points.extend(cubic_point(c,t) for t in np.linspace(0,1,steps+1))
    return np.array(points),float(bound)


if __name__=='__main__':
    flex=sorted(set(list(np.arange(-25,111,10))+list(np.linspace(-25,110,51))+[110]))
    yaw=sorted(set(list(np.arange(-20,21,10))+list(np.linspace(-20,20,51))))
    poses=sorted(set([(float(q),0.) for q in flex]+[(0.,float(q)) for q in yaw]+
                     [(f,y) for f in [-25.,30.,60.,90.,110.] for y in [-20.,20.]]))
    rows=[];control_samples=[];worst_radius=999.;worst_gap=999.;maxlengtherror=0.;failed=[]
    low=np.ones(3)*np.inf;high=-low.copy()
    for flex_deg,yaw_deg in poses:
        routes=[];clouds=[];spacings=[]
        for lane in SIX_LANES:
            route=bowden_universal(flex_deg,yaw_deg,lane)
            route_metrics=[metrics(s['points']) for s in route['path']]
            rmin=min(m['minimum_radius'] for m in route_metrics)
            err=abs(sum(m['length'] for m in route_metrics)-28.5)
            worst_radius=min(worst_radius,rmin);maxlengtherror=max(maxlengtherror,err)
            for m in route_metrics:low=np.minimum(low,m['minimum']);high=np.maximum(high,m['maximum'])
            routes.append(route);cl,sp=cloud(route);clouds.append(cl);spacings.append(sp)
            control_samples.append({'flex':flex_deg,'yaw':yaw_deg,'lane':lane,'parameters':route['parameters']})
            if rmin<3.5 or err>1e-8:failed.append({'pose':[flex_deg,yaw_deg],'lane':lane,'radius':rmin,'length_error':err})
        gap=999.
        for i in range(len(routes)):
            tree=cKDTree(clouds[i])
            for j in range(i+1,len(routes)):
                distance=float(tree.query(clouds[j],workers=1)[0].min())-(spacings[i]+spacings[j])/2
                gap=min(gap,distance-2*LINER_OUTER_RADIUS)
        worst_gap=min(worst_gap,gap)
        rows.append({'flex_deg':flex_deg,'yaw_deg':yaw_deg,'liner_surface_gap_lower_bound_mm':gap})
        if gap<0:failed.append({'pose':[flex_deg,yaw_deg],'guide_gap':gap})
    result={'samples':len(poses),'lanes':list(SIX_LANES),'minimum_radius_mm':worst_radius,
            'maximum_length_error_mm':maxlengtherror,'minimum_liner_surface_gap_lower_bound_mm':worst_gap,
            'centerline_envelope':{'minimum':low.tolist(),'maximum':high.tolist()},
            'failed':failed,'rows':rows,'control_samples':control_samples,
            'limitations':'Local guides and full-length shape only. Whole-hand hardware and intermediate unsampled parameter poses need their own gate.'}
    Path(__file__).with_name('bowden_universal_report.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ['rows','control_samples']},indent=2))
    if failed:raise SystemExit(1)
