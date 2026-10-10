"""Laminates: plies of a unidirectional lamina at angles, by classical laminate theory (CLT).

A lamina is transversely isotropic about its fibre direction 1: E1, E2, nu12
and G12 in its plane (what a datasheet gives), G13 = G12 and E3 = E2, nu13 =
nu12 by that symmetry, and G23 from nu23 (E2 / (2 (1 + nu23))) for the
through-thickness shear and the thick (solid) path. Its strengths are Xt, Xc
(along the fibres, tension and compression), Yt, Yc (across them) and S (in-plane
shear), all positive.

A layup lists its plies from the bottom face up: ply 1 lies on the face the
laminate's normal points away from. Angles are in degrees from the layup's 0°
direction, turning toward its 90° direction (normal x 0°).

CLT, per ply k between heights z_k and z_k+1 (from the mid-plane):
Q is the lamina's plane-stress stiffness in its own axes, Q̄ = T(θ)ᵀ Q T(θ)
with T the engineering-strain rotation, and A = Σ Q̄ (z_k+1 - z_k),
B = Σ Q̄ (z_k+1² - z_k²) / 2, D = Σ Q̄ (z_k+1³ - z_k³) / 3. The transverse shear
stiffness is H = 5/6 Σ R(θ)ᵀ diag(G13, G23) R(θ) (z_k+1 - z_k).

Failure, ply by ply, on the in-plane stresses in the ply's own axes (σ1, σ2,
τ12): the Tsai-Wu index F1 σ1 + F2 σ2 + F11 σ1² + F22 σ2² + F66 τ12² + 2 F12 σ1 σ2
(F1 = 1/Xt - 1/Xc, F2 = 1/Yt - 1/Yc, F11 = 1/(Xt Xc), F22 = 1/(Yt Yc), F66 = 1/S²,
F12 = -½ √(F11 F22), Tsai and Hahn's default), and the max-stress index, the
largest of σ1/Xt or -σ1/Xc, σ2/Yt or -σ2/Yc and |τ12|/S. A ply fails at an index
of 1. Stdlib at import; numeric work inside functions.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from cadgen._internal.fea.materials import Material

__all__ = [
    "LAMINA_KEYS", "Lamina", "Laminate", "LayeredMaterial", "Ply", "max_stress", "notation", "parse_layup", "tsai_wu",
]

#: Reissner-Mindlin's shear correction factor (as shell.py's).
SHEAR_CORRECTION = 5.0 / 6.0
#: A lamina's keys: required, then optional.
LAMINA_REQUIRED = ("E1_MPa", "E2_MPa", "nu12", "G12_MPa", "Xt_MPa", "Xc_MPa", "Yt_MPa", "Yc_MPa", "S_MPa")
LAMINA_OPTIONAL = ("G13_MPa", "G23_MPa", "nu23", "density_t_per_mm3", "name")
LAMINA_KEYS = (*LAMINA_REQUIRED, *LAMINA_OPTIONAL)
_EXAMPLE = ('{"E1_MPa": 181000, "E2_MPa": 10300, "nu12": 0.28, "G12_MPa": 7170, "Xt_MPa": 1500, "Xc_MPa": 1500, '
            '"Yt_MPa": 40, "Yc_MPa": 246, "S_MPa": 68}')


def _json(value: Any) -> str:
    import json

    try:
        return json.dumps(value, ensure_ascii=False)
    except (TypeError, ValueError):
        return repr(value)


def _number(value: Any, where: str, *, positive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{where}: expected a number, got {_json(value)}")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{where}: expected a finite number, got {number}")
    if positive and not number > 0:
        raise ValueError(f"{where}: must be > 0, got {number:g}")
    return number


@dataclass(frozen=True)
class Lamina:
    """One unidirectional ply material: stiffness (MPa), strengths (MPa, positive) and density (tonne/mm^3)."""

    name: str
    E1: float
    E2: float
    nu12: float
    G12: float
    Xt: float
    Xc: float
    Yt: float
    Yc: float
    S: float
    G13: float
    G23: float
    nu23: float
    density: float = 0.0
    #: What was assumed for a value the study did not give, in words (the summary says them).
    assumed: tuple[str, ...] = ()

    def Q(self):
        """The plane-stress reduced stiffness in the ply's own axes (σ1, σ2, τ12 from ε1, ε2, γ12)."""
        import numpy as np

        nu21 = self.nu12 * self.E2 / self.E1
        d = 1.0 - self.nu12 * nu21
        return np.array([[self.E1 / d, self.nu12 * self.E2 / d, 0.0],
                         [self.nu12 * self.E2 / d, self.E2 / d, 0.0],
                         [0.0, 0.0, self.G12]])

    def block(self, d1, d2) -> dict:
        """The 3D orthotropic block (materials.py's ``orthotropic``) of this lamina with fibres along ``d1``."""
        return {
            "E1_MPa": self.E1, "E2_MPa": self.E2, "E3_MPa": self.E2, "nu12": self.nu12, "nu13": self.nu12,
            "nu23": self.nu23, "G12_MPa": self.G12, "G13_MPa": self.G13, "G23_MPa": self.G23,
            "axes": [[float(c) for c in d1], [float(c) for c in d2]],
        }

    def as_dict(self) -> dict:
        return {"name": self.name, "E1_MPa": self.E1, "E2_MPa": self.E2, "nu12": self.nu12, "G12_MPa": self.G12,
                "G13_MPa": self.G13, "G23_MPa": self.G23, "nu23": self.nu23, "Xt_MPa": self.Xt, "Xc_MPa": self.Xc,
                "Yt_MPa": self.Yt, "Yc_MPa": self.Yc, "S_MPa": self.S,
                **({"density_t_per_mm3": self.density} if self.density else {})}


