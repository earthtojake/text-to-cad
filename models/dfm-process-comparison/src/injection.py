from cadgen import materials, model
from lib.tray_geometry import tray


@model
def injection():
    part = tray("injection")
    # moulded: ABS, the common injection-moulding resin
    part.material = materials.abs_plastic
    return part


if __name__ == "__main__":
    injection()
