"""PROTOTYPE: the regular display modes on OCCT's PBR raster, as the look (``look.py``) draws them.

``occt.py`` asks this module for its rig and its faces' materials; the viewer draws the same
record through three's physical materials (core's ``lib/xbf/xbfLook.js``). Preview draws a part
with a material in the same material (under its own studio's light), so a material looks one
material in every look.

- **The environment** is the look's image (``studio.hdr``: equirectangular, the document's frame,
  decoded as three's HDRLoader decodes it), sampled onto a cube map's six faces in OpenGL's face
  orientation. OCCT takes a cube map's texels as colours, each at most 1, so the faces hold the
  radiance over its brightest value ``M`` and the light that scales the image -- the ambient light,
  which OCCT's PBR program multiplies the whole image-based light by -- is ``M`` times the look's
  intensity: the same light, to a float's precision.
- **The key** is a directional light at the look's intensity (the PBR program reads a light's
  intensity; Phong did not).
- **A face's material** is a ``Graphic3d_PBRMaterial`` (a ``PHYSIC`` aspect, so the PBR colour is
  the base colour): a part without a material is the look's plain finish over its colour raised to
  the look's power, as is every fill (Parts); a part with one is its colour as authored, its
  metallic, roughness, IOR, emission (colour times strength) and alpha. What OCCT's raster has no
  term for is approximated: a clear coat is drawn as the base's roughness eased toward the coat's
  (``COAT_ROUGHNESS``), anisotropy is dropped, and transmission becomes opacity
  (``1 - TRANSMISSION_OPACITY * transmission``) over the base colour tinted by the transmission
  colour. OCCT's roughness is ``0.01 + 0.99 n`` of the normalized ``n`` it is given, so it is
  given ``(r - 0.01) / 0.99`` for three's ``r``.
- **X-ray** is not drawn by this: it is the look's colour-only model (``look.py``) on OCCT's Phong
  program, its rig ``put_up_colour_only``'s and its faces' material ``occt.py``'s.
"""

from __future__ import annotations

import math
from functools import lru_cache
from typing import Any

import numpy as np

from cadgen.engine.render.look import LOOK

CUBE_SIZE = 256
# A transmissive material's opacity: fully transmissive glass is its reflections alone.
TRANSMISSION_OPACITY = 1.0
# A clear coat over a rougher base: the base's roughness moved this far toward the coat's.
COAT_ROUGHNESS = 0.5


def decode_hdr(data: bytes) -> np.ndarray:
    """A Radiance RGBE image (flat or new run-length scanlines) as float32 (H, W, 3), each pixel
    ``m / 255 * 2 ** (e - 128)`` as three's HDRLoader decodes it, rows top first."""
    end = data.index(b"\n\n") + 2
    line = data.index(b"\n", end)
    axes = data[end:line].split()
    if len(axes) != 4 or axes[0] != b"-Y" or axes[2] != b"+X":
        raise ValueError("an environment image is a -Y H +X W Radiance file")
    height, width = int(axes[1]), int(axes[3])
    at = line + 1
    out = np.zeros((height, width, 4), np.uint8)
    for row in range(height):
        if data[at] == 2 and data[at + 1] == 2 and (data[at + 2] << 8 | data[at + 3]) == width:
            at += 4
            for channel in range(4):
                x = 0
                while x < width:
                    count = data[at]
                    at += 1
                    if count > 128:
                        count -= 128
                        out[row, x:x + count, channel] = data[at]
                        at += 1
                    else:
                        out[row, x:x + count, channel] = np.frombuffer(data, np.uint8, count, at)
                        at += count
                    x += count
        else:
            out[row] = np.frombuffer(data, np.uint8, width * 4, at).reshape(width, 4)
            at += width * 4
    scale = np.where(out[..., 3:4] > 0, np.ldexp(1.0, out[..., 3:4].astype(np.int32) - 128) / 255.0, 0.0)
    return (out[..., :3].astype(np.float64) * scale).astype(np.float32)


@lru_cache(maxsize=1)
def environment() -> np.ndarray:
    """The look's environment, its radiance per pixel (H, W, 3)."""
    return decode_hdr(LOOK.environment_path.read_bytes())


def sample(image: np.ndarray, directions: np.ndarray) -> np.ndarray:
    """The equirectangular ``image`` along unit ``directions`` (..., 3), bilinear: columns once
    around +Z from -X through +Y, +X and -Y, rows from +Z to -Z (``look.py``)."""
    height, width = image.shape[:2]
    x, y, z = directions[..., 0], directions[..., 1], directions[..., 2]
    u = 0.5 - np.arctan2(y, x) / (2 * math.pi)
    v = 0.5 - np.arcsin(np.clip(z, -1, 1)) / math.pi
    fx, fy = u * width - 0.5, v * height - 0.5
    x0, y0 = np.floor(fx).astype(int), np.floor(fy).astype(int)
    tx, ty = (fx - x0)[..., None], (fy - y0)[..., None]
    y1 = np.clip(y0 + 1, 0, height - 1)
    y0 = np.clip(y0, 0, height - 1)
    x1, x0 = (x0 + 1) % width, x0 % width
    top = image[y0, x0] * (1 - tx) + image[y0, x1] * tx
    bottom = image[y1, x0] * (1 - tx) + image[y1, x1] * tx
    return top * (1 - ty) + bottom * ty