def lamina_from_spec(raw: Any, where: str, name: str = "") -> Lamina:
    """A lamina object, checked; the optional values filled by transverse isotropy, each assumption said."""
    if not isinstance(raw, dict):
        raise ValueError(f"{where}: a ply material as an object like {_EXAMPLE}")
    unknown = set(raw) - set(LAMINA_KEYS)
    if unknown:
        raise ValueError(f"{where}: unknown keys {sorted(unknown)}; a ply material takes {', '.join(LAMINA_KEYS)}")
    missing = [key for key in LAMINA_REQUIRED if key not in raw]
    if missing:
        raise ValueError(f"{where}: a ply material needs {', '.join(missing)} (its stiffness and its five strengths, "
                         f"from the prepreg's datasheet), like {_EXAMPLE}")
    v = {key: _number(raw[key], f"{where}.{key}", positive=key.endswith("_MPa")) for key in LAMINA_REQUIRED}
    if not abs(v["nu12"]) < math.sqrt(v["E1_MPa"] / v["E2_MPa"]):
        raise ValueError(f"{where}.nu12: {v['nu12']:g} is not physically possible with these E1 and E2")
    assumed = []
    G13 = _number(raw["G13_MPa"], f"{where}.G13_MPa", positive=True) if "G13_MPa" in raw else v["G12_MPa"]
    if "G13_MPa" not in raw:
        assumed.append("G13 = G12 (transverse isotropy)")
    nu23 = _number(raw["nu23"], f"{where}.nu23") if "nu23" in raw else v["nu12"]
    if "nu23" not in raw and "G23_MPa" not in raw:
        assumed.append("nu23 = nu12")
    if not -1.0 < nu23 < 1.0:
        raise ValueError(f"{where}.nu23: must be between -1 and 1, got {nu23:g}")
    G23 = _number(raw["G23_MPa"], f"{where}.G23_MPa", positive=True) if "G23_MPa" in raw else v["E2_MPa"] / (2.0 * (1.0 + nu23))
    if "G23_MPa" not in raw:
        assumed.append("G23 = E2 / (2 (1 + nu23))")
    density = _number(raw["density_t_per_mm3"], f"{where}.density_t_per_mm3") if "density_t_per_mm3" in raw else 0.0
    label = raw.get("name", name)
    if not isinstance(label, str):
        raise ValueError(f"{where}.name: a short piece of text")
    return Lamina(label or "ply", v["E1_MPa"], v["E2_MPa"], v["nu12"], v["G12_MPa"], v["Xt_MPa"], v["Xc_MPa"],
                  v["Yt_MPa"], v["Yc_MPa"], v["S_MPa"], G13, G23, nu23, density, tuple(assumed))


