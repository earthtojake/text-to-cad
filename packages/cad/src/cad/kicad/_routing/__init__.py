"""The router behind ``cad.kicad.route``: the plan's connections searched for and pulled tight, by the board's rules.

Nothing here imports KiPy or touches a file: ``cad.kicad._route`` hands it the open board's text and KiCad's rules,
and writes back the copper it answers. numpy and the standard library alone.

- ``shapes``: exact shapes (a point, a segment, a polygon or an arc grown by a radius) and their distances;
- ``board``: the board's copper, holes, keep-outs and outline as those shapes, read from its text;
- ``rules``: each net's class, the board's minimums, the custom rules kept the safe way;
- ``field``: the clearance fields on the grid, from which the search's free nodes are read;
- ``search``: A* over the grid, octolinear on each layer, vias between;
- ``tighten``: the exact checks and the pull-tight pass;
- ``plan``: one plan routed, entry by entry, in its order.
"""
