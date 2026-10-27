"""Versioned conversions of an already-loaded XCAF document, without rebuilding geometry.

Only xbf/8 -> xbf/9 is supported. Original physical attributes and NamedData remain
on their labels; each distinct resolved look gets a native payload on a copied
physical label. Shape/face/component visual references, geometry and the original
build closure are untouched. The caller owns any eventual file write.
"""

from __future__ import annotations

import json
import math
from dataclasses import MISSING, fields
from typing import Any

MIGRATION_GUID = "7406c53e-8344-4cf2-8b65-6f8708871215"


class DocumentCompatibilityError(ValueError):
    """A document whose declared format cannot be safely read or converted."""


def provenance(doc: Any) -> dict[str, Any] | None:
    """The separate migration record; the original build closure is never changed."""
    from cadgen.engine import document

    text = document._label_text(doc.Main(), MIGRATION_GUID)
    return None if text is None else json.loads(text)


def set_origin(doc: Any, origin: dict[str, Any]) -> None:
    """Record the first known export origin, without guessing an unknown closure base."""
    record = provenance(doc)
    if record is None or "origin" in record:
        return
    from OCP.Standard import Standard_GUID
    from OCP.TCollection import TCollection_AsciiString
    from OCP.TDataStd import TDataStd_AsciiString

    record["origin"] = origin
    text = json.dumps(record, sort_keys=True, separators=(",", ":"), allow_nan=False)
    TDataStd_AsciiString.Set_s(doc.Main(), Standard_GUID(MIGRATION_GUID), TCollection_AsciiString(text))


def _extra(label: Any) -> dict[str, Any]:
    """Read the known xbf/8 scalar fields without removing any original metadata."""
    from OCP.TCollection import TCollection_ExtendedString
    from OCP.TDataStd import TDataStd_NamedData
    from cadgen.engine import document

    data = TDataStd_NamedData()
    if not document._find(label, data, TDataStd_NamedData.GetID_s()):
        return {}
    result: dict[str, Any] = {}
    for name in ("family", "standard", "source"):
        key = TCollection_ExtendedString(name)
        if data.HasString(key):
            result[name] = data.GetString(key).ToExtString()
    for name in ("young_modulus", "poisson_ratio", "yield_strength", "ultimate_strength",
                 "thermal_expansion", "thermal_conductivity", "specific_heat", "anisotropy",
                 "anisotropy_rotation", "transmission", "transmission_depth", "coat",
                 "coat_roughness", "emissive_strength"):
        key = TCollection_ExtendedString(name)
        if data.HasReal(key):
            result[name] = data.GetReal(key)
    key = TCollection_ExtendedString("transmission_color")
    if data.HasArrayOfReals(key):
        array = data.GetArrayOfReals(key)
        result["transmission_color"] = [array.Value(i) for i in range(array.Lower(), array.Upper() + 1)]
    return result


def _physical(name: str, density: float | None, extra: dict[str, Any]) -> Any:
    """Use the values in the file, never a catalogue's replacement for its material."""
    from bd_materials import metals, plastics, glass
    from bd_materials.core import Range, SolidMaterial, PolymerMaterial

    family = extra.get("family")
    kind = {"metal": metals.MetalMaterial, "plastic": plastics.PlasticMaterial,
            "elastomer": plastics.PlasticMaterial, "glass": glass.GlassMaterial}.get(family, SolidMaterial)
    # A generic legacy material could carry yield strength regardless of family.
    # PolymerMaterial is a generic native range table covering all old solid fields.
    if extra.get("yield_strength") is not None and "yield_strength" not in {f.name for f in fields(kind)}:
        kind = PolymerMaterial
    values: dict[str, Any] = {}
    for field in fields(kind):
        if field.default is not MISSING:
            values[field.name] = field.default
        else:
            values[field.name] = "" if field.name == "hardness_scale" else None
    values.update(name=name, density=density, family=family,
                  transparent=bool(extra.get("transmission", 0.0)))
    for old, new, divisor in (("young_modulus", "modulus_of_elasticity", 1e9),
                            ("poisson_ratio", "poisson_ratio", 1.0),
                            ("yield_strength", "yield_strength", 1e6),
                            ("ultimate_strength", "tensile_strength", 1e6),
                            ("thermal_expansion", "thermal_expansion", 1.0),
                            ("thermal_conductivity", "thermal_conductivity", 1.0),
                            ("specific_heat", "specific_heat_capacity", 1.0)):
        if extra.get(old) is not None:
            if not math.isfinite(extra[old]):
                raise ValueError(f"legacy material {old} is not finite")
            value = extra[old] / divisor
            values[new] = Range(value, value)
    return kind(**values)


