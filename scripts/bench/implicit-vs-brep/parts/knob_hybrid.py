"""A showcase part: a revolved knob, hollowed, with a filleted grip pattern and a hex socket."""

from cadgen import implicit as im

GRIP_COUNT = 8


@im.part(out=["../out/knob_hybrid.glb", "../out/knob_hybrid.step"], resolution=0.25)
def knob():
    outline = im.polygon([(0, 0), (14, 0), (16, 4), (13, 18), (8, 22), (0, 22)])
    body = im.revolve(outline).named("body")
    grips = im.union(
        *[im.capsule((15, 0, 6), (11.5, 0, 20), 2.2).rotate(360 / GRIP_COUNT * i) for i in range(GRIP_COUNT)]
    ).named("grips")
    shaped = im.subtract(body, grips, round=1.2)
    socket = im.extrude(im.regular_polygon(6, 3.2), 12).translate(0, 0, 4).named("socket")
    hollow = shaped.shell(1.6) - im.half_space((0, 0, -1), (0, 0, 0.9)).named("opening")  # below the bottom plate: open
    return hollow - socket | (im.cylinder(5.5, 12, radius_edge=0.5).translate(0, 0, 8) - socket).named("boss")


if __name__ == "__main__":
    knob()
