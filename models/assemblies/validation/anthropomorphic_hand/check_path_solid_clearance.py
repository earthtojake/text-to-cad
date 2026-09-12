"""Exercise the separation proof on clear, crossing, tangent and contained paths."""
import json
from pathlib import Path
from cadgen import build123d as bd
from path_solid_clearance import boundary_separation

box = bd.Box(2, 2, 2)
cases = [
    ('clear', (-3, 2, 0), (3, 2, 0), .3, True),
    ('tube_overlaps', (-3, 1.2, 0), (3, 1.2, 0), .3, False),
    ('crosses_solid', (-3, 0, 0), (3, 0, 0), .3, False),
    ('starts_inside', (0, 0, 0), (3, 0, 0), .3, False),
    ('fully_contained', (-.5, 0, 0), (.5, 0, 0), .3, False),
    ('tangent', (-3, 1, 0), (3, 1, 0), .3, False),
]
rows = []
for name, start, end, radius, expected in cases:
    wire = bd.Wire([bd.Edge.make_line(start, end)])
    proof = boundary_separation(wire, box, radius)
    assert proof['proven_separated'] == expected, (name, proof)
    rows.append({'case': name, 'expected_separated': expected, **proof})
report = {'pass': True, 'cases': rows}
Path(__file__).with_suffix('.json').write_text(json.dumps(report, indent=2)+'\n')
print('PASS', len(rows), 'boundary separation cases')
