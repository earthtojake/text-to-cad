"""Exact neutral audit of frozen3151-body progress assembly's rigid bodies."""
from pathlib import Path
import sys,json
HERE=Path(__file__).parent
sys.path.insert(0,str(HERE.parents[1]/'src/anthropomorphic_hand'))
from lib.native_integration import frozen_bodies
from check_assembly_interference import audit
bodies=frozen_bodies(include_variable=False)
print('NATIVE RIGID',len(bodies),flush=True)
result=audit(bodies,HERE/'native_progress_neutral.json')
assert result['pass']
