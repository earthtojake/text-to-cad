
from bd_materials import FinishedMaterial, plastics
from threejs_materials import PbrProperties

from cadgen import model
from lib.tray_geometry import tray


@model
def injection():
    part = tray("injection")
    # moulded: ABS, the common injection-moulding resin
    part.material = FinishedMaterial(
        plastics.abs_().material,
        pbr=PbrProperties.create('Acrylonitrile butadiene styrene, moulded or printed', color='#767679ff',
            metalness=0.0, roughness=0.55),
    )
    return part


if __name__ == "__main__":
    injection()