@dataclass(frozen=True)
class Ply:
    lamina: Lamina
    angle_deg: float
    thickness: float


def strain_rotation(theta_rad: float):
    """T(θ): a strain (ε_x, ε_y, γ_xy) in axes turned by θ, Voigt with engineering shear: ε' = T ε."""
    import numpy as np

    c, s = math.cos(theta_rad), math.sin(theta_rad)
    return np.array([[c * c, s * s, c * s], [s * s, c * c, -c * s], [-2.0 * c * s, 2.0 * c * s, c * c - s * s]])


def q_bar(lamina: Lamina, angle_deg: float):
    """The ply's plane-stress stiffness in the laminate's axes: T(θ)ᵀ Q T(θ)."""
    T = strain_rotation(math.radians(angle_deg))
    return T.T @ lamina.Q() @ T


def shear_bar(lamina: Lamina, angle_deg: float):
    """The ply's transverse shear stiffness (γ_xz, γ_yz) in the laminate's axes: R(θ)ᵀ diag(G13, G23) R(θ)."""
    import numpy as np

    c, s = math.cos(math.radians(angle_deg)), math.sin(math.radians(angle_deg))
    R = np.array([[c, s], [-s, c]])
    return R.T @ np.diag([lamina.G13, lamina.G23]) @ R


@dataclass(frozen=True)
class Laminate:
    """Plies from the bottom face up."""

    plies: tuple[Ply, ...]

    @property
    def thickness(self) -> float:
        return sum(ply.thickness for ply in self.plies)

    def interfaces(self) -> list[float]:
        """The plies' boundaries, from -t/2 (the bottom face) to t/2."""
        z = [-0.5 * self.thickness]
        for ply in self.plies:
            z.append(z[-1] + ply.thickness)
        z[-1] = 0.5 * self.thickness
        return z

    def abd(self):
        """A, B, D (3 x 3 each, N/mm, N, N mm) by CLT."""
        import numpy as np

        A, B, D = np.zeros((3, 3)), np.zeros((3, 3)), np.zeros((3, 3))
        z = self.interfaces()
        for k, ply in enumerate(self.plies):
            Q = q_bar(ply.lamina, ply.angle_deg)
            A += Q * (z[k + 1] - z[k])
            B += Q * (z[k + 1] ** 2 - z[k] ** 2) / 2.0
            D += Q * (z[k + 1] ** 3 - z[k] ** 3) / 3.0
        return A, B, D

    def shear(self):
        """H (2 x 2, N/mm): the transverse shear stiffness with the shear correction factor."""
        import numpy as np

        H = np.zeros((2, 2))
        for ply in self.plies:
            H += shear_bar(ply.lamina, ply.angle_deg) * ply.thickness
        return SHEAR_CORRECTION * H

    def flipped(self) -> "Laminate":
        """The same laminate seen from its other face: plies in reverse order, angles mirrored."""
        return Laminate(tuple(Ply(p.lamina, -p.angle_deg + 0.0, p.thickness) for p in reversed(self.plies)))

    def density(self) -> float:
        return sum(p.lamina.density * p.thickness for p in self.plies) / self.thickness

    def symmetric(self) -> bool:
        plies = self.plies
        return all(a.lamina == b.lamina and a.angle_deg == b.angle_deg and a.thickness == b.thickness
                   for a, b in zip(plies, reversed(plies)))


def _angle_text(angle: float) -> str:
    text = f"{angle:.4g}"
    return "0" if text in ("0", "-0") else text


