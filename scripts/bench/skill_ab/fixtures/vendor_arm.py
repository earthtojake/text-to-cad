"""A two-joint arm as a vendor ships it: three solids in one assembly, placed as built, and no joints."""
import build123d as bd
from cad import model

MIN = (bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN)


@model
def vendor_arm():
    base = bd.Cylinder(30, 20, align=MIN)
    base.label = "RA2-BASE-01"
    upper = bd.Pos(0, 0, 20) * bd.Box(20, 20, 120, align=MIN)
    upper.label = "RA2-LINK-A"
    forearm = bd.Pos(0, 0, 140) * bd.Box(16, 16, 100, align=MIN)
    forearm.label = "RA2-LINK-B"
    return bd.Compound(children=[base, upper, forearm], label="RA2")


if __name__ == "__main__":
    vendor_arm()
