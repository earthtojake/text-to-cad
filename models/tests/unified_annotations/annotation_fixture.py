from cadgen import build123d as bd, step, label_shape, srgb

MATERIALS = {
    "definitions": {
        "steel": {"name": "Brushed steel", "roughness": 0.32, "metalness": 0.8},
        "paint": {"name": "Blue paint", "baseColor": "#2469AC", "roughness": 0.42, "opacity": 0.5},
    },
    "assignments": [
        {"targets": ["#base", "#shaft"], "material": "steel"},
        {"targets": ["#arm"], "material": "paint"},
    ],
}
KINEMATICS = {
    "mates": [{"name": "swing", "kind": "revolute", "parent": "#base", "child": "#arm",
               "axis": {"origin": [0,0,10], "dir": [0,0,1]}, "limits": [-80,80]}],
    "poses": {"open": {"swing": 45}},
}
ANIMATION = r"""export const clips = { demo: {
    label: "Turn shaft", duration: 4, loop: true,
    update(t, m) { m.get("shaft").translate([0,0,8*Math.sin(Math.PI*t/2)]); }
}};"""

@step(materials=MATERIALS, kinematics=KINEMATICS, animation=ANIMATION)
def annotation_fixture():
    base = label_shape(bd.Pos(0,0,3)*bd.Box(72,52,6), "base")
    shaft = label_shape(bd.Pos(0,0,18)*bd.Cylinder(5,24), "shaft")
    arm = label_shape(bd.Pos(18,0,12)*bd.Box(44,12,8), "arm")
    arm.color = srgb("#37966F", 0.6)
    pins = [label_shape(bd.Pos(-27+18*x, y,9)*bd.Cylinder(2,6), f"pin_{x}_{y}")
            for x in range(4) for y in (-18,18)]
    return bd.Compound(children=[base, shaft, arm, *pins])

if __name__ == "__main__":
    annotation_fixture()
