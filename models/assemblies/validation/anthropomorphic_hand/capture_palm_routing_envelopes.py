"""Capture conservative primitive envelopes directly from palm frame datums."""
import json,hashlib,pprint
from pathlib import Path
from lib import palm_frame
palm_frame._rib=lambda points,radius=1.35:{'kind':'rib','points':points,'radius':radius}
palm_frame._eye=lambda center,radius=3.75,bore=2.53,thickness=2.,axis='z':{'kind':'cylinder','center':center,'radius':radius,'thickness':thickness,'axis':axis}
palm_frame._finish=lambda pieces,*args:pieces
source=Path(palm_frame.__file__)
packet={'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'fixed':palm_frame.make_palm_frame(),'moving':palm_frame.make_little_metacarpal()}
(source.parent/'palm_routing_envelopes.json').write_text(json.dumps(packet,indent=2)+'\n')
(source.parent/'palm_routing_envelopes_data.py').write_text('PALM_ENVELOPES = '+pprint.pformat(packet,sort_dicts=False,width=110)+'\n')
print(len(packet['fixed']),len(packet['moving']))
