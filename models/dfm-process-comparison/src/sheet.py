
from bd_materials import FinishedMaterial, metals
from threejs_materials import PbrProperties

from cadgen import model
from lib.tray_geometry import tray


@model
def sheet():
    part = tray("sheet")
    # 5052-H32 sheet (README): the catalogue's generic aluminium
    part.material = FinishedMaterial(
        metals.aluminum().material,
        pbr=PbrProperties.create('Aluminum 6061-T6', color='#f5f6f6ff', metalness=1.0, roughness=0.35,
            anisotropy=0.3),
    )
    return part


if __name__ == "__main__":
    sheet()
