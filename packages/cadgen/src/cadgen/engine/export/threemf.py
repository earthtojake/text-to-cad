"""3MF: a zip holding one model, in millimetres.

An object per prototype (its mesh at the prototype's frame) and a build item per
placement (the object at the placement's transform). Looks go through the 3MF materials
extension: one base material per look (named by the part's material, else its colour),
its display colour the look's colour in sRGB, and a metallic display property per base
(``pbmetallicdisplayproperties``: the material's metallicness and roughness, a matte one
for a look without a material). An object's default look is its part's; a painted face's
triangles name their own (``pid``/``p1``). A placement whose own colour is not its part's
places an object of its own drawn in that colour.
"""

from __future__ import annotations

import json

import zipfile
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape, quoteattr

from cadgen.engine.export import ZIP_DATE
from cadgen.engine.export.mesh import groups, meshes

__all__ = ["write"]

CORE = "http://schemas.microsoft.com/3dmanufacturing/core/2015/02"
MATERIALS = "http://schemas.microsoft.com/3dmanufacturing/material/2015/02"
BASE_ID = 1
PROPERTIES_ID = 2


def _srgb(value: float) -> int:
    value = min(max(float(value), 0.0), 1.0)
    value = value * 12.92 if value <= 0.0031308 else 1.055 * value ** (1 / 2.4) - 0.055
    return round(value * 255)


def _hex(rgba: tuple) -> str:
    return "#%02X%02X%02X%02X" % (_srgb(rgba[0]), _srgb(rgba[1]), _srgb(rgba[2]), round(float(rgba[3]) * 255))


def write(view: Any, path: Path) -> None:
    held = meshes(view)
    looks: list[tuple] = []
    look_at: dict[tuple, int] = {}

    def look_index(look: tuple) -> int:
        found = look_at.get(look)
        if found is None:
            found = look_at[look] = len(looks)
            looks.append(look)
        return found

    objects: list[str] = []
    object_at: dict[tuple, int | None] = {}

    def object_of(index: int, color: tuple | None) -> int | None:
        key = (index, color)
        if key in object_at:
            return object_at[key]
        mesh = held[index]
        if not mesh.triangles:
            object_at[key] = None
            return None
        prototype = view.prototypes[index]
        default = look_index(groups(mesh, {**prototype, "faceColors": {}, "faceMaterials": {}}, color)[0][0])
        vertices = "".join(f'<vertex x="{x:.6g}" y="{y:.6g}" z="{z:.6g}"/>' for x, y, z in mesh.positions.tolist())
        rows = []
        for look, indices in groups(mesh, prototype, color):
            at = look_index(look)
            tail = "/>" if at == default else f' pid="{BASE_ID}" p1="{at}"/>'
            rows.extend(f'<triangle v1="{a}" v2="{b}" v3="{c}"{tail}' for a, b, c in indices.reshape(-1, 3).tolist())
        ident = len(objects) + 3
        objects.append(f'<object id="{ident}" type="model" name={quoteattr(prototype["name"])} pid="{BASE_ID}" '
                       f'pindex="{default}"><mesh><vertices>{vertices}</vertices>'
                       f'<triangles>{"".join(rows)}</triangles></mesh></object>')
        object_at[key] = ident
        return ident

    items = []
    for placed in view.placements:
        own = view.prototypes[placed.prototype].get("color")
        color = placed.color if placed.color is not None and placed.color != (tuple(own) if own else None) else None
        ident = object_of(placed.prototype, color)
        if ident is None:
            continue
        m = placed.matrix
        transform = " ".join(f"{value:.9g}" for value in (m[0, 0], m[1, 0], m[2, 0], m[0, 1], m[1, 1], m[2, 1],
                                                          m[0, 2], m[1, 2], m[2, 2], m[0, 3], m[1, 3], m[2, 3]))
        items.append(f'<item objectid="{ident}" transform="{transform}"/>')
    bases, metallic = [], []
    for at, (rgba, given) in enumerate(looks):
        given = json.loads(given) if given is not None else None
        name = given["material"]["name"] if given is not None else f"colour {at + 1}"
        if given is not None:
            given = given["pbr"]["values"]
            metallic.append(f'<m:pbmetallic name={quoteattr(name)} metallicness="{given.get("metalness", 0.0):.6g}" '
                            f'roughness="{given.get("roughness", 0.5):.6g}"/>')
        else:
            metallic.append(f'<m:pbmetallic name={quoteattr(name)} metallicness="0" roughness="0.6"/>')
        bases.append(f'<base name={quoteattr(name)} displaycolor="{_hex(rgba)}"/>')
    # One display property per base, in their order (the extension's rule): shown only for a
    # model with a material at all.
    shown = any(given is not None for _rgba, given in looks)
    resources = (f'<m:pbmetallicdisplayproperties id="{PROPERTIES_ID}">{"".join(metallic)}'
                 f'</m:pbmetallicdisplayproperties>' if shown else "")
    group = f' m:displaypropertiesid="{PROPERTIES_ID}"' if shown else ""
    model = ('<?xml version="1.0" encoding="UTF-8"?>\n'
             f'<model unit="millimeter" xml:lang="en-US" xmlns="{CORE}" xmlns:m="{MATERIALS}">'
             f'<metadata name="Title">{escape(view.name)}</metadata>'
             f'<resources>{resources}<basematerials id="{BASE_ID}"{group}>{"".join(bases)}</basematerials>'
             f'{"".join(objects)}</resources><build>{"".join(items)}</build></model>')
    content_types = ('<?xml version="1.0" encoding="UTF-8"?>\n'
                     '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                     '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                     '<Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/>'
                     '</Types>')
    relationships = ('<?xml version="1.0" encoding="UTF-8"?>\n'
                     '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                     '<Relationship Target="/3D/3dmodel.model" Id="rel0" '
                     'Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/></Relationships>')
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, text in (("[Content_Types].xml", content_types), ("_rels/.rels", relationships),
                           ("3D/3dmodel.model", model)):
            entry = zipfile.ZipInfo(name, ZIP_DATE)
            entry.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(entry, text)
