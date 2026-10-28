"""Write the manual rendering corpus to an explicitly selected ignored folder."""
import argparse
from pathlib import Path

from cadgen import export
from source import machined_bearing_housing, painted_pressure_regulator, glass_sample_vessel, mixed_material_instrument


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    for create in [machined_bearing_housing, painted_pressure_regulator, glass_sample_vessel, mixed_material_instrument]:
        doc = create()
        export(doc, args.out / f"{create.__name__}.glb")
