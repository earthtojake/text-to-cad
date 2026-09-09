"""Minimum end retraction certificate before ferrule/resin separation."""
import sys,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[4]
sys.path.insert(0,str(ROOT/'models/assemblies/src/anthropomorphic_hand'))
from lib.drive_terminal import *
from lib.capstan import sweep_round,make_terminal_ferrule
from lib.capstan_path import full_groove_path,prefix_length,path_length
rows=[]
for radius in (3.5,4.5,5.5,7.,11.):
 rope=arc_tube(radius,.30,-2.,-.85,-60.,-1)
 bond=make_driven_bond_line(radius);ferrule=make_driven_ferrule(radius)
 rows.append({'family':radius,'retraction_mm':.85,'bond_distance':rope.distance_to(bond),
              'rope_bond_overlap':(rope&bond).volume,'rope_ferrule_overlap':(rope&ferrule).volume})
first=full_groove_path()[0];length=path_length([first]);reverse={'kind':'bezier','points':list(reversed(first['points']))}
trimmed=prefix_length([reverse],length-.85)[0];trimmed['points']=list(reversed(trimmed['points']))
rope=sweep_round([trimmed],.30);bond=make_capstan_bond_line();ferrule=make_terminal_ferrule()
rows.append({'family':'capstan','retraction_mm':.85,'bond_distance':rope.distance_to(bond),
              'rope_bond_overlap':(rope&bond).volume,'rope_ferrule_overlap':(rope&ferrule).volume})
report={'ok':all(r['bond_distance']>.04 and r['rope_bond_overlap']<1e-7 and r['rope_ferrule_overlap']<1e-7 for r in rows),
 'checks':rows,'per_route':tendon_end_release_contract()}
Path(__file__).with_suffix('.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({'ok':report['ok'],'checks':rows}),flush=True)
assert report['ok']
