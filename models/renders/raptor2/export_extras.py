"""Export IGES and OBJ sidecars for the Raptor 2 reconstruction package.

Educational, non-functional public-source reconstruction. Not suitable for
manufacture, propulsion, testing, or operational engineering.

STEP comes from `scripts/gen ... --write-step`; STL/GLB come from
`scripts/export ... --stl/--glb`. This helper adds the two formats that pipeline does not emit:

    PYTHONPATH=<repo>/packages/cadpy/src <venv-python> export_extras.py

- IGES: written from the same gen_step() geometry via the OCCT IGES writer.
- OBJ: converted from the native GLB sidecar via trimesh (preserves per-part
  meshes); requires the GLB to exist first.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

ENTRIES = ["raptor2", "raptor2_cutaway", "raptor2_exploded"]


def _load_entry(name: str):
    path = HERE / f"{name}.step.py"
    spec = importlib.util.spec_from_file_location(f"{name}.step", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _shape_of(envelope):
    return envelope["shape"] if isinstance(envelope, dict) else envelope


def export_iges(shape, path: Path) -> bool:
    from OCP.IGESControl import IGESControl_Controller, IGESControl_Writer
    from OCP.Interface import Interface_Static

    IGESControl_Controller.Init_s()
    Interface_Static.SetCVal_s("write.iges.unit", "MM")
    writer = IGESControl_Writer("MM", 0)
    writer.AddShape(shape.wrapped)
    writer.ComputeModel()
    return bool(writer.Write(str(path)))


def export_obj(glb_path: Path, obj_path: Path) -> bool:
    import trimesh

    scene = trimesh.load(str(glb_path))
    scene.export(str(obj_path))
    return obj_path.exists() and obj_path.stat().st_size > 0


def main() -> int:
    failures = []
    for name in ENTRIES:
        shape = _shape_of(_load_entry(name).gen_step())
        iges_path = HERE / f"{name}.iges"
        ok = export_iges(shape, iges_path)
        print(f"{name}.iges: {'ok' if ok else 'FAILED'} "
              f"({iges_path.stat().st_size // 1024} KiB)" if ok else f"{name}.iges: FAILED")
        if not ok:
            failures.append(iges_path.name)
        glb_path = HERE / f"{name}.glb"
        obj_path = HERE / f"{name}.obj"
        if glb_path.exists():
            ok = export_obj(glb_path, obj_path)
            print(f"{name}.obj: {'ok' if ok else 'FAILED'}")
            if not ok:
                failures.append(obj_path.name)
        else:
            print(f"{name}.obj: skipped ({glb_path.name} missing; run scripts/export --glb first)")
    if failures:
        print("FAILURES:", ", ".join(failures))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
