"""Complete48 routed-tendon integration study; final acceptance remains separate."""
from cadgen import step
from lib.assembly import integration_bodies,Body,compound
from lib.layout import TENDONS
from lib.forearm_routing import forearm_route
from lib.transport_guide import make_tendon
from lib.bowden_guide import make_bowden_body
from lib.finish import finish
from lib.neutral_routes import NEUTRAL_ROUTES


@step(out='../../STEP/anthropomorphic_hand/hand_progress_review.step')
def hand_progress_review():
    bodies=integration_bodies(palm_baseline=False)
    for route,tendon in zip(NEUTRAL_ROUTES,TENDONS):
        assert route['name']==tendon['name']
        rope=finish(make_tendon(route['path'],route['name']),
                    'tendon_flex' if tendon['sign']>0 else 'tendon_extend',route['name'])
        bodies.append(Body(rope,'variable',tendon['joint'].split('_')[0],'tendon'))
        for group in route['groups']:
            if group.get('guide') not in ('snug_reaction_liner','fixed_curved_guide','compliant_wrist_guide','open_saddle'):continue
            liner=make_bowden_body(group['path'],group['label'],liner=True)
            bodies.append(Body(liner,'variable',tendon['joint'].split('_')[0],'guide'))
    import json
    from pathlib import Path
    metadata=Path(__file__).resolve().parents[2]/'validation/anthropomorphic_hand/hand_progress_body_frames.json'
    metadata.write_text(json.dumps([{'name':b.name,'frame':b.frame,'system':b.system,'kind':b.kind} for b in bodies],indent=2)+'\n')
    return compound(bodies,'complete_tendon_routing_integration_study')


if __name__=='__main__':hand_progress_review()
