"""A stand-in OpenSCAD for the package suites: a script named ``openscad`` that takes the command line the
openscad integration gives OpenSCAD (``cad.openscad._render``) and writes what OpenSCAD would -- a small
binary STL and a dependency file naming the program and its includes -- so the library's reader and
operations, the commands and the viewer's route run with no OpenSCAD installed. The real one renders in the
openscad suite alone (``tests/python/packages/openscad``, ``scripts/test/test-openscad.sh``).

The stub says ``OpenSCAD version 2021.01`` to ``--version`` (``--help`` lists no ``--backend``); renders a
12-triangle box of the size the program's first ``cube([x, y, z])`` names (10 x 10 x 10 when none), from the
origin as OpenSCAD's ``cube`` is; says ``Current top level object is not a 3D object.`` and exits 1 for a
program whose first word is ``square`` or ``circle``; exits 1 with ``ERROR: Parser error`` for one holding
``syntax error``; names in the dependency file every file an ``include <...>`` or ``use <...>`` points at,
relative to the program's folder, and the program itself, in Make's format with spaces escaped; and echoes
each ``echo(...)`` of the program as ``ECHO: ...`` on stderr. A shebang script: Windows does not run it, and
the tests that run it say so by name where they skip.
"""

from __future__ import annotations

import os
import stat
import sys
from pathlib import Path

__all__ = ["RUNS", "stub_env", "write_stub"]

#: Whether this platform runs the stub (a shebang script).
RUNS = not sys.platform.startswith("win")

_SCRIPT = r'''#!{python}
"""A stand-in OpenSCAD (tests/python/support/openscad_stub.py)."""
import math
import re
import struct
import sys
from pathlib import Path


def main(argv):
    if "--version" in argv:
        print("OpenSCAD version 2021.01")
        return 0
    if "--help" in argv:
        print("Usage: openscad [options] file.scad\n  -o [ --o ] arg  output specified file\n"
              "  --export-format arg  overrides format\n  -d [ --d ] arg  deps_file")
        return 0
    out = deps = None
    files = []
    it = iter(argv)
    for arg in it:
        if arg == "-o":
            out = next(it)
        elif arg == "-d":
            deps = next(it)
        elif arg == "--export-format":
            next(it)
        elif arg.startswith("--"):
            continue
        else:
            files.append(arg)
    if not files or out is None:
        print("Can't open input file!", file=sys.stderr)
        return 1
    program = Path(files[0])
    try:
        text = program.read_text(encoding="utf-8")
    except OSError:
        print(f"Can't open input file '{{program}}'!", file=sys.stderr)
        return 1
    for line in re.findall(r"echo\((.*?)\);", text):
        print(f"ECHO: {{line}}", file=sys.stderr)
    if "syntax error" in text:
        print(f"ERROR: Parser error: syntax error in file {{program.name}}, line 1", file=sys.stderr)
        print(f"Can't parse file '{{program}}'!", file=sys.stderr)
        return 1
    first = re.search(r"\b(cube|square|circle|cylinder|sphere|difference|union|translate)\b", text)
    includes = [program.parent / name for name in re.findall(r"(?:include|use)\s*<([^>]+)>", text)]
    if deps is not None:
        lines = [f"{{out}}: \\"] + [f"\t{{str(path).replace(' ', chr(92) + ' ')}} \\" for path in includes]
        lines.append(f"\t{{str(program).replace(' ', chr(92) + ' ')}}")
        Path(deps).write_text("\n".join(lines) + "\n", encoding="utf-8")
    if first and first.group(1) in ("square", "circle"):
        print("   Top level object is a 2D object:\n   Contours:        1\nCurrent top level object is not a 3D object.",
              file=sys.stderr)
        return 1
    size = re.search(r"cube\(\s*\[\s*([\d.]+)\s*,\s*([\d.]+)\s*,\s*([\d.]+)\s*\]", text)
    x, y, z = (float(size.group(1)), float(size.group(2)), float(size.group(3))) if size else (10.0, 10.0, 10.0)
    corners = [(0, 0, 0), (x, 0, 0), (x, y, 0), (0, y, 0), (0, 0, z), (x, 0, z), (x, y, z), (0, y, z)]
    faces = [(0, 2, 1), (0, 3, 2), (4, 5, 6), (4, 6, 7), (0, 1, 5), (0, 5, 4),
             (1, 2, 6), (1, 6, 5), (2, 3, 7), (2, 7, 6), (3, 0, 4), (3, 4, 7)]
    data = bytearray(b"OpenSCAD Model".ljust(80, b"\0")) + struct.pack("<I", len(faces))
    for a, b, c in faces:
        pa, pb, pc = corners[a], corners[b], corners[c]
        u = [pb[i] - pa[i] for i in range(3)]
        v = [pc[i] - pa[i] for i in range(3)]
        n = [u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0]]
        length = math.sqrt(sum(value * value for value in n)) or 1.0
        data += struct.pack("<3f", *(value / length for value in n))
        for point in (pa, pb, pc):
            data += struct.pack("<3f", *point)
        data += struct.pack("<H", 0)
    Path(out).write_bytes(bytes(data))
    print("   Top level object is a 3D object:\n   Facets:         12", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
'''


def write_stub(folder: Path | str, name: str = "openscad") -> Path:
    """The stub written as ``folder/<name>``, executable; its path."""
    path = Path(folder) / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_SCRIPT.format(python=sys.executable), encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return path


def stub_env(path: Path | str) -> dict[str, str]:
    """The environment that names the stub as the OpenSCAD to run (``CAD_OPENSCAD``)."""
    return {**os.environ, "CAD_OPENSCAD": str(path)}
