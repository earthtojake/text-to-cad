"""SpaceX Mechazilla + Starship/Super Heavy - full launch system assembly.

Entry generator for the complete stack on the pad. All geometry lives in the
shared helper `starship_mechazilla_parts.py`; this entry composes the whole
scene and declares the animation sidecar. The individual major components are
also available as their own entries in this folder:

- `starship.step.py`       - Starship upper stage (exploded interior reveal)
- `super_heavy.step.py`    - Super Heavy booster (exploded interior reveal)
- `mechazilla_tower.step.py` - launch tower + carriage + chopstick + QD arms
                               (chopstick catch/close animation)
- `launch_mount.step.py`   - orbital launch mount (exploded pad hardware)

Each component entry imports the same helper, so its geometry is identical to
its counterpart inside this assembly. See the helper module docstring for the
coordinate convention and the ref-contract notes the sidecars rely on.
"""

import starship_mechazilla_parts as smz


def gen_step():
    return {
        "shape": smz.build_scene(),
        "params": "starship_mechazilla.params.js",
    }
