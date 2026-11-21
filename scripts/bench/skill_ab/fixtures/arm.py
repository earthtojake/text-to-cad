"""A two-joint arm: a base, an upper arm and a forearm."""
import build123d as bd
from cad import model
from cad.build123d import mechanism_state

MIN = (bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN)


@model
def arm():
    base = bd.Cylinder(30, 20, align=MIN)
    base.label = "base"
    upper = bd.Pos(0, 0, 20) * bd.Box(20, 20, 120, align=MIN)
    upper.label = "upper_arm"
    forearm = bd.Pos(0, 0, 140) * bd.Box(16, 16, 100, align=MIN)
    forearm.label = "forearm"

    shoulder = bd.Axis((0, 0, 20), (0, 1, 0))
    bd.RevoluteJoint("shoulder", base, axis=shoulder, angular_range=(-90, 90))
    bd.RigidJoint("shoulder", upper, bd.Plane(origin=shoulder.position, z_dir=shoulder.direction).location)
    base.joints["shoulder"].connect_to(upper.joints["shoulder"], angle=0)

    elbow = bd.Axis((0, 0, 140), (0, 1, 0))
    bd.RevoluteJoint("elbow", upper, axis=elbow, angular_range=(-120, 120))
    bd.RigidJoint("elbow", forearm, bd.Plane(origin=elbow.position, z_dir=elbow.direction).location)
    upper.joints["elbow"].connect_to(forearm.joints["elbow"], angle=0)

    assembly = bd.Compound(children=[base, upper, forearm], label="arm")
    mechanism_state(assembly, "home", shoulder=0, elbow=0)
    mechanism_state(assembly, "reach", shoulder=45, elbow=60)
    return assembly


if __name__ == "__main__":
    arm()
