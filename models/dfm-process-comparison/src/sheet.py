from cadgen import materials, model
from lib.tray_geometry import tray


@model
def sheet():
    part = tray("sheet")
    # 5052-H32 sheet (README): the catalogue's generic aluminium
    part.material = materials.aluminium
    return part


if __name__ == "__main__":
    sheet()