def _native(name: str, density: float | None, extra: dict[str, Any], rgba: tuple,
            visual: dict[str, Any]) -> Any:
    from bd_materials import FinishedMaterial
    from threejs_materials import PbrProperties
    from cadgen.engine.colors import linear_to_srgb

    values = {"color": [linear_to_srgb(c) for c in rgba[:3]], "opacity": rgba[3],
              "metalness": visual.get("metalness", 0.0), "roughness": visual.get("roughness", 0.5),
              "ior": visual.get("ior", 1.5), "emissive": list(visual.get("emissive", (0.0, 0.0, 0.0))),
              "anisotropy": extra.get("anisotropy", 0.0),
              "anisotropyRotation": extra.get("anisotropy_rotation", 0.0),
              "transmission": extra.get("transmission", 0.0), "clearcoat": extra.get("coat", 0.0),
              "clearcoatRoughness": extra.get("coat_roughness", 0.0),
              "emissiveIntensity": extra.get("emissive_strength", 1.0)}
    for old, new in (("transmission_color", "attenuationColor"), ("transmission_depth", "attenuationDistance")):
        if extra.get(old) is not None:
            values[new] = extra[old]
    pbr = PbrProperties.from_dict({"id": name, "name": name, "source": "xbf/8",
                                   "url": "", "license": "", "values": values, "textures": {}})
    return FinishedMaterial(_physical(name, density, extra), pbr=pbr)


def _look(label: Any) -> tuple[tuple, dict[str, Any], str]:
    """The resolved linear colour and standard PBR factors on one assigned label."""
    from OCP.Quantity import Quantity_ColorRGBA
    from OCP.XCAFDoc import XCAFDoc_ColorGen, XCAFDoc_ColorSurf, XCAFDoc_ColorTool, XCAFDoc_VisMaterialTool
    from cadgen.engine import document

    visual = XCAFDoc_VisMaterialTool.GetShapeMaterial_s(label)
    own = None
    color = Quantity_ColorRGBA()
    for kind in (XCAFDoc_ColorSurf, XCAFDoc_ColorGen):
        if XCAFDoc_ColorTool.GetColor_s(label, kind, color):
            rgb = color.GetRGB()
            own = (rgb.Red(), rgb.Green(), rgb.Blue(), color.Alpha())
            break
    rgba = own or document.DEFAULT_COLOR
    name = ""
    values: dict[str, Any] = {}
    if visual is not None and visual.HasPbrMaterial():
        pbr = visual.PbrMaterial()
        base = pbr.BaseColor
        rgb = base.GetRGB()
        # Keep the standard label colour where it overrides the visual material.
        rgba = own or (rgb.Red(), rgb.Green(), rgb.Blue(), base.Alpha())
        glow = visual.ConvertToCommonMaterial().EmissiveColor
        values = {"metalness": pbr.Metallic, "roughness": pbr.Roughness,
                  "ior": pbr.RefractionIndex, "emissive": (glow.Red(), glow.Green(), glow.Blue())}
        raw = visual.RawName()
        name = raw.ToCString() if raw is not None else ""
    return tuple(rgba), values, name


