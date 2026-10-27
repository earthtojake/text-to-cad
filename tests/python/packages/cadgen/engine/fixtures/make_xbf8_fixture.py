"""Regenerate the saved-format fixture with the published cadgen 0.8.0 environment.

This is a maintenance command, never imported or run by the test suite. The old
writer and old OCCT binary driver are the subject of this fixture: making these
bytes with the current engine would not test backwards reading.
"""
from __future__ import annotations

import hashlib
import importlib.metadata
import json
import platform
from pathlib import Path


def main() -> None:
    expected = {"cadgen": "0.8.0", "build123d": "0.11.1", "cadquery-ocp-novtk": "7.9.3.1.1"}
    versions = {name: importlib.metadata.version(name) for name in expected}
    if versions != expected:
        raise SystemExit(f"Run with the published old environment {expected}; found {versions}")

    import build123d as bd
    from cadgen import Material, paint
    from cadgen.engine import document, previous
    from cadgen.engine.colors import linear
    from OCP.TCollection import TCollection_ExtendedString
    from OCP.TDataStd import TDataStd_NamedData
    from OCP.XCAFDoc import XCAFDoc_DocumentTool, XCAFDoc_VisMaterialTool
    from OCP.TDF import TDF_LabelSequence

    folder = Path(__file__).resolve().parent
    path = folder / "xbf8_materials.xbf"
    physics = {
        "name": "Legacy test alloy", "density": 7850.0, "family": "metal",
        "standard": "TEST-ALLOY-8", "source": "fixture: measured coupon, old SI units",
        "description": "Saved alloy with independently authored visual finishes",
        "young_modulus": 210e9, "poisson_ratio": 0.29, "yield_strength": 355e6,
        "ultimate_strength": 610e6, "thermal_expansion": 12.3e-6,
        "thermal_conductivity": 42.5, "specific_heat": 470.0, "isotropic": False,
    }
    appearance = {
        "metallic": 0.3, "roughness": 0.6, "ior": 1.45, "anisotropy": 0.4,
        "anisotropy_rotation": 0.7, "transmission": 0.5, "transmission_color": "#bed4e8",
        "transmission_depth": 0.02, "coat": 0.6, "coat_roughness": 0.15,
        "emissive": "#28405a", "emissive_strength": 2.5,
    }
    material = Material(**physics, **appearance)
    left = bd.Box(2, 3, 4)
    left.label = "block"
    left.color = "#80a0c0cc"
    left.material = material
    paint(left, left.faces().sort_by(bd.Axis.Z)[-1], material)
    right = left.moved(bd.Location((10, 0, 0)))
    right.label = "block_copy"
    right.color = "#4488cc99"
    pin = bd.Pos(0, 6, 1) * bd.Cylinder(0.5, 2)
    pin.label = "pin"
    pin.color = "#c0804066"
    pin.material = material
    nested = bd.Compound(children=[left, pin], label="subassembly")
    shape = bd.Compound(children=[nested, right], label="legacy_kit")
    tree = document.collect(shape, "legacy_kit")
    for part in tree.parts:
        part.key = document.geometry_key(part.shape)
        part.names = {"faces": [f"{part.name}_face_{i}" for i in range(1, 7)],
                      "edges": [f"{part.name}_edge_1"], "vertices": [f"{part.name}_vertex_1"]}
        # A painted face can have a visual independent of its shared physical card.
        for ordinal in part.face_materials:
            part.face_colors[ordinal] = tuple(linear("#55aa7733"))
    # A fourth occurrence reuses the pin prototype, with its own placement and colour.
    pin_prototype = next(part for part in tree.parts if part.name == "pin")
    pin_prototype.color = None  # the two occurrences own their distinct colours
    tree.root.components.append(document.Component(pin_prototype, bd.Location((5, 6, 1)).wrapped,
                                                   "pin_instance", tuple(linear("#aadd6677"))))
    closure = {
        "schema": previous.SCHEMA,
        "engine": {"release": "cadgen 0.8.0", "format": previous.FORMAT, "digest": "old-writer-fixture"},
        "libs": {"build123d": versions["build123d"], "OCP": "7.9.3.1"},
        "platform": {"python": platform.python_version(), "system": platform.system(), "arch": platform.machine()},
        "source": {"kind": "script", "path": "../unavailable/legacy_model.py", "function": "legacy_kit"},
        "modules": [["../unavailable/legacy_model.py", "d" * 32]], "symbols": {},
        "inputs": [["read", "../unavailable/dimensions.json", "a" * 32]], "bodies": 1,
    }
    closure["key"] = previous.key(closure)
    tree.closure = previous.text(closure)
    doc = document.to_xcaf(tree)
    shapes = XCAFDoc_DocumentTool.ShapeTool_s(doc.Main())
    # Keep the old physical reference shared, while giving pin its own core PBR.
    # The released reader resolves these fields from XCAFDoc_VisMaterial, not NamedData.
    for label in (shapes.Label().FindChild(i, False) for i in range(1, len(tree.order) + 1)):
        if document._label_name(label) != "pin":
            continue
        visual = XCAFDoc_VisMaterialTool.GetShapeMaterial_s(label)
        pbr = visual.PbrMaterial()
        pbr.Metallic, pbr.Roughness, pbr.RefractionIndex = 0.75, 0.12, 1.62
        visual.SetPbrMaterial(pbr)
    definitions = TDF_LabelSequence()
    XCAFDoc_DocumentTool.MaterialTool_s(doc.Main()).GetMaterialLabels(definitions)
    assert definitions.Length() == 1
    data = TDataStd_NamedData.Set_s(definitions.Value(1))
    data.SetString(TCollection_ExtendedString("vendor_batch"), TCollection_ExtendedString("lot-17"))
    data.SetReal(TCollection_ExtendedString("vendor_scale"), 1.2345)
    data.SetInteger(TCollection_ExtendedString("custom_revision"), 7)
    document.save(doc, path, compare=False, tree=tree)
    loaded = document.Loaded(path)
    snapshot = loaded.structure()
    snapshot.pop("path", None)
    snapshot.pop("version", None)
    expected_record = {
        "generator": Path(__file__).name, "versions": versions,
        "python": platform.python_version(), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "bytes": path.stat().st_size, "writer": loaded.writer, "closure": loaded.closure,
        "physical": physics, "appearance": appearance, "structure": snapshot,
        "custom_metadata": {"vendor_batch": "lot-17", "vendor_scale": 1.2345, "custom_revision": 7},
        "total_volume": sum(bd.Compound(p.shape).volume for p in loaded.prototypes),
    }
    (folder / "xbf8_materials.json").write_text(json.dumps(expected_record, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {path.name}: {path.stat().st_size} bytes, {len(loaded.prototypes)} prototypes, "
          f"{len(loaded.instances)} instances, {loaded.writer}")


if __name__ == "__main__":
    main()
