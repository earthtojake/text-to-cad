"""A KiCad file a sample's scripts write is build output, never committed.

A folder of `models/` that holds a `build.py` makes its KiCad project with it (`cad run build.py`): every file that
build writes is listed in GENERATED, kept out of Git by the folder's `.gitignore`, and never tracked, so the board
can never drift from the scripts that make it. The name is that convention's alone: only tracked paths are read
here, and a generator's KiCad files are untracked, so a `build.py` is taken for one whatever it builds, and a script
under `models/` that builds anything else takes another name. Any other KiCad file such a folder tracks is source, listed in
SOURCE with the reason no script makes it. A board no script makes (a folder without a `build.py`) is source, and
nothing here looks at it.
"""

from __future__ import annotations

import re
import subprocess
import unittest
from collections.abc import Iterable, Mapping

from tests.python.support.paths import REPO_ROOT

KICAD_FILE = re.compile(r"(?:\.kicad_(?:pcb|sch|pro|dru|sym|mod|prl|wks)|(?:^|/)(?:fp|sym)-lib-table)$")
BUILD = "build.py"

# The folder of each sample with a build.py -> what its build writes, relative to it (a name ending in `/`, a
# folder and everything in it).
GENERATED: dict[str, tuple[str, ...]] = {
    "models/electronics/macropad": (
        "macropad.kicad_pcb", "macropad.kicad_pro", "macropad.kicad_dru", "macropad.kicad_sch", "usb_power.kicad_sch",
        "mcu.kicad_sch", "keys.kicad_sch", "macropad.pretty/"),
    "models/electronics/eurorack_lfo": (
        "twin_orbit.kicad_pcb", "twin_orbit.kicad_sch", "lfo.kicad_sch", "power.kicad_sch", "twin_orbit.pretty/",
        "fp-lib-table", "sym-lib-table"),
    "models/electronics/orbit_clock": (
        "orbit.kicad_pcb", "orbit.kicad_pro", "orbit.kicad_sch", "power.kicad_sch", "mcu.kicad_sch",
        "minutes.kicad_sch", "hours.kicad_sch", "orbit.kicad_sym", "power.kicad_sym", "orbit.pretty/",
        "fp-lib-table", "sym-lib-table"),
    "models/electronics/pinball/board": (
        "pinball.kicad_pcb", "pinball.kicad_pro", "pinball.kicad_dru", "pinball.kicad_sch", "power.kicad_sch",
        "mcu.kicad_sch", "inputs.kicad_sch", "lighting.kicad_sch", "flippers.kicad_sch", "audio.kicad_sch",
        "pinball.kicad_sym", "power.kicad_sym", "pinball.pretty/", "fp-lib-table", "sym-lib-table"),
}

# A KiCad file tracked in a folder with a build.py -> why no script makes it.
SOURCE: dict[str, str] = {
    "models/electronics/macropad/fp-lib-table":
        "the project's footprint library table, written by hand: no script writes it, and the build reads it",
    "models/electronics/macropad/sym-lib-table":
        "the project's symbol library table, written by hand: no script writes it, and ERC reads it",
    "models/electronics/eurorack_lfo/twin_orbit.kicad_pro":
        "the board's rules and netclasses, set by hand: no script writes them, and KiCad makes the board beside it",
}


def _covers(folder: str, name: str, path: str) -> bool:
    target = f"{folder}/{name}"
    return path.startswith(target) if name.endswith("/") else path == target


def violations(tracked: Iterable[str], generated: Mapping[str, Iterable[str]] = GENERATED,
               source: Mapping[str, str] = SOURCE) -> list[str]:
    """What breaks the rule in `tracked` (every tracked path): a folder with a build.py GENERATED does not list, an
    entry with no build.py, a generated file tracked, a KiCad file in a generator's folder SOURCE does not excuse,
    and a SOURCE entry that excuses nothing or says nothing."""
    tracked = sorted(tracked)
    broken = []
    builders = {path[: -len(BUILD) - 1] for path in tracked if path.endswith(f"/{BUILD}")}
    for folder in sorted(builders - set(generated)):
        broken.append(f"{folder}: has a {BUILD}, the name of a KiCad sample's build under models/: list the KiCad "
                      f"files it writes in GENERATED, or give a script that builds no KiCad project another name")
    for folder in sorted(set(generated) - builders):
        broken.append(f"{folder}: listed in GENERATED, but no {BUILD} is tracked there")
    for path, why in sorted(source.items()):
        if not why.strip():
            broken.append(f"{path}: a source file names no reason")
        if path not in tracked:
            broken.append(f"{path}: listed as source, but not tracked; remove the entry")
    for path in tracked:
        folder = next((f for f in generated if path.startswith(f + "/")), None)
        if folder is None:
            continue
        if any(_covers(folder, name, path) for name in generated[folder]):
            broken.append(f"{path}: written by {folder}/{BUILD}, so build output: untrack it (git rm --cached)")
        elif KICAD_FILE.search(path) and path not in source:
            broken.append(f"{path}: a KiCad file beside {folder}/{BUILD}; list it in GENERATED if the build "
                          "writes it, else in SOURCE with why no script makes it")
    return broken


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=REPO_ROOT, capture_output=True, text=True, check=True).stdout


class GeneratedKicadFilesUntrackedTest(unittest.TestCase):
    def test_no_generated_kicad_file_is_tracked(self) -> None:
        self.assertEqual(violations(path for path in git("ls-files", "-z", "models").split("\0") if path), [])

    def test_every_generated_kicad_file_is_ignored(self) -> None:
        paths = [f"{folder}/{name}x.kicad_mod" if name.endswith("/") else f"{folder}/{name}"
                 for folder, names in GENERATED.items() for name in names]
        ignored = set(git("check-ignore", "--no-index", "--", *paths).split())
        self.assertEqual([path for path in paths if path not in ignored], [])

    def test_the_rule_refuses_what_it_names(self) -> None:
        generated = {"m/a": ("a.kicad_pcb", "a.pretty/"), "m/gone": ("g.kicad_pcb",)}
        source = {"m/a/a.kicad_pro": "set by hand", "m/a/fp-lib-table": " ", "m/a/old.kicad_dru": "none left"}
        tracked = ["models/x/build.py", "m/a/build.py", "m/a/a.kicad_pcb", "m/a/a.pretty/R.kicad_mod",
                   "m/a/a.kicad_pro", "m/a/fp-lib-table", "m/a/b.kicad_sch", "m/a/notes.md", "m/b/b.kicad_pcb"]
        broken = [message.split(":")[0] for message in violations(tracked, generated, source)]
        # A builder unlisted, a listed folder with no builder, a reason left blank, a source entry with no file, the
        # generated files tracked, a KiCad file neither generated nor source; a board with no builder is not looked at.
        self.assertEqual(broken, ["models/x", "m/gone", "m/a/fp-lib-table", "m/a/old.kicad_dru", "m/a/a.kicad_pcb",
                                  "m/a/a.pretty/R.kicad_mod", "m/a/b.kicad_sch"])


if __name__ == "__main__":
    unittest.main()