def _xbf8(doc: Any) -> int:
    """Prepare every conversion before modifying any label; the caller wraps the writes."""
    from OCP.TCollection import TCollection_HAsciiString
    from OCP.TDataStd import TDataStd_NamedData, TDataStd_TreeNode
    from OCP.TDF import TDF_ChildIterator, TDF_RelocationTable
    from OCP.XCAFDoc import XCAFDoc, XCAFDoc_DocumentTool, XCAFDoc_Material, XCAFDoc_VisMaterialTool
    from OCP.collections import Sequence_TDF_Label
    from cadgen.engine import document

    tool = XCAFDoc_DocumentTool.MaterialTool_s(doc.Main())
    definitions = Sequence_TDF_Label()
    tool.GetMaterialLabels(definitions)
    originals: dict[str, tuple[Any, Any, dict]] = {}
    for at in range(1, definitions.Length() + 1):
        label = definitions.Value(at)
        physical = XCAFDoc_Material()
        if document._find(label, physical, XCAFDoc_Material.GetID_s()):
            originals[document._entry(label)] = (label, physical, _extra(label))
    plans: dict[tuple, tuple[Any, Any, list]] = {}
    first: dict[str, Any] = {}
    iterator = TDF_ChildIterator(doc.Main(), True)
    while iterator.More():
        label = iterator.Value()
        iterator.Next()
        node = TDataStd_TreeNode()
        source = None
        entry = ""
        if document._find(label, node, XCAFDoc.MaterialRefGUID_s()) and node.HasFather():
            entry = document._entry(node.Father().Label())
            source = originals.get(entry)
            if source is None:
                raise ValueError(f"material reference {entry} has no physical definition")
        visual = XCAFDoc_VisMaterialTool.GetShapeMaterial_s(label)
        if source is None and visual is None:
            continue
        rgba, look, visual_name = _look(label)
        physical = source[1] if source is not None else None
        name = physical.GetName().ToCString() if physical is not None and physical.GetName() is not None else visual_name
        density = (physical.GetDensity() * 1000.0 or None) if physical is not None else None
        material = _native(name or "material", density, source[2] if source is not None else {}, rgba, look)
        key = (entry, document.material_key(material))
        if key not in plans:
            plans[key] = (source, material, [])
        plans[key][2].append(label)
        first.setdefault(entry, material)
    # Even an unassigned physical table entry retains its original values.
    for entry, (label, physical, extra) in originals.items():
        if entry not in first:
            name = physical.GetName().ToCString() if physical.GetName() is not None else "material"
            first[entry] = _native(name, physical.GetDensity() * 1000.0 or None, extra, document.DEFAULT_COLOR, {})
    # material_key validates strict JSON, including finite numbers, before writes begin.
    for material in first.values():
        document.material_key(material)
    for entry, (label, _physical_attr, _extra_values) in originals.items():
        document._write_extra(label, first[entry])
    for source, material, labels in plans.values():
        if source is not None:
            original, physical, _ = source
            made = tool.AddMaterial(physical.GetName(), physical.GetDescription(), physical.GetDensity(),
                                    physical.GetDensName(), physical.GetDensValType())
            data = TDataStd_NamedData()
            if document._find(original, data, TDataStd_NamedData.GetID_s()):
                data.Paste(TDataStd_NamedData.Set_s(made), TDF_RelocationTable())
            name = document._label_name(original)
            if name:
                document._name(made, name)
        else:
            made = tool.AddMaterial(TCollection_HAsciiString(material.name), TCollection_HAsciiString(""),
                                    0.0, TCollection_HAsciiString("density"),
                                    TCollection_HAsciiString("MASS_DENSITY_MEASURE"))
        document._write_extra(made, material)
        for label in labels:
            tool.SetMaterial(label, made)
    return len(plans) + sum(entry not in {key[0] for key in plans} for entry in originals)


_UPGRADES = {"xbf/8": ("xbf/9", _xbf8)}


def upgrade(doc: Any) -> dict[str, Any] | None:
    """Upgrade a supported document in memory, leaving build provenance unchanged.

    Current-format and non-cadgen documents are no-ops. Unsupported formats and
    incomplete conversions raise DocumentCompatibilityError. All label changes
    are one reversible OCCT command; only a successful conversion changes writer.
    """
    from cadgen.engine import document
    from cadgen.engine.previous import FORMAT

    writer = document._label_text(doc.Main(), document.WRITER_GUID)
    version = document.written_format(writer)
    if version is None or version == FORMAT:
        return None
    path = []
    seen = set()
    current = version
    while current != FORMAT:
        if current in seen:
            raise DocumentCompatibilityError(f"cyclic document migration at {current}")
        seen.add(current)
        step = _UPGRADES.get(current)
        if step is None:
            raise DocumentCompatibilityError(f"unsupported document format {version}; expected {FORMAT}")
        path.append((current, step[0], step[1]))
        current = step[0]
    from OCP.Standard import Standard_GUID
    from OCP.TCollection import TCollection_AsciiString
    from OCP.TDataStd import TDataStd_AsciiString

    if doc.HasOpenCommand():
        raise DocumentCompatibilityError("cannot migrate a document with an open command")
    prior = document._label_text(doc.Main(), MIGRATION_GUID)
    undo_limit = doc.GetUndoLimit()
    if undo_limit == 0:
        doc.SetUndoLimit(1)
    doc.NewCommand()
    try:
        steps = [{"from": old, "to": new, "materials": convert(doc)} for old, new, convert in path]
        current = document._writer()
        info = {"from": version, "to": FORMAT, "writer": writer, "by": current,
                "materials": sum(step["materials"] for step in steps)}
        if len(steps) > 1:
            info["steps"] = steps
        if prior is not None:
            info["previous"] = json.loads(prior)
            if "origin" in info["previous"]:
                info["origin"] = info["previous"]["origin"]
        TDataStd_AsciiString.Set_s(doc.Main(), Standard_GUID(MIGRATION_GUID),
                                 TCollection_AsciiString(json.dumps(info, sort_keys=True, separators=(",", ":"))))
        TDataStd_AsciiString.Set_s(doc.Main(), Standard_GUID(document.WRITER_GUID), TCollection_AsciiString(current))
        doc.CommitCommand()
        return info
    except Exception as error:
        doc.AbortCommand()
        raise DocumentCompatibilityError(f"cannot migrate {version} to {FORMAT}: {error}") from error
    finally:
        if undo_limit == 0:
            doc.SetUndoLimit(undo_limit)
