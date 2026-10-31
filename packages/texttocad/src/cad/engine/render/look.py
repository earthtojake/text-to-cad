"""The regular display modes' look: one frozen record that both renderers draw by.

``occt.py`` draws it on OCCT's PBR raster (``finish.py``; X-ray on its Phong program), the engine
serves it as JSON (``GET /api/look``, its environment at ``GET /api/look/environment``:
``serve.py``), and the CAD Viewer draws an engine document's regular modes by it through three's
physical materials (core's ``lib/xbf/xbfLook.js``). Preview's photographic look is not here.

**The light.** One key, a directional light at ``intensity`` (radiance: a white surface facing it
reflects ``intensity / pi``), and one environment, ``studio.hdr`` beside this module, lighting
every surface at ``environment.intensity``. Nothing else: no ambient term, no fill, no shadow
(X-ray apart: its own model, below). The environment is the CAD Viewer's neutral studio (the one
an authored finish reflected), baked once by ``scripts/look/bake-environment.mjs`` as a 512 x 256
equirectangular Radiance image in the document's frame: rows from +Z (the top row) to -Z, columns once around +Z from -X through +Y, +X
and -Y; a pixel is ``m / 255 * 2 ** (e - 128)``, as three's HDRLoader decodes it. Both renderers
load that image: OCCT through a cube map whose texels hold the radiance over its brightest value,
its ambient light (OCCT's PBR program multiplies the whole image-based light by it) that brightest
value times ``environment.intensity``, from which OCCT bakes its image-based light; the viewer
through three's PMREM, every level of which it fills as OCCT bakes (core's
``lib/viewer/ggxEnvironment.js``): the image convolved with the GGX lobe of the level's roughness,
the roughest the irradiance's nine spherical harmonics, estimated from the 1024 points OCCT's own
bake reads.

**The surfaces.** A part without a material, and every fill (Parts), is the ``plain`` finish (a
dielectric) over its colour, linear, raised to ``colour_power``: squared, which keeps the
saturated colours of OCCT's Phong look, whose ASPECT material multiplied the colour by itself. A
part with a material is its colour as authored and its finish: metallic, roughness, IOR, emission
and alpha, which both renderers draw alike. Anisotropy neither draws: OCCT's raster has no term for
it, and the viewer draws OCCT's program (three's bent reflection turned a brushed plate's top, seen
from above, from the studio's softbox to its dark wall). What else OCCT's raster has no term for,
the viewer draws and OCCT approximates (``finish.py``): a clear coat (OCCT: the base's roughness
eased toward the coat's) and transmission (OCCT: opacity over the colour tinted by the transmission
colour).

**The surface model** (``brdf = "occt"``) is OCCT 7.9's PBR program (``occt_phong-pbr``, read from
the GLSL it compiles), which the viewer draws too (core's ``lib/viewer/surfaceBrdf.js``): per light
``((1 - F) (1 - metallic) base / pi + D G F / 4) * intensity * max(0, N.L)`` (GGX ``D`` of
``alpha = r^2``, Schlick-GGX ``G = 1 / ((N.V (1 - k) + k) (N.L (1 - k) + k))`` with
``k = (r + 1)^2 / 8``, Schlick ``F`` at V.H from ``F0 = mix(F0(ior), base, metallic)``); and from
the environment ``ambient * ((1 - F_r) (1 - metallic) base * SH(N) + (F0 A + B) * prefiltered(R, r))``
(``F_r`` Schlick at N.V toward ``max(1 - r, F0)``; ``A``, ``B`` OCCT's split-sum table,
``GenerateEnvLUT``: Schlick-GGX at ``k = r^2 / 2``; ``prefiltered`` the image convolved with the GGX
lobe of ``r``; ``SH`` the irradiance's nine spherical harmonics, over pi). Single scattering: no
multiple-scattering energy is added back, as three's own physical model adds it.

**The picture** is the linear sum clamped and sRGB-encoded (``tone = "clamp"``): OCCT's raster
applies no tone curve and no exposure. Its Filmic curve (``Graphic3d_ToneMappingMethod_Filmic``) is
the path tracer's alone (``Display.fs``, under ``PATH_TRACING``): with ``x`` the linear colour
times ``2 ** Exposure`` and ``W`` the ``WhitePoint``,

    f(x)  = (x * (1.425 x + 0.05) + 0.004) / (x * (1.425 x + 0.6) + 0.0491) - 0.0821
    out   = f(x) / f(W)

**X-ray** is the colour-only model both renderers drew before the look was physically based
(``xray``): no finish, a part's material its colour alone, at the mode's opacity (0.22) under
every edge. OCCT draws it with its Phong program (``occt_phong``), an ambient light and
directional lights white (Phong reads a directional light's colour, not its intensity, so each is
1), each face ``AIS_Shape`` given its colour twice, which OCCT's ASPECT material multiplies:

    rgb = c * c * (ambient + sum_k max(0, N.L_k)) + specular * sum_k [N.L_k > 0] * max(0, N.H_k) ** (128 * shininess)

The viewer draws it with three's own physical model under the same lights (at ``pi`` times each
radiance, three's Lambertian surface dividing by ``pi``) and no environment, its colour squared
and a GGX lobe as wide as the Phong highlight (core's ``lib/xbf/xbfLook.js``), and blends it in
linear light, as OCCT's sRGB frame buffer blends it (its rig's ``blend``: the faces drawn into a
half-float target and encoded once, the edges drawn over them after, as OCCT draws them in a layer
over the model; core's ``lib/viewer/sceneRig.js``). The two order the faces apart: three sorts
each part back to front, OCCT draws them as displayed.

A drawing (a DXF, ``drawing.py``) has no light: ``DRAWING`` is the viewer's DXF pane's look, its paper
and its ink (the pen ACI 7 draws in) for the light and the dark appearance (core's ``lib/appTheme.js``),
its lines one pixel wide, the drawing fitted within the pane's margin.

Edges are unlit lines in their class's colour, 1 px; Hidden line's faces are unlit in the
backdrop's colour, hiding what is behind them; Wireframe draws edges alone. The grid is the viewer's measuring grid (core's
``lib/viewer/stageGrid.js``, drawn by ``grid.py``): graph paper on z = 0 through the origin, the
step of 1, 2 or 5 x 10^n nearest ``framing / cells`` (``framing`` the model's diameter at rest
times 1.04), a major every 5th or 10th line, a red X and a green Y axis, faded out ``extent``
framings from the origin.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Light:
    """A directional light: ``direction`` the way it travels (``V3d_DirectionalLight``'s), in the
    document's frame (Z up), a face turned against it lit; ``intensity`` its radiance."""

    name: str
    direction: tuple[float, float, float]
    intensity: float


@dataclass(frozen=True)
class Environment:
    """The image-based light: ``file`` beside this module, at ``intensity`` times its radiance."""

    file: str
    intensity: float


@dataclass(frozen=True)
class Finish:
    """A dielectric or metal surface, as glTF's metallic-roughness model has it."""

    metallic: float
    roughness: float
    ior: float


@dataclass(frozen=True)
class Mode:
    """A display mode's recipe. ``faces``: ``lit``, ``backdrop`` (unlit in the backdrop's colour,
    hiding what is behind) or ``none``; ``edges``: ``none``, ``visible`` (depth tested) or ``all``
    (over every face); ``palette``: each instance in the parts palette, by its index."""

    name: str
    faces: str
    edges: str
    opacity: float = 1.0
    palette: bool = False


@dataclass(frozen=True)
class ColourOnly:
    """X-ray's colour-only model: an ambient light, directional lights (``intensity`` 1: Phong
    reads none), and Phong's white highlight, ``specular`` strong at exponent ``128 * shininess``."""

    ambient: float
    lights: tuple[Light, ...]
    specular: float
    shininess: float


@dataclass(frozen=True)
class Grid:
    colour: str
    cells: float  # minor cells across the model's framing: the cell is the round step nearest framing / cells
    extent: float  # framings from the origin by which the paper has faded out
    axes: bool  # a red X and a green Y axis line


@dataclass(frozen=True)
class Drawing:
    """The look of a drawing: paper and ink by appearance, the lines' width, the fit's margin (pixels)."""

    light: tuple[str, str]
    dark: tuple[str, str]
    line_width: float
    margin: float

    def paper(self, appearance: str) -> tuple[str, str]:
        """``(paper, ink)`` for ``light`` or ``dark``."""
        return self.dark if appearance == "dark" else self.light


@dataclass(frozen=True)
class Look:
    backdrop: str
    lights: tuple[Light, ...]
    environment: Environment
    colour_power: float
    plain: Finish
    brdf: str
    tone: str
    exposure: float
    fill: str
    palette: tuple[str, ...]
    edge_colours: tuple[tuple[str, str], ...]
    edge_width: float
    modes: tuple[Mode, ...]
    grid: Grid
    xray: ColourOnly
    version: int = field(default=4)

    @property
    def environment_path(self) -> Path:
        """The environment's image, which ``GET /api/look/environment`` serves."""
        return Path(__file__).resolve().parent / self.environment.file

    def edge(self, line: str) -> str:
        return dict(self.edge_colours)[line]

    def mode(self, name: str) -> Mode:
        return next(mode for mode in self.modes if mode.name == name)

    def json(self) -> dict[str, Any]:
        """The record as ``GET /api/look`` serves it (camelCase, as the structure is); the
        environment's image is ``GET /api/look/environment``."""
        return {
            "version": self.version, "backdrop": self.backdrop,
            "lights": [{"name": light.name, "direction": list(light.direction), "intensity": light.intensity}
                       for light in self.lights],
            "environment": {"url": "/api/look/environment", "intensity": self.environment.intensity},
            "colourPower": self.colour_power,
            "plain": {"metallic": self.plain.metallic, "roughness": self.plain.roughness, "ior": self.plain.ior},
            "brdf": self.brdf, "tone": self.tone, "exposure": self.exposure, "fill": self.fill,
            "palette": list(self.palette), "edges": {"colours": dict(self.edge_colours), "width": self.edge_width},
            "modes": {mode.name: {"faces": mode.faces, "edges": mode.edges, "opacity": mode.opacity,
                                  "palette": mode.palette} for mode in self.modes},
            "grid": {"colour": self.grid.colour, "cells": self.grid.cells, "extent": self.grid.extent,
                     "axes": self.grid.axes},
            "xray": {"ambient": self.xray.ambient,
                     "lights": [{"name": light.name, "direction": list(light.direction), "intensity": light.intensity}
                                for light in self.xray.lights],
                     "specular": self.xray.specular, "shininess": self.xray.shininess},
        }


LOOK = Look(
    backdrop="#f0f4f9",
    lights=(Light("key", (-0.35, 0.55, -1.0), 4.0),),
    environment=Environment("studio.hdr", 0.5),
    colour_power=2.0,
    plain=Finish(metallic=0.0, roughness=0.5, ior=1.5),
    brdf="occt",
    tone="clamp",
    exposure=0.0,
    fill="#b6c4ce",
    palette=("#b6c4ce", "#f4a7a7", "#f8c77e", "#f7e38d", "#b9e88f", "#8fe3c0", "#92d7f5", "#a9b8ff", "#c7a8ff",
             "#f2a7d9"),
    edge_colours=(("feature", "#253443"), ("tangent", "#667788"), ("seam", "#495b6c")),
    edge_width=1.0,
    modes=(Mode("solid", "lit", "visible"), Mode("shaded", "lit", "none"),
           Mode("parts", "lit", "visible", palette=True), Mode("xray", "lit", "all", opacity=0.22),
           Mode("hidden-line", "backdrop", "visible"), Mode("wireframe", "none", "all")),
    grid=Grid(colour="#4ea8cc", cells=20.0, extent=6.0, axes=True),
    xray=ColourOnly(ambient=0.5, lights=(Light("key", (-0.35, 0.55, -1.0), 1.0), Light("fill", (0.6, 0.2, -0.3), 1.0)),
                    specular=0.08, shininess=0.35),
)

DRAWING = Drawing(light=("#ffffff", "#171717"), dark=("#27292d", "#fafafa"), line_width=1.0, margin=16.0)
