"""Freeze selected transport controls as tracked Python source plus review JSON."""
import json,pprint,sys
from pathlib import Path
source=Path(sys.argv[1])
rows=json.loads(source.read_text())
assert all(len(row['rows'])==6 for row in rows)
destination=Path('models/assemblies/src/anthropomorphic_hand/lib/thumb_cmc_atlas.py')
text='"""Frozen CMC transport control atlas; imported for CAD dependency tracking."""\nATLAS = '+pprint.pformat(rows,width=110,sort_dicts=False)+'\n'
for path,content in [(destination,text),(destination.with_suffix('.json'),json.dumps(rows,indent=2)+'\n')]:
 temp=path.with_suffix(path.suffix+'.tmp');temp.write_text(content);temp.replace(path)
print('Exported',len(rows),'CMC control packets from',source)
