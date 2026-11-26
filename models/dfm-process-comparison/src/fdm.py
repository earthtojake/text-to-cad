
from bd_materials import FinishedMaterial, plastics
from threejs_materials import PbrProperties

from cad import xbf
from lib.tray_geometry import tray


@xbf
def fdm():
    part = tray("fdm")
    # printed upright: PLA (README)
    part.material = FinishedMaterial(
        plastics.pla().material,
        pbr=PbrProperties.create('Polylactic acid, the common FDM filament', color='#ededebff', metalness=0.0,
            roughness=0.45),
    )
    return part


if __name__ == "__main__":
    fdm()
