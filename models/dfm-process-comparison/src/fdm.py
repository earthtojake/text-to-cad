from cadgen import materials, model
from lib.tray_geometry import tray


@model
def fdm():
    part = tray("fdm")
    # printed upright: PLA (README)
    part.material = materials.pla
    return part


if __name__ == "__main__":
    fdm()
