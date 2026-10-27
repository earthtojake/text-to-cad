
from bd_materials import FinishedMaterial, plastics
from threejs_materials import PbrProperties

from cadgen import model
from lib.tray_geometry import tray


@model
def baseline():
    part = tray("baseline")
    # the thin-wall FDM starting point: PLA (README)
    part.material = FinishedMaterial(
        plastics.pla().material,
        pbr=PbrProperties.create('Polylactic acid, the common FDM filament', color='#ededebff', metalness=0.0,
            roughness=0.45),
    )
    return part


if __name__ == "__main__":
    baseline()
