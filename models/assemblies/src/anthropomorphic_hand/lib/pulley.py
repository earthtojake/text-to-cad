"""Turned, dished tendon pulleys. Dimensions in mm; local rotary axis +Z.

The tendon centreline is the circle (pitch_radius, z=0). The exact circular
groove section is rope_radius + 0.05, leaving 0.05 radial seating clearance.
Outer diameter = 2 * (pitch_radius + 0.50), axial envelope = width.
Bore radius is the *finished clearance bore*, not a nominal shaft radius.
The default driven D bore clears a 2 mm D shaft by 0.03 radially, with its
torque flat on native +X at x=0.75. Set keyed=False for a round idler.
"""

from cadgen import build123d as bd, srgb


def make_pulley(pitch_radius=3.5, rope_radius=0.30, width=1.50,
                bore_radius=1.03, label="tendon_pulley", *, keyed=True,
                bore_flat=None):
    """One genuinely connected solid, with a toroidal U groove and dished web.

    Intended radius family: 3.5, 4.5, 5.5, 7.0, and wrist R11. Axles, bearings and retainers
    are separate assembly bodies. Upper/lower cheeks are symmetric so either
    side can be presented; no opaque shells conceal the tendon groove.
    """
    groove = rope_radius + 0.05
    half = width / 2
    flange_z = half - 0.10
    hub_r = bore_radius + 0.67
    web_z = 0.28
    if pitch_radius < hub_r + 1.50:
        raise ValueError("pulley pitch radius leaves insufficient dished web")
    if flange_z < groove + 0.25:
        raise ValueError("width must preserve the groove and rounded flange")
    if min(rope_radius, bore_radius) <= 0:
        raise ValueError("rope and bore radii must be positive")

    edges = []
    def point(rz):
        return (rz[0], 0, rz[1])
    def line(a, b):
        edges.append(bd.Edge.make_line(point(a), point(b)))
    def arc(a, through, b):
        edges.append(bd.Edge.make_three_point_arc(point(a), point(through), point(b)))
    def bezier(*p):
        edges.append(bd.Edge.make_bezier(*[point(v) for v in p]))

    # Upper half, from the axial bore to the rope groove. All external corners
    # are built as tangent curves in the lathe section, not post-fillet guesses.
    line((bore_radius, -half + .10), (bore_radius, half - .10))
    arc((bore_radius, half-.10), (bore_radius+.029289, half-.029289),
        (bore_radius+.10, half))
    line((bore_radius+.10, half), (hub_r-.10, half))
    bezier((hub_r-.10, half), (hub_r+.19, half),
           (hub_r+.05, web_z), (hub_r+.42, web_z))
    line((hub_r+.42, web_z), (pitch_radius-.85, web_z))
    bezier((pitch_radius-.85, web_z), (pitch_radius-.50, web_z),
           (pitch_radius-.43, flange_z), (pitch_radius-.10, flange_z))
    line((pitch_radius-.10, flange_z), (pitch_radius+.40, flange_z))
    arc((pitch_radius+.40, flange_z),
        (pitch_radius+.470711, flange_z-.029289),
        (pitch_radius+.50, flange_z-.10))
    bezier((pitch_radius+.50, flange_z-.10),
           (pitch_radius+.50, groove+.05),
           (pitch_radius+.24, groove), (pitch_radius, groove))

    # Exactly a semicircle, revolved into the working toroidal rope seat.
    arc((pitch_radius, groove), (pitch_radius-groove, 0),
        (pitch_radius, -groove))

    # Lower half reflects the same clean highlight surfaces.
    bezier((pitch_radius, -groove), (pitch_radius+.24, -groove),
           (pitch_radius+.50, -groove-.05),
           (pitch_radius+.50, -flange_z+.10))
    arc((pitch_radius+.50, -flange_z+.10),
        (pitch_radius+.470711, -flange_z+.029289),
        (pitch_radius+.40, -flange_z))
    line((pitch_radius+.40, -flange_z), (pitch_radius-.10, -flange_z))
    bezier((pitch_radius-.10, -flange_z),
           (pitch_radius-.43, -flange_z),
           (pitch_radius-.50, -web_z), (pitch_radius-.85, -web_z))
    line((pitch_radius-.85, -web_z), (hub_r+.42, -web_z))
    bezier((hub_r+.42, -web_z), (hub_r+.05, -web_z),
           (hub_r+.19, -half), (hub_r-.10, -half))
    line((hub_r-.10, -half), (bore_radius+.10, -half))
    arc((bore_radius+.10, -half),
        (bore_radius+.029289, -half+.029289),
        (bore_radius, -half+.10))
    section = bd.Face(bd.Wire(edges))
    wheel = bd.revolve(section, axis=bd.Axis.Z)
    if keyed:
        # The D cap is confined to the hub: the entire turned working profile,
        # including the rope seat and flange surfaces, is exactly unchanged.
        # A nominal journal is 0.03 smaller than the circular clearance bore.
        # The matching shaft flat has no angular lash at neutral; +X is always
        # the torque-flat normal. Wrist bore 3.03 therefore uses flat +2.25.
        flat = .75 * (bore_radius - .03) if bore_flat is None else bore_flat
        if not 0 < flat < bore_radius - .10:
            raise ValueError("D bore flat must lie inside the bore with lip clearance")
        cap_radius = bore_radius + .11
        cap_edges = []
        def cap_line(a, b):
            cap_edges.append(bd.Edge.make_line(point(a), point(b)))
        def cap_arc(a, middle, b):
            cap_edges.append(bd.Edge.make_three_point_arc(point(a), point(middle), point(b)))
        cap_line((flat, -half+.10), (flat, half-.10))
        cap_arc((flat, half-.10), (flat+.029289, half-.029289),
                (flat+.10, half))
        cap_line((flat+.10, half), (cap_radius+.10, half))
        cap_line((cap_radius+.10, half), (cap_radius+.10, -half))
        cap_line((cap_radius+.10, -half), (flat+.10, -half))
        cap_arc((flat+.10, -half), (flat+.029289, -half+.029289),
                (flat, -half+.10))
        cap_face = bd.Face(bd.Wire(cap_edges))
        cap_prism = bd.extrude(cap_face, amount=2*cap_radius, dir=(0, 1, 0))
        cap_prism = bd.Pos(0, -cap_radius, 0) * cap_prism
        cap = cap_prism & bd.Cylinder(cap_radius, width)
        wheel = wheel + cap
    wheel.label = label
    wheel.color = srgb("#B7C3CB")
    wheel.cad_material = {"metalness": .88, "roughness": .28}
    if len(wheel.solids()) != 1 or not wheel.is_valid or wheel.volume <= 0:
        raise ValueError(f"{label}: turned profile failed solid validation")
    return wheel
