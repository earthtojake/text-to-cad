"""STEP rendering properties absent from the current OCCT STEP translator.

OCCT's STEP parser retains unsupported reflectance records as undefined entities.
This adapter follows only styled items and their transfer mappings, so geometric
entities are not traversed one by one through the Python bindings. The linear-RGB
metallic/specular approximation follows the Khronos specular-gloss conversion:
https://github.com/KhronosGroup/glTF/tree/main/extensions/2.0/Archived/KHR_materials_pbrSpecularGlossiness
"""
from __future__ import annotations

import io
import math
from typing import Any


def _styles(ws: Any) -> Any:
    from OCP.STEPConstruct import STEPConstruct_Styles
    styles = STEPConstruct_Styles(ws)
    styles.LoadStyles()
    return styles


def _surface(style: Any) -> Any:
    """Find the existing surface assignment, preserving any separate curve style."""
    for i in range(1, style.NbStyles() + 1):
        assignment = style.StylesValue(i)
        for j in range(1, assignment.NbStyles() + 1):
            usage = assignment.StylesValue(j).SurfaceStyleUsage()
            if usage:
                return assignment, j, usage
    return None


def _fill_colour(side: Any) -> Any:
    for i in range(1, side.NbStyles() + 1):
        fill = side.StylesValue(i).SurfaceStyleFillArea()
        if not fill:
            continue
        area = fill.FillArea()
        for j in range(1, area.NbFillStyles() + 1):
            color = area.FillStylesValue(j).FillAreaStyleColour()
            if color:
                return color.FillColour()
    return None


def _template(looks: list[tuple]) -> list[Any]:
    """Parse one small standards-compliant in-memory set of unsupported records."""
    from OCP.IFSelect import IFSelect_RetDone
    from OCP.STEPCAFControl import STEPCAFControl_Reader
    records = []
    for i, (ambient, diffuse, specular, exponent, rgb) in enumerate(looks):
        a, b = 2 * i + 1, 2 * i + 2
        records.append(f"#{a}=SURFACE_STYLE_REFLECTANCE_AMBIENT_DIFFUSE_SPECULAR({ambient:.12e},{diffuse:.12e},{specular:.12e},{exponent:.12e},#{b});")
        records.append(f"#{b}=COLOUR_RGB('',{rgb[0]:.12e},{rgb[1]:.12e},{rgb[2]:.12e});")
    text = ("ISO-10303-21;\nHEADER;\nFILE_DESCRIPTION((''),'2;1');\n"
            "FILE_NAME('','',(''),(''),'','','');\n"
            "FILE_SCHEMA(('AP242_MANAGED_MODEL_BASED_3D_ENGINEERING_MIM_LF'));\n"
            "ENDSEC;\nDATA;\n" + "\n".join(records) + "\nENDSEC;\nEND-ISO-10303-21;")
    reader = STEPCAFControl_Reader()
    if reader.ReadStream('appearance', io.BytesIO(text.encode('ascii'))) != IFSelect_RetDone:
        raise ValueError('could not construct STEP appearance records')
    model = reader.Reader().Model()
    return [model.Value(2 * i + 1) for i in range(len(looks))]