def notation(laminate: Laminate) -> str:
    """The layup in the usual short form, bottom ply first: "[0/90]s" for a symmetric one, else "[0/45/-45/90]"."""
    angles = [_angle_text(p.angle_deg) for p in laminate.plies]
    if len(angles) >= 2 and len(angles) % 2 == 0 and laminate.symmetric():
        return f"[{'/'.join(angles[: len(angles) // 2])}]s"
    return f"[{'/'.join(angles)}]"


def tsai_wu(lamina: Lamina, s1, s2, t12):
    """The Tsai-Wu failure index of in-plane ply stresses (MPa, ply axes); 1 is the onset of failure."""
    F1, F2 = 1.0 / lamina.Xt - 1.0 / lamina.Xc, 1.0 / lamina.Yt - 1.0 / lamina.Yc
    F11, F22, F66 = 1.0 / (lamina.Xt * lamina.Xc), 1.0 / (lamina.Yt * lamina.Yc), 1.0 / lamina.S ** 2
    F12 = -0.5 * math.sqrt(F11 * F22)
    return F1 * s1 + F2 * s2 + F11 * s1 * s1 + F22 * s2 * s2 + F66 * t12 * t12 + 2.0 * F12 * s1 * s2


def max_stress(lamina: Lamina, s1, s2, t12):
    """The max-stress failure index: the largest share of a strength any one stress uses."""
    import numpy as np

    along = np.where(np.asarray(s1) >= 0, np.asarray(s1) / lamina.Xt, -np.asarray(s1) / lamina.Xc)
    across = np.where(np.asarray(s2) >= 0, np.asarray(s2) / lamina.Yt, -np.asarray(s2) / lamina.Yc)
    return np.maximum(np.maximum(along, across), np.abs(np.asarray(t12)) / lamina.S)


def parse_layup(document: dict) -> tuple[Laminate, list[dict], tuple[float, float, float] | None]:
    """The study's ``layup`` (plies, bottom first), its ``laminae`` (ply materials by name) and its ``layup_axis``
    (the 0° direction): the laminate, each ply as echoed, and the axis (``None``: the default)."""
    raw = document.get("layup")
    where = "layup"
    if not isinstance(raw, list) or not raw:
        raise ValueError('study.layup: the plies from the bottom face up, like [{"material": "cfrp", "angle_deg": 0, '
                         '"thickness_mm": 0.25}, ...]')
    library = document.get("laminae", {})
    if not isinstance(library, dict):
        raise ValueError(f'study.laminae: the ply materials by name, like {{"cfrp": {_EXAMPLE}}}')
    named = {str(key): lamina_from_spec(value, f"laminae.{key}", str(key)) for key, value in library.items()}
    plies, echo = [], []
    for index, entry in enumerate(raw):
        at = f"{where}[{index}]"
        if not isinstance(entry, dict):
            raise ValueError(f'{at}: expected an object like {{"material": "cfrp", "angle_deg": 45, "thickness_mm": 0.25}}')
        unknown = set(entry) - {"material", "angle_deg", "thickness_mm"}
        if unknown:
            raise ValueError(f"{at}: unknown keys {sorted(unknown)}; a ply takes material, angle_deg and thickness_mm")
        for key in ("material", "angle_deg", "thickness_mm"):
            if key not in entry:
                raise ValueError(f"{at}.{key}: every ply needs its material, its angle_deg and its thickness_mm")
        material = entry["material"]
        if isinstance(material, str):
            if material not in named:
                choices = f"one of {', '.join(sorted(named))}" if named else "none are given"
                raise ValueError(f"{at}.material: {material!r} is not in study.laminae ({choices}); "
                                 f"name it there or give the ply material inline, like {_EXAMPLE}")
            lamina = named[material]
        else:
            lamina = lamina_from_spec(material, f"{at}.material", f"ply {index + 1}")
        angle = _number(entry["angle_deg"], f"{at}.angle_deg")
        if not -180.0 <= angle <= 180.0:
            raise ValueError(f"{at}.angle_deg: an angle from -180 to 180 degrees, got {angle:g}")
        thickness = _number(entry["thickness_mm"], f"{at}.thickness_mm", positive=True)
        plies.append(Ply(lamina, angle, thickness))
        echo.append({"material": lamina.name, "angle_deg": angle, "thickness_mm": thickness})
    axis = None
    if "layup_axis" in document:
        vector = document["layup_axis"]
        if not isinstance(vector, list) or len(vector) != 3:
            raise ValueError("study.layup_axis: the plies' 0° direction as [x, y, z], like [1, 0, 0]")
        components = [_number(c, "layup_axis") for c in vector]
        size = math.sqrt(sum(c * c for c in components))
        if not size > 0:
            raise ValueError("study.layup_axis: the direction is zero")
        axis = tuple(c / size for c in components)
    return Laminate(tuple(plies)), echo, axis  # type: ignore[return-value]


