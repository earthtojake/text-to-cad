"""How far along a drawing is and whose conventions it follows: its stage and
its profile.

The stage (concept, prototype, production) is the same everywhere: it says how
much the drawing must define, and the completeness report checks each sheet
against it. A profile is a company's or an industry's conventions: the
tolerancing standard its drawings are read by, its own names for the stages,
the extra title-block cells it asks for and the letters that mark a key
characteristic. A profile carries conventions, never numbers: every value that prints as a
requirement is the person's.

Part of :mod:`cadgen.eng_drawing`; nothing here imports the kernel or ezdxf at
module scope.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

STAGES = ("concept", "prototype", "production")
#: How each stage reads in the title block's STAGE cell. A concept drawing says
#: outright that nobody should make parts from it.
_STAGE_LABELS = {"concept": "CONCEPT, NOT FOR MANUFACTURE", "prototype": "PROTOTYPE", "production": "PRODUCTION"}
#: The tolerancing standards a profile follows, one per drawing: ISO 8015 reads
#: each tolerance on its own, where Y14.5's Rule #1 lets a size limit control
#: form, so a drawing that mixes them cannot be read either way.
STANDARDS = ("ISO GPS", "ASME Y14.5-2018")
#: Each standard's note that the drawing is read by it.
_STANDARD_NOTES = {"ISO GPS": "TOLERANCING ISO 8015.",
                   "ASME Y14.5-2018": "DIMENSIONS AND TOLERANCES PER ASME Y14.5-2018."}
#: Each standard's general tolerance note around the person's words: ISO names a
#: general tolerance standard and class ("ISO 2768-m"), a Y14.5 drawing states its
#: values ("±0.1"). A sheet with no profile reads as ISO, as its title block does.
_GENERAL_TOLERANCE_NOTES = {"ISO GPS": "TOLERANCES PER {} UNLESS OTHERWISE SPECIFIED.",
                            "ASME Y14.5-2018": "UNLESS OTHERWISE SPECIFIED, TOLERANCES ARE {}."}
#: Words in a general tolerance that belong to the other standard.
_OTHER_STANDARD = {"ISO GPS": ("ASME", "Y14.5"), "ASME Y14.5-2018": ("ISO 2768", "ISO 22081", "ISO 8015")}
#: The extra cells a profile may add share the title block's top band with
#: COMPANY and STAGE, so only a few fit.
_MOST_FIELDS = 3


@dataclass(frozen=True)
class Profile:
    """A company's or an industry's drawing conventions.

    ``categories`` maps the company's own names for its drawing categories to
    the stages they mean (``{"TYPE B": "production"}``); a sheet given one of
    them prints it in place of the stage. ``fields`` names extra title-block
    cells (``"CAGE CODE"``), filled per sheet from ``Sheet(fields=...)`` and
    blank until then. ``characteristic_mark`` is the boxed letters that mark a
    key characteristic: AS9103 leaves the symbol to the customer. A company's
    own conventions are one of these: ``Profile("ACME", "ASME Y14.5-2018",
    fields=("CAGE CODE",))``."""

    name: str
    standard: str
    categories: Mapping[str, str] = field(default_factory=dict)
    fields: tuple[str, ...] = ()
    characteristic_mark: str = "KC"

    def __post_init__(self) -> None:
        if self.standard not in STANDARDS:
            raise ValueError(f"unknown standard {self.standard!r}; one of {', '.join(STANDARDS)}")
        for category, stage in self.categories.items():
            if stage not in STAGES:
                raise ValueError(f"category {category!r} maps to {stage!r}; a category names one of the stages "
                                 f"{', '.join(STAGES)}")
        object.__setattr__(self, "categories", dict(self.categories))
        if isinstance(self.fields, str):
            raise TypeError(f"fields is a sequence of cell names, fields=({self.fields!r},) for one")
        object.__setattr__(self, "fields", tuple(self.fields))
        if (len(set(self.fields)) != len(self.fields) or len(self.fields) > _MOST_FIELDS
                or not all(isinstance(f, str) and f.strip() and f == f.upper() for f in self.fields)):
            raise ValueError(f"fields are up to {_MOST_FIELDS} different upper-case cell names, got {self.fields!r}")
        mark = self.characteristic_mark
        if not (isinstance(mark, str) and 1 <= len(mark) <= 3 and mark.isalnum() and mark == mark.upper()):
            raise ValueError(f"characteristic_mark is one to three upper-case letters or digits, got {mark!r}")


#: ISO GPS: ISO 2768 or ISO 22081 general tolerances, ISO 1101 frames, the
#: ISO 7200 sheet the drawing already is.
GENERIC = Profile("GENERIC", "ISO GPS", {})


def _standard_note(profile: Profile | None) -> list[str]:
    """The note naming the standard a profile's drawing is read by; none without one."""
    return [_STANDARD_NOTES[profile.standard]] if profile is not None else []


def _general_tolerance_note(profile: Profile | None, tolerance: str) -> str:
    return _GENERAL_TOLERANCE_NOTES[profile.standard if profile is not None else "ISO GPS"].format(tolerance)


def _check_general_tolerance(profile: Profile | None, tolerance: str) -> None:
    """Refuse a general tolerance from the standard the profile does not follow."""
    if profile is None or not tolerance:
        return
    other = next((word for word in _OTHER_STANDARD[profile.standard] if word in tolerance.upper()), None)
    if other is not None:
        raise ValueError(f"general_tolerance={tolerance!r} is {other}'s, and the {profile.name} profile follows "
                         f"{profile.standard}; one drawing is read by one standard")