def cube_faces(image: np.ndarray, size: int = CUBE_SIZE) -> np.ndarray:
    """The six faces (+X, -X, +Y, -Y, +Z, -Z) side by side, (size, 6 size, 3), each in OpenGL's
    orientation of a cube map face, rows top first. OCCT reads a cube map's direction ``c`` as the
    document's ``(c.z, c.x, c.y)`` (measured: its +Y is up), so each texel holds the image there."""
    a = (np.arange(size) + 0.5) / size * 2 - 1
    s, t = np.meshgrid(a, a)
    one = np.ones_like(s)
    faces = [(one, -t, -s), (-one, -t, s), (s, one, t), (s, -one, -t), (s, -t, one), (-s, -t, -one)]
    strips = []
    for face in faces:
        directions = np.stack(face, -1)
        directions /= np.linalg.norm(directions, axis=-1, keepdims=True)
        strips.append(sample(image, directions[..., [2, 0, 1]]))
    return np.concatenate(strips, axis=1)


@lru_cache(maxsize=1)
def _cube_pixmap() -> tuple[Any, float]:
    from OCP.Image import Image_Format, Image_PixMap
    from OCP.Quantity import Quantity_Color, Quantity_TOC_RGB

    faces = cube_faces(environment()).astype(np.float64)
    brightest = float(faces.max()) or 1.0
    faces /= brightest
    height, width = faces.shape[:2]
    pixmap = Image_PixMap()
    pixmap.InitZero(Image_Format.Image_Format_RGBF, width, height)
    pixmap.SetTopDown(True)
    for y in range(height):
        row = faces[y]
        for x in range(width):
            r, g, b = row[x]
            pixmap.SetPixelColor(x, y, Quantity_Color(r, g, b, Quantity_TOC_RGB))
    return pixmap, brightest


def put_up(view: Any, viewer: Any, backdrop: Any) -> list[Any]:
    """The look's rig on ``view``: its environment as the image-based light, its key, the PBR
    shading model, and ``backdrop`` (a ``Quantity_Color``) behind the model. OCCT bakes the
    image-based light from the background's cube map, so the cube map is the background until a
    first frame has baked it, and the backdrop after. Returns the lights, for whoever replaces them."""
    from OCP.Aspect import Aspect_GradientFillMethod
    from OCP.Graphic3d import Graphic3d_CubeMapPacked, Graphic3d_TypeOfShadingModel
    from OCP.Quantity import Quantity_Color, Quantity_TOC_RGB
    from OCP.V3d import V3d_AmbientLight, V3d_DirectionalLight
    from OCP.gp import gp_Dir

    pixmap, brightest = _cube_pixmap()
    white = Quantity_Color(1, 1, 1, Quantity_TOC_RGB)
    ambient = V3d_AmbientLight(white)
    ambient.SetIntensity(LOOK.environment.intensity * brightest)
    lights = [ambient]
    for light in LOOK.lights:
        directional = V3d_DirectionalLight(gp_Dir(*light.direction), white)
        directional.SetIntensity(light.intensity)
        lights.append(directional)
    for light in lights:
        viewer.AddLight(light)
        viewer.SetLightOn(light)
    cubemap = Graphic3d_CubeMapPacked(pixmap)
    cubemap.SetMipmapsGeneration(True)
    view.SetBackgroundCubeMap(cubemap, True, False)
    view.SetImageBasedLighting(True)
    view.SetShadingModel(Graphic3d_TypeOfShadingModel.Graphic3d_TypeOfShadingModel_Pbr)
    view.Redraw()  # bakes the image-based light from the cube map
    view.SetBgGradientColors(backdrop, backdrop, Aspect_GradientFillMethod.Aspect_GradientFillMethod_Vertical, False)
    return lights


def put_up_colour_only(view: Any, viewer: Any) -> list[Any]:
    """X-ray's colour-only rig on ``view`` (``LOOK.xray``): its ambient light and its white
    directional lights, Phong shading, no image-based light. Returns the lights, for whoever
    replaces them; ``put_up`` puts the look's own rig back."""
    from OCP.Graphic3d import Graphic3d_TypeOfShadingModel
    from OCP.Quantity import Quantity_Color, Quantity_TOC_RGB
    from OCP.V3d import V3d_AmbientLight, V3d_DirectionalLight
    from OCP.gp import gp_Dir

    white = Quantity_Color(1, 1, 1, Quantity_TOC_RGB)
    ambient = V3d_AmbientLight(white)
    ambient.SetIntensity(LOOK.xray.ambient)
    lights = [ambient]
    for light in LOOK.xray.lights:
        directional = V3d_DirectionalLight(gp_Dir(*light.direction), white)
        directional.SetIntensity(light.intensity)
        lights.append(directional)
    for light in lights:
        viewer.AddLight(light)
        viewer.SetLightOn(light)
    view.SetImageBasedLighting(False)
    view.SetShadingModel(Graphic3d_TypeOfShadingModel.Graphic3d_TypeOfShadingModel_Phong)
    return lights


