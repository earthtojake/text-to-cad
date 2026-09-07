"""Protected axial stations for material removal; no model mutation."""
from pathlib import Path
import sys,json
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'src/anthropomorphic_hand'))
from lib.layout import FINGERS

def intervals(length,width,distal,role,finger):
    protected=[(-10.,4.4),(length-4.4,length+10.)]
    arches=[.56] if distal else ([.70] if (length,width) in {(45.,18.),(28.,15.),(26.,14.5),(33.,17.)} else [.32,.70])
    protected += [(length*f-.85,length*f+.85) for f in arches]
    if distal:protected += [(length*.71-1.65,length*.71+1.65)]
    elif role=='proximal':
        stations=[12.25,length-7]
        if finger!='thumb':stations += [length-12.25,length-15]
        protected += [(x-.8,x+.8) for x in stations]
    else:
        stations=[10 if finger=='little' else 12.25,length-7]
        protected += [(x-.8,x+.8) for x in stations]
    merged=[]
    for lo,hi in sorted(protected):
        if merged and lo<=merged[-1][1]:merged[-1][1]=max(hi,merged[-1][1])
        else:merged.append([lo,hi])
    windows=[(a[1],b[0]) for a,b in zip(merged,merged[1:]) if b[0]-a[1]>=2.5]
    return {'protected':merged,'windows':windows}
rows={}
for f in FINGERS:
 for i,role in enumerate(('proximal','middle','distal')):
    rows[f.name+'_'+role+'_frame']=intervals(f.lengths[i],f.widths[i],i==2,role,f.name)
for L,W,role in [(27,16,'proximal'),(21,13,'distal')]:rows['thumb_'+role+'_frame']=intervals(L,W,role=='distal',role,'thumb')
Path('models/assemblies/validation/anthropomorphic_hand/phalanx_sculpt_station_plan_r4.json').write_text(json.dumps(rows,indent=2))
for name,row in rows.items():print(name,row['windows'])