def write_visual_styles(writer: Any, doc: Any) -> bool:
    """Attach standard reflectance to styled products and material-painted faces."""
    from OCP.collections import Sequence_TDF_Label
    from OCP.STEPConstruct import STEPConstruct
    from OCP.TopAbs import TopAbs_COMPOUND, TopAbs_COMPSOLID, TopAbs_FACE, TopAbs_SOLID
    from OCP.TopExp import TopExp_Explorer
    from OCP.XCAFDoc import XCAFDoc_DocumentTool, XCAFDoc_ShapeTool, XCAFDoc_VisMaterialTool

    ws = writer.ChangeWriter().WS()
    styles = _styles(ws)
    by_item = {}
    for i in range(1, styles.NbStyles() + 1):
        style = styles.Style(i)
        if style.Item():
            by_item.setdefault(style.Item(), []).append(style)
    tool = XCAFDoc_DocumentTool.ShapeTool_s(doc.Main())
    labels = Sequence_TDF_Label()
    tool.GetShapes(labels)
    finder = ws.TransferWriter().FinderProcess()
    targets = {}
    for i in range(1, labels.Length() + 1):
        part = labels.Value(i)
        if XCAFDoc_ShapeTool.IsAssembly_s(part):
            continue
        subs = Sequence_TDF_Label()
        XCAFDoc_ShapeTool.GetSubShapes_s(part, subs)
        for label in [part] + [subs.Value(j) for j in range(1, subs.Length() + 1)]:
            visual = XCAFDoc_VisMaterialTool.GetShapeMaterial_s(label)
            if not visual or not visual.HasPbrMaterial():
                continue
            shape = XCAFDoc_ShapeTool.GetShape_s(label)
            if label == part or shape.ShapeType() in (TopAbs_COMPOUND, TopAbs_COMPSOLID):
                explorer = TopExp_Explorer(shape, TopAbs_SOLID)
                shapes = []
                while explorer.More():
                    shapes.append(explorer.Current())
                    explorer.Next()
                if not shapes:
                    explorer = TopExp_Explorer(shape, TopAbs_FACE)
                    while explorer.More():
                        shapes.append(explorer.Current())
                        explorer.Next()
                if not shapes:
                    shapes = [shape]
            else:
                shapes = [shape]
            for shape in shapes:
                item = STEPConstruct.FindEntity_s(finder, shape)
                if not item:
                    continue
                for styled in by_item.get(item, []):
                    surface = _surface(styled)
                    if surface and surface[0].DynamicType().Name() != "StepVisual_PresentationStyleByContext" and _fill_colour(surface[2].Style()):
                        # A material on a solid/face wins over its parent's material
                        # when both map to the same STEP styled item.
                        targets[styled] = (surface, visual)
    if not targets:
        return False

    from cadgen.engine.colors import linear_to_srgb
    from OCP.STEPConstruct import STEPConstruct_RenderingProperties, STEPConstruct_Styles
    from OCP.StepVisual import (StepVisual_PresentationStyleAssignment, StepVisual_PresentationStyleSelect,
                                StepVisual_RenderingPropertiesSelect, StepVisual_SurfaceSideStyle,
                                StepVisual_SurfaceStyleElementSelect, StepVisual_SurfaceStyleUsage)
    from OCP.collections import (HArray1_StepVisual_PresentationStyleAssignment,
                                 HArray1_StepVisual_PresentationStyleSelect,
                                 HArray1_StepVisual_SurfaceStyleElementSelect)

    from OCP.Quantity import Quantity_Color, Quantity_TOC_RGB

    looks = {}
    details = []
    for styled, (surface, visual) in targets.items():
        pbr = visual.PbrMaterial()
        color = pbr.BaseColor.GetRGB()
        base = (color.Red(), color.Green(), color.Blue())
        metal = max(0., min(1., pbr.Metallic))
        rough = max(0., min(1., pbr.Roughness))
        spec = tuple(.04 * (1. - metal) + c * metal for c in base)
        remaining = 1. - max(spec)
        diffuse = base
        diffuse_factor = max(0., min(1., .96 * (1. - metal) / max(remaining, 1e-6)))
        key = (0.2, diffuse_factor, 1., 128. * (1. - rough), tuple(linear_to_srgb(c) for c in spec))
        looks.setdefault(key, len(looks))
        details.append((styled, surface, visual, diffuse, key))
    records = dict(zip(looks, _template(list(looks))))
    model = writer.ChangeWriter().Model()
    for styled, (assignment, selected, usage), visual, diffuse, key in details:
        color = Quantity_Color(*diffuse, Quantity_TOC_RGB)
        encoded = STEPConstruct_Styles.EncodeColor_s(color)
        props = STEPConstruct_RenderingProperties()
        props.Init(color, 1. - visual.PbrMaterial().BaseColor.Alpha())
        props.SetAmbientDiffuseAndSpecularReflectance(*key[:4], Quantity_Color(*key[4], Quantity_TOC_RGB))
        rendering = props.CreateRenderingProperties(encoded)
        selectors = rendering.Properties()
        selector = StepVisual_RenderingPropertiesSelect()
        selector.SetValue(records[key])
        selectors.SetValue(selectors.Length(), selector)
        # Clone the assignment path: STEP writer may share a style between objects.
        original_side = usage.Style()
        old = [original_side.StylesValue(i) for i in range(1, original_side.NbStyles() + 1)
               if not original_side.StylesValue(i).SurfaceStyleRendering()]
        rendering_select = StepVisual_SurfaceStyleElementSelect()
        rendering_select.SetValue(rendering)
        values = HArray1_StepVisual_SurfaceStyleElementSelect(1, len(old) + 1)
        for i, value in enumerate([*old, rendering_select], 1):
            values.SetValue(i, value)
        side = StepVisual_SurfaceSideStyle()
        side.Init(original_side.Name(), values)
        replacement_usage = StepVisual_SurfaceStyleUsage()
        replacement_usage.Init(usage.Side(), side)
        newselect = StepVisual_PresentationStyleSelect()
        newselect.SetValue(replacement_usage)
        choices = HArray1_StepVisual_PresentationStyleSelect(1, assignment.NbStyles())
        for i in range(1, assignment.NbStyles() + 1):
            choices.SetValue(i, newselect if i == selected else assignment.StylesValue(i))
        replacement = StepVisual_PresentationStyleAssignment()
        replacement.Init(choices)
        assignments = HArray1_StepVisual_PresentationStyleAssignment(1, styled.NbStyles())
        for i in range(1, styled.NbStyles() + 1):
            assignments.SetValue(i, replacement if styled.StylesValue(i) == assignment else styled.StylesValue(i))
        styled.SetStyles(assignments)
        model.AddWithRefs(replacement)
    return True


