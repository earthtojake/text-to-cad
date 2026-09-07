"""Macro review of the five driven D-bore tendon pulley radii, in mm."""
from cadgen import build123d as bd, step
from lib.pulley import make_pulley


@step(out="../../STEP/anthropomorphic_hand/pulley_review.step",
      mesh_tolerance=0.0008, mesh_angular_tolerance=0.008)
def pulley_review():
    children = []
    for radius, x in zip((3.5, 4.5, 5.5, 7.0, 11.0), (-40, -29, -16, 0, 22)):
        wheel = make_pulley(pitch_radius=radius, bore_radius=3.03 if radius == 11 else 1.03,
                            label=f"turned_tendon_pulley_R{str(radius).replace('.', '_')}")
        children.append(bd.Pos(x, 0, 0) * wheel)
    return bd.Compound(label="turned_tendon_pulley_family", children=children)


if __name__ == "__main__":
    pulley_review()