def occt_roughness(roughness: float) -> float:
    """The normalized roughness OCCT is given for three's ``roughness`` (``0.01 + 0.99 n``)."""
    return min(max((roughness - 0.01) / 0.99, 0.0), 1.0)


def linear(value: Any) -> tuple[float, float, float]:
    """A colour as linear RGB: a ``#rrggbb`` (sRGB, as CSS) decoded, an rgb(a) tuple as it is."""
    if isinstance(value, str):
        encoded = [int(value.lstrip("#")[at:at + 2], 16) / 255 for at in (0, 2, 4)]
        return tuple(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in encoded)
    return tuple(float(c) for c in value[:3])


def finish(rgba: Any, material: dict[str, Any] | None) -> dict[str, Any]:
    """What a face is drawn as: ``rgba`` its colour (linear, as the structure holds it, or a
    ``#rrggbb`` fill), ``material`` the structure's material for it, or None. Base colour, alpha,
    metallic, roughness, IOR and emission, every approximation applied."""
    colour = linear(rgba if rgba is not None else LOOK.fill)
    alpha = float(rgba[3]) if isinstance(rgba, (tuple, list)) and len(rgba) > 3 else 1.0
    if material is None:
        return {"color": tuple(value ** LOOK.colour_power for value in colour), "alpha": alpha,
                "metallic": LOOK.plain.metallic, "roughness": LOOK.plain.roughness, "ior": LOOK.plain.ior,
                "emission": (0.0, 0.0, 0.0)}
    if material["pbr"].get("textures"):
        raise ValueError("OCCT snapshots of native material texture maps require UV mapping; use a scalar PBR look")
    material = material["pbr"]["values"]
    roughness = float(material.get("roughness") if material.get("roughness") is not None else 0.5)
    coat = float(material.get("clearcoat") or 0.0)
    if coat > 0:
        target = float(material.get("clearcoatRoughness") or 0.0)
        roughness += (target - roughness) * COAT_ROUGHNESS * coat
    transmission = float(material.get("transmission") or 0.0)
    if transmission > 0:
        tint = material.get("attenuationColor") or (1.0, 1.0, 1.0)
        colour = tuple(c * float(t) for c, t in zip(colour, tint))
        alpha *= 1 - TRANSMISSION_OPACITY * transmission
    strength = float(material.get("emissiveIntensity") if material.get("emissiveIntensity") is not None else 1.0)
    emission = tuple(float(value) * strength for value in (material.get("emissive") or (0.0, 0.0, 0.0)))
    return {"color": colour, "alpha": alpha, "metallic": float(material.get("metalness") or 0.0),
            "roughness": roughness, "ior": float(material.get("ior") or 1.5), "emission": emission}


def aspect(found: dict[str, Any]) -> Any:
    """``finish``'s answer as an OCCT material: a PHYSIC aspect whose PBR material is the finish."""
    from OCP.Graphic3d import (Graphic3d_MaterialAspect, Graphic3d_NameOfMaterial, Graphic3d_PBRMaterial,
                               Graphic3d_TypeOfMaterial)
    from OCP.collections import Vec3_float
    from OCP.Quantity import Quantity_Color, Quantity_ColorRGBA, Quantity_TOC_RGB

    colour = Quantity_Color(*found["color"], Quantity_TOC_RGB)
    material = Graphic3d_MaterialAspect(Graphic3d_NameOfMaterial.Graphic3d_NameOfMaterial_UserDefined)
    material.SetMaterialType(Graphic3d_TypeOfMaterial.Graphic3d_MATERIAL_PHYSIC)
    material.SetColor(colour)
    material.SetDiffuseColor(colour)
    pbr = Graphic3d_PBRMaterial()
    pbr.SetColor(Quantity_ColorRGBA(colour, found["alpha"]))
    pbr.SetMetallic(found["metallic"])
    pbr.SetRoughness(occt_roughness(found["roughness"]))
    pbr.SetIOR(found["ior"])
    pbr.SetEmission(Vec3_float(*(float(value) for value in found["emission"])))
    pbr.SetAlpha(found["alpha"])
    material.SetPBRMaterial(pbr)
    if found["alpha"] < 1:
        material.SetAlpha(found["alpha"])
    return material


def face_material(rgba: Any, material: dict[str, Any] | None) -> tuple[Any, Any]:
    """A face's OCCT material (``aspect``) and its base colour, for ``finish``'s arguments."""
    from OCP.Quantity import Quantity_Color, Quantity_TOC_RGB

    found = finish(rgba, material)
    return aspect(found), Quantity_Color(*found["color"], Quantity_TOC_RGB)
