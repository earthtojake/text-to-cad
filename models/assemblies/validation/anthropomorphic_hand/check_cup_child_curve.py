import sys,json
from pathlib import Path
HERE=Path(__file__).parent;sys.path.insert(0,str(HERE.parents[1]/'src/anthropomorphic_hand'))
from lib.cup_guide_mounts import make_cup_child_bank
parts=make_cup_child_bank();print([(p.label,p.volume,p.is_valid) for p,*_ in parts],flush=True)
