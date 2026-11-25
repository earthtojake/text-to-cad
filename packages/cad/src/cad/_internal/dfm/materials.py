"""The materials a check's ``--material`` names, and the class each belongs to.

A rule whose limit differs by material reads the material's class (``metal``, ``plastic``) or the
material's own name (a resin's wall range, its clamp pressure). Names are lowercase; each takes its
common spellings as aliases. A material the table does not know is refused by name, with the list.

A part's declared material (``part.material = metals.aluminum()``, a ``bd_materials.FinishedMaterial`` the
document keeps) names the table's material too (``declared``): its family (``aluminum``, ``mild_steel``,
``PETG``), else the first word of its name (``Alu_G6061_T6``), so a check given no ``--material`` judges
by what the model says the part is made of.
"""

from __future__ import annotations

from cad._internal.refused import ArgumentRefused

__all__ = ["CLASSES", "MATERIALS", "declared", "material_class", "resolve"]

#: Each material, its class and the spellings it is also given.
MATERIALS: dict[str, tuple[str, tuple[str, ...]]] = {
    # metals
    "aluminum": ("metal", ("aluminium", "al", "6061", "6061-t6", "7075", "5052", "al6061", "al5052")),
    "steel": ("metal", ("mild_steel", "mild-steel", "carbon_steel", "1018", "a36", "cold_rolled_steel", "crs", "4130",
                        "chromoly", "4130_chromoly")),
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
#: bd_materials' families and name stems the table knows under another name.
_FAMILIES = {"mild_steel": "steel", "alloy_steel": "steel", "tool_steel": "steel", "spring_steel": "steel",
             "mildsteel": "steel", "alloysteel": "steel", "toolsteel": "steel", "springsteel": "steel",
             "alu": "aluminum", "pa": "nylon", "pet": "petg"}


def resolve(name: str | None) -> str | None:
    """The table's name for ``name`` (None for None); ``ValueError`` listing the known ones."""
    if name is None:
        return None
    found = _ALIASES.get(name.strip().lower().replace(" ", "_"))
    if found is None:
        raise ArgumentRefused(f"--material is one of {', '.join(MATERIALS)}, not {name!r}")
    return found


def material_class(name: str | None) -> str | None:
    """``metal`` or ``plastic`` for a material the table knows, None for none."""
    resolved = resolve(name)
    return MATERIALS[resolved][0] if resolved else None


def declared(material: object) -> str | None:
    """The table's name for a part's declared material (a ``bd_materials.FinishedMaterial``: its
    ``.material.family``, else the first word of its ``.name``), None for no material or one the table has no
    name for (wood, glass, a custom material)."""
    if material is None:
        return None
    physics = getattr(material, "material", None)
    for candidate in (getattr(physics, "family", None), getattr(material, "name", None),
                      getattr(physics, "name", None)):
        if not isinstance(candidate, str) or not candidate:
            continue
        stem = candidate.strip().lower().replace("-", "_")
        for key in (stem, stem.split("_")[0]):
            found = _ALIASES.get(_FAMILIES.get(key, key))
            if found is not None:
                return found
    return None
