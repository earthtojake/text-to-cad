"""The braided-surface study: every cord held on its neutral route, braided.

The review assemblies carry no joint choreography. What they show is the cord
SURFACE: each of the 48 tendons is a smooth swept tube in the STEP, and this
clip lays the braid over it in place. The rope is "deformed" from its neutral
centerline onto the same centerline, so nothing moves and only the finish
changes. Those centerlines are ``lib.neutral_routes`` -- the very paths the
assemblies sweep the tendons along -- so the braid always sits on the geometry
it is drawn over.

A ``max_segment_length`` longer than any cord asks for no longitudinal
refinement: nothing bends, so there is nothing for extra vertices to follow.
"""
import cadgen
from lib.layout import TENDONS
from lib.neutral_routes import NEUTRAL_ROUTES

BRAID = {'pitch': .8, 'depth': .022, 'strands': 8}


def neutral_ropes():
    """(target, centerline) per tendon: its neutral route, its cross-section
    frame seeded along +X or -X by the tendon's sign."""
    ropes = []
    for route, tendon in zip(NEUTRAL_ROUTES, TENDONS):
        assert route['name'] == tendon['name']
        ropes.append((f"#{route['name']}", {'normal': [tendon['sign'], 0, 0], 'segments': route['path']}))
    return ropes


def braided_presentation():
    """The `animation=` of a review assembly that carries all 48 neutral cords."""
    ropes = neutral_ropes()

    def presentation(t, m):
        for target, rest in ropes:
            m.get(target).deform_tube(rest=rest, path=rest, max_segment_length=1000000, braid=BRAID)

    return {'presentation': cadgen.clip(presentation, duration=1, loop=False, label='Braided surface study')}