# -- the laminate as a solid: a stiffness per ply by height --------------------------------------------------


@dataclass(frozen=True)
class LayerStack:
    """The plies through a thick plate: the bottom face's height along ``normal``, the ply interfaces above it,
    each ply's 6 x 6 stiffness in global axes and its material directions (fibre, across, normal)."""

    normal: tuple[float, float, float]
    base: float
    heights: tuple[float, ...]
    matrices: tuple = field(repr=False)
    directions: tuple = field(repr=False)

    def ply_index(self, points):
        """Each point's ply (0 is the bottom), by its height above the bottom face, from a (3, ...) array."""
        import numpy as np

        height = np.einsum("i,i...->...", np.asarray(self.normal), points) - self.base
        return np.clip(np.searchsorted(np.asarray(self.heights[1:-1]), height, side="right"), 0, len(self.matrices) - 1)

    def parts(self, points):
        """``[(C, inside)]`` for operators.voigt_parts: each ply's matrix and where (a boolean like ``points[0]``)."""
        index = self.ply_index(points)
        return [(C, index == k) for k, C in enumerate(self.matrices)]


@dataclass(frozen=True)
class LayeredMaterial(Material):
    """A laminate meshed as a solid: one material whose stiffness is each ply's where that ply is."""

    layers: Any = field(default=None, hash=False, compare=False)

    def mirrors_onto_itself(self, axis: int) -> bool:
        """Each ply is its own mirror image about a plane normal to global ``axis`` (an axis of its material frame
        in the plate's plane; a plane across the thickness would turn the stack over, so never that one)."""
        if abs(float(self.layers.normal[axis])) > 1e-9:
            return False
        return all(any(abs(abs(float(d[axis])) - 1.0) < 1e-9 for d in frame) for frame in self.layers.directions)


def layered_material(laminate: Laminate, normal, axis, base: float, name: str) -> LayeredMaterial:
    """The laminate as a :class:`LayeredMaterial` through a plate whose bottom face is at height ``base`` along
    ``normal`` (plies stacked along it), its 0° direction ``axis``."""
    import numpy as np

    from cadgen._internal.fea.operators import orthotropic_matrix

    n = np.asarray(normal, dtype=float)
    x0 = np.asarray(axis, dtype=float)
    y0 = np.cross(n, x0)
    heights, matrices, directions = [0.0], [], []
    for ply in laminate.plies:
        heights.append(heights[-1] + ply.thickness)
        c, s = math.cos(math.radians(ply.angle_deg)), math.sin(math.radians(ply.angle_deg))
        d1, d2 = c * x0 + s * y0, -s * x0 + c * y0
        matrices.append(orthotropic_matrix(ply.lamina.block(d1, d2)))
        directions.append((tuple(d1), tuple(d2), tuple(n)))
    first = laminate.plies[0].lamina
    stack = LayerStack(tuple(float(c) for c in n), float(base), tuple(heights), tuple(matrices), tuple(directions))
    return LayeredMaterial(name, first.E1, first.nu12 if 0 <= first.nu12 < 0.5 else 0.3, None, laminate.density(),
                           layers=stack)
