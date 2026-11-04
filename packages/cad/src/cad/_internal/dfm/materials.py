"""The materials a check's ``--material`` names, and the class each belongs to.

A rule whose limit differs by material reads the material's class (``metal``, ``plastic``) or the
material's own name (a resin's wall range, its clamp pressure). Names are lowercase; each takes its
common spellings as aliases. A material the table does not know is refused by name, with the list.
"""

from __future__ import annotations

__all__ = ["CLASSES", "MATERIALS", "material_class", "resolve"]

#: Each material, its class and the spellings it is also given.
MATERIALS: dict[str, tuple[str, tuple[str, ...]]] = {
    # metals
    "aluminum": ("metal", ("aluminium", "al", "6061", "6061-t6", "7075", "5052", "al6061", "al5052")),
    "steel": ("metal", ("mild_steel", "mild-steel", "carbon_steel", "1018", "a36", "cold_rolled_steel", "crs")),
    "stainless": ("metal", ("stainless_steel", "stainless-steel", "ss", "304", "316", "ss304", "ss316", "316l")),
    "brass": ("metal", ("c360",)),
    "copper": ("metal", ("c110", "c101")),
    "titanium": ("metal", ("ti", "ti6al4v", "ti-6al-4v", "grade5")),
    "galvanized": ("metal", ("galvanized_steel", "galvanised")),
    # plastics
    "abs": ("plastic", ()),
    "pc": ("plastic", ("polycarbonate",)),
    "pc_abs": ("plastic", ("pc-abs", "pcabs")),
    "pp": ("plastic", ("polypropylene",)),
    "pe": ("plastic", ("polyethylene",)),
    "hdpe": ("plastic", ("high_density_polyethylene",)),
    "ldpe": ("plastic", ("low_density_polyethylene",)),
    "pps": ("plastic", ("polyphenylene_sulfide",)),
    "pu": ("plastic", ("polyurethane", "pur")),
    "lft": ("plastic", ("long_fiber_reinforced", "long-fiber", "lfrt")),
    "nylon": ("plastic", ("pa", "pa6", "pa66", "pa12", "polyamide")),
    "nylon_gf": ("plastic", ("pa-gf", "glass_filled_nylon", "pa6-gf30", "nylon-gf")),
    "pom": ("plastic", ("acetal", "delrin")),
    "pmma": ("plastic", ("acrylic",)),
    "ps": ("plastic", ("polystyrene", "hips")),
    "peek": ("plastic", ()),
    "pei": ("plastic", ("ultem",)),
    "pbt": ("plastic", ()),
    "pvc": ("plastic", ()),
    "tpu": ("plastic", ("tpe", "lcp_free_tpe")),
    "pla": ("plastic", ()),
    "petg": ("plastic", ("pet",)),
    "lcp": ("plastic", ()),
    "ptfe": ("plastic", ("teflon",)),
}
CLASSES = ("metal", "plastic")
_ALIASES = {alias: name for name, (_, aliases) in MATERIALS.items() for alias in (name, *aliases)}


def resolve(name: str | None) -> str | None:
    """The table's name for ``name`` (None for None); ``ValueError`` listing the known ones."""
    if name is None:
        return None
    found = _ALIASES.get(name.strip().lower().replace(" ", "_"))
    if found is None:
        raise ValueError(f"--material is one of {', '.join(MATERIALS)}, not {name!r}")
    return found


def material_class(name: str | None) -> str | None:
    """``metal`` or ``plastic`` for a material the table knows, None for none."""
    resolved = resolve(name)
    return MATERIALS[resolved][0] if resolved else None
