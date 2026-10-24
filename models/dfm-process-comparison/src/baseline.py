from cadgen import materials, model
from lib.tray_geometry import tray


@model
def baseline():
    part = tray("baseline")
    # the thin-wall FDM starting point: PLA (README)
    part.material = materials.pla
    return part


if __name__ == "__main__":
    baseline()
