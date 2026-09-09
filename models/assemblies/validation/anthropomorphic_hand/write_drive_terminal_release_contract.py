"""Write the numeric release contract, distinguishing certified and candidate paths."""
import sys,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[4]
sys.path.insert(0,str(ROOT/'models/assemblies/src/anthropomorphic_hand'))
from lib.drive_terminal import tendon_end_release_contract,drive_terminal_release_directions,capstan_bond_release_directions
report={'end_release':tendon_end_release_contract(),'driven_release_vectors':drive_terminal_release_directions(),
 'capstan_bond_initial_release_vectors':capstan_bond_release_directions(),
 'capstan_bond_standalone_release_certified':False,
 'capstan_bond_explode_policy':'Retain resin with bonded ferrule/capstan group; do not use the candidate vector as an independent full withdrawal.',
 'capstan_failed_candidate_report':'capstan_bond_release_check.json'}
Path(__file__).with_name('drive_terminal_release_contract.json').write_text(json.dumps(report,indent=2)+'\n')
