"""KiCad's stock libraries, for the scripts that copy a symbol or a footprint out of them. The same file in
every ECAD sample.

They are found where the `cad` command finds them for the KiCad it runs (ERC, DRC, the netlist import), so one
setting serves the scripts and KiCad: `symbols/`, `footprints/` and `3dmodels/` side by side, in the folder
whose `3dmodels` `CAD_KICAD_3DMODELS` names, else in an installed KiCad. A variable such as
`KICAD10_SYMBOL_DIR` is not read, as `cad` does not pass it to KiCad.

An installed KiCad keeps a symbol library as one file (`symbols/Device.kicad_sym`); KiCad's library repository,
downloaded, keeps it as a folder, a file a symbol (`symbols/Device.kicad_symdir/R.kicad_sym`). Both are read.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from cad.engine.formats.kicad.models3d import installations, library_roots

VARIABLE = "CAD_KICAD_3DMODELS"


def _places() -> list[Path]:
    """Each folder that may hold KiCad's libraries, in `cad`'s order: the parent of each `3dmodels` folder
    `CAD_KICAD_3DMODELS` names, then each installed KiCad's, newest first."""
    named = [Path(root).parent for root in library_roots() if os.path.normcase(Path(root).name) == "3dmodels"]
    return list(dict.fromkeys([*named, *(Path(place) for place in installations())]))


def find(kind: str) -> Path | None:
    """KiCad's `symbols` or `footprints` folder, or None where there is none."""
    return next((place / kind for place in _places() if (place / kind).is_dir()), None)


def _named(missing: list[str]) -> str:
    """What `CAD_KICAD_3DMODELS` says, and why it did not lead to the `missing` folders."""
    named = [folder for folder in (os.environ.get(VARIABLE) or "").split(os.pathsep) if folder.strip()]
    return ", ".join(
        f"{folder}: " + ("not a folder" if not os.path.isdir(os.path.expanduser(folder))
                         else "not named 3dmodels" if os.path.normcase(Path(folder).name) != "3dmodels"
                         else f"no {'/ or '.join(missing)}/ beside it") for folder in named) or "unset"


def require(*kinds: str) -> None:
    """Stop, in a few lines, where a library folder of `kinds` is not found: before anything is built."""
    missing = [kind for kind in kinds if find(kind) is None]
    if missing:
        sys.exit(
            f"{Path(sys.argv[0]).name}: KiCad's stock libraries were not found ({' and '.join(missing)}).\n"
            f"  looked for  {'/ and '.join(kinds)}/ beside the 3dmodels folder {VARIABLE} names ({_named(missing)}),\n"
            f"              then in an installed KiCad ({', '.join(installations()) or 'none'})\n"
            f"  set         {VARIABLE}=<folder>/3dmodels, where <folder> holds symbols/, footprints/ and 3dmodels/\n"
            "              (3dmodels/ must be there; it may be empty)\n"
            "  get them    install KiCad 10, or download kicad-symbols and kicad-footprints at tag 10.0.8 from\n"
            "              gitlab.com/kicad/libraries (about 25 MB): the commands are in this sample's README.md")


def folder(kind: str) -> Path:
    require(kind)
    return find(kind)


def symbol_file(lib: str, name: str) -> Path:
    """The file that holds symbol `name` of the stock library `lib`: the library's one file, or the symbol's own
    in the library's folder. A symbol that `extends` another finds its parent by the same call."""
    symbols = folder("symbols")
    for path in (symbols / f"{lib}.kicad_sym", symbols / f"{lib}.kicad_symdir" / f"{name}.kicad_sym"):
        if path.is_file():
            return path
    sys.exit(f"{Path(sys.argv[0]).name}: no stock symbol {lib}:{name}: neither {lib}.kicad_sym nor "
             f"{lib}.kicad_symdir/{name}.kicad_sym in {symbols}")


def footprint_file(lib: str, name: str) -> Path:
    """The stock footprint `lib:name`, a `.kicad_mod` in the library's `.pretty` folder."""
    path = folder("footprints") / f"{lib}.pretty" / f"{name}.kicad_mod"
    if not path.is_file():
        sys.exit(f"{Path(sys.argv[0]).name}: no stock footprint {lib}:{name}: {path} is not there")
    return path


def model_file(name: str) -> Path | None:
    """The stock STEP a footprint names (`${KICAD10_3DMODEL_DIR}/<name>`, here without the variable), in the 3D
    libraries the board's 3D view reads; None where none holds it."""
    return next((Path(root) / name for root in library_roots() if (Path(root) / name).is_file()), None)