def read_visual_styles(reader: Any, doc: Any) -> None:
    """Restore native STEP reflectance as an approximate PBR look on its shape label."""
    from OCP.STEPConstruct import STEPConstruct, STEPConstruct_Styles
    from OCP.Quantity import Quantity_Color
    from OCP.Standard import Standard_Failure
    from OCP.TDF import TDF_Label
    from OCP.TCollection import TCollection_AsciiString
    from OCP.XCAFDoc import XCAFDoc_DocumentTool, XCAFDoc_VisMaterial
    from cadgen.engine.document import _quantity

    ws = reader.Reader().WS()
    styles = _styles(ws)
    tool = XCAFDoc_DocumentTool.ShapeTool_s(doc.Main())
    material_tool = XCAFDoc_DocumentTool.VisMaterialTool_s(doc.Main())
    process = ws.TransferReader().TransientProcess()
    cache = {}
    for i in range(1, styles.NbStyles() + 1):
        styled = styles.Style(i)
        found = _surface(styled)
        if not found or found[0].DynamicType().Name() == "StepVisual_PresentationStyleByContext" or not styled.Item():
            continue
        side = found[2].Style()
        for j in range(1, side.NbStyles() + 1):
            rendering = side.StylesValue(j).Value()
            if rendering is None or not hasattr(rendering, 'Properties') or rendering.Properties() is None:
                continue
            alpha, data = 1., None
            for k in range(1, rendering.Properties().Length() + 1):
                prop = rendering.Properties().Value(k).Value()
                if not prop:
                    continue
                if prop.DynamicType().Name() == 'StepVisual_SurfaceStyleTransparent':
                    alpha = 1. - prop.Transparency()
                elif prop.DynamicType().Name() == 'StepData_UndefinedEntity' and prop.StepType() == 'SURFACE_STYLE_REFLECTANCE_AMBIENT_DIFFUSE_SPECULAR':
                    data = prop.UndefinedContent()
            if data is None or data.NbParams() != 5:
                continue
            try:
                ambient, diffuse_factor, specular_factor, exponent = [float(data.ParamValue(k).ToCString()) for k in range(1, 5)]
                spec_color = data.ParamEntity(5)
                diffuse_color = rendering.SurfaceColour()
                d = Quantity_Color()
                s = Quantity_Color()
                if not STEPConstruct_Styles.DecodeColor_s(diffuse_color, d) or not STEPConstruct_Styles.DecodeColor_s(spec_color, s):
                    continue
                vals = [ambient, diffuse_factor, specular_factor, exponent, alpha, d.Red(), d.Green(), d.Blue(), s.Red(), s.Green(), s.Blue()]
                if (not all(math.isfinite(v) for v in vals)
                        or not all(0. <= v <= 1. for v in (ambient, diffuse_factor, specular_factor, alpha))
                        or exponent < 0.):
                    continue
                clamp = lambda v: max(0., min(1., v))
                diffuse = [clamp(v * diffuse_factor) for v in (d.Red(), d.Green(), d.Blue())]
                specular = [clamp(v * specular_factor) for v in (s.Red(), s.Green(), s.Blue())]
                brightness = lambda c: math.sqrt(.299 * c[0] ** 2 + .587 * c[1] ** 2 + .114 * c[2] ** 2)
                ds, ss = brightness(diffuse), brightness(specular)
                remaining = 1. - max(specular)
                if ss < .04:
                    metal = 0.
                else:
                    b = ds * remaining / .96 + ss - .08
                    metal = clamp((-b + math.sqrt(max(b * b - .16 * (.04 - ss), 0.))) / .08)
                diffuse_base = [x * remaining / .96 / max(1. - metal, 1e-6) for x in diffuse]
                spec_base = [(x - .04 * (1. - metal)) / max(metal, 1e-6) for x in specular]
                base = [clamp(a * (1. - metal * metal) + b * metal * metal) for a, b in zip(diffuse_base, spec_base)]
                rough = 1. - clamp(exponent / 128.)
                key = (*base, clamp(alpha), metal, rough)
                shape = STEPConstruct.FindShape_s(process, styled.Item())
                label = TDF_Label()
                if shape.IsNull() or not tool.Search(shape, label, False, False, True):
                    continue
                if key not in cache:
                    visual = XCAFDoc_VisMaterial()
                    pbr = visual.ConvertToPbrMaterial()
                    pbr.BaseColor = _quantity((*base, clamp(alpha)))
                    pbr.Metallic = metal
                    pbr.Roughness = rough
                    pbr.IsDefined = True
                    visual.SetPbrMaterial(pbr)
                    cache[key] = material_tool.AddMaterial(visual, TCollection_AsciiString('STEP appearance'))
                material_tool.SetShapeMaterial(label, cache[key])
            except (AttributeError, ValueError, TypeError, OverflowError, Standard_Failure):
                # Unknown or malformed foreign styles keep the reader's standard color.
                continue
