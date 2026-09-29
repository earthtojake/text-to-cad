"""A small hollow electronics enclosure: open bottom, corner screw bosses, one cable notch."""

from cadgen import implicit as im

# Outer envelope (mm); Z is up, the open bottom sits on z = 0.
LENGTH = 60.0  # along X (the long side)
WIDTH = 40.0  # along Y
HEIGHT = 25.0
WALL = 1.5

# Screw bosses for M3, on the inside corners, running floor to ceiling.
BOSS_OD = 5.5
BOSS_HOLE = 2.5
BOSS_HEIGHT = HEIGHT - WALL  # from the open bottom to the underside of the lid
HOLE_DEPTH = BOSS_HEIGHT - 3.0  # leave the lid intact above the screw
INNER_X = LENGTH / 2 - WALL  # inside face of the short walls
INNER_Y = WIDTH / 2 - WALL  # inside face of the long walls
BOSS_X = INNER_X - BOSS_OD / 2 + 0.25  # tucked into the corner, overlapping the walls slightly
BOSS_Y = INNER_Y - BOSS_OD / 2 + 0.25

# Cable notch in one long wall (y = -WIDTH/2), open at the bottom edge, rounded on top.
NOTCH_WIDTH = 12.0
NOTCH_DEPTH = 10.0  # how far up from the bottom edge the notch reaches


@im.part(out="../out/enclosure_sdf.glb", resolution=0.4)
def enclosure():
    # The body is built taller than the part so the cavity's floor lies below z = 0;
    # cutting everything below z = 0 then leaves an open bottom with full-height walls.
    outer = im.box((LENGTH, WIDTH, HEIGHT + WALL)).translate(0, 0, (HEIGHT - WALL) / 2).named("outer")
    cavity = (
        im.box((LENGTH - 2 * WALL, WIDTH - 2 * WALL, HEIGHT - WALL))
        .translate(0, 0, (HEIGHT - WALL) / 2)
        .named("cavity")
    )
    floor_cut = im.half_space((0, 0, -1), (0, 0, 0.0)).named("open_bottom")
    shell = outer - cavity - floor_cut

    boss = (
        im.cylinder(radius=BOSS_OD / 2, height=BOSS_HEIGHT)
        .translate(BOSS_X, BOSS_Y, BOSS_HEIGHT / 2)
        .mirror("x")
        .mirror("y")
        .named("bosses")
    )
    screw_hole = (
        im.cylinder(radius=BOSS_HOLE / 2, height=2 * HOLE_DEPTH)  # extends below z = 0, so it's open at the bottom
        .translate(BOSS_X, BOSS_Y, 0)
        .mirror("x")
        .mirror("y")
        .named("screw_holes")
    )

    # A rounded slot, drawn in XZ and pushed through the long wall along Y. It is
    # twice the notch depth tall and centred on z = 0, so it opens through the bottom edge.
    notch = (
        im.extrude(im.rect(NOTCH_WIDTH, 2 * NOTCH_DEPTH, radius=NOTCH_WIDTH / 2), 3 * WALL)
        .rotate(90, axis=(1, 0, 0))
        .translate(0, -WIDTH / 2, 0)
        .named("cable_notch")
    )

    return (shell | boss) - screw_hole - notch


if __name__ == "__main__":
    enclosure()
