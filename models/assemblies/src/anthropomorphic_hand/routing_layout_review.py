"""Complete48 routed-tendon integration study; final acceptance remains separate."""
from cadgen import step
from lib.assembly import integration_bodies,Body,compound
from lib.layout import TENDONS
from lib.forearm_routing import forearm_route
from lib.transport_guide import make_tendon
from lib.bowden_guide import make_bowden_body
from lib.finish import finish
from lib.neutral_routes import NEUTRAL_ROUTES


@step(out='../../STEP/anthropomorphic_hand/routing_layout_review.step')
def routing_layout_review():
    # Explicitly use the strict-valid baseline main palm while its final
    # surface revision is being completed. This is an integration study.
    bodies=integration_bodies(palm_baseline=True)
    for route,tendon in zip(NEUTRAL_ROUTES,TENDONS):
        assert route['name']==tendon['name']
        rope=finish(make_tendon(route['path'],route['name']),
                    'tendon_flex' if tendon['sign']>0 else 'tendon_extend',route['name'])
        bodies.append(Body(rope,'variable',tendon['joint'].split('_')[0],'tendon'))
        for group in route['groups']:
            if group.get('guide') not in ('snug_reaction_liner','fixed_curved_guide','compliant_wrist_guide','open_saddle'):continue
            liner=make_bowden_body(group['path'],group['label'],liner=True)
            bodies.append(Body(liner,'variable',tendon['joint'].split('_')[0],'guide'))
    return compound(bodies,'complete_tendon_routing_integration_study')


if __name__=='__main__':routing_layout_review()
