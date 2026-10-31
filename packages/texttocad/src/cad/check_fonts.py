"""Find the font file that breaks ``import build123d``.

build123d parses every font in the system font folders at import time and has no
per-file guard, so one malformed file aborts the import and every cad command with
it. The resulting error names no file. This parses the same folders the same way and
prints the ones that fail.

Run: python -m cad.check_fonts [DIR ...]

Exits 0 when every font parses, 1 when any file fails, 2 when fontTools is missing.
Reads fonts and nothing else -- it never moves or edits a file, because the folder it
is pointed at on Windows is a system folder.
"""

from __future__ import annotations

import os
import sys

from cad._internal.font_scan import family_name, system_font_dirs


def _font_paths(directory: str) -> list[str]:
    """The files build123d's ``register_folder`` would open.

    Listed with ``os.listdir`` and NOT ``glob.glob``, which is the whole point: cadgen
    installs a guard over ``glob.glob`` that hides the fonts build123d cannot register,
    so it can import. A checker built on the filtered listing would report a clean
    folder on precisely the machine it exists to diagnose.
    """
    try:
        names = os.listdir(os.path.normpath(directory))
    except OSError:
        return []
    return sorted(
        os.path.join(os.path.normpath(directory), name)
        for name in names
        if name.lower().endswith((".ttf", ".otf", ".ttc"))
    )


def check(dirs: list[str] | None = None) -> list[tuple[str, str]]:
    """Parse every font in `dirs`; return (path, error) for each one build123d cannot use.

    A font with no family name is one too (#636).

    The name table is read, not just the file opened. ``TTFont(path)`` is lazy: it
    validates the sfnt header and defers the tables, so a file with a plausible
    header but a broken table directory constructs fine here and then fails inside
    build123d's ``_get_font_faces``, whose first act is ``ft_font["name"].names``. A
    check that stopped at construction would report a clean sweep on exactly the
    machine that cannot import build123d.
    """
    from fontTools.ttLib import TTFont, ttCollection

    failures: list[tuple[str, str]] = []
    for directory in dirs or system_font_dirs():
        for path in _font_paths(directory):
            try:
                if os.path.splitext(path)[1].strip(".").lower() == "ttc":
                    fonts = list(ttCollection.TTCollection(path))
                else:
                    fonts = [TTFont(path)]
                for font in fonts:
                    if not family_name(font):
                        failures.append((path, "no family name, which OCCT refuses"))
                        break
            except Exception as exc:  # noqa: BLE001 - reporting, not handling
                failures.append((path, f"{type(exc).__name__}: {exc}"))
    return failures


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    dirs = argv or system_font_dirs()

    try:
        failures = check(dirs)
    except ImportError:
        sys.stderr.write(
            "fontTools is not installed, so the fonts cannot be checked.\n"
            "Install the CAD requirements first: pip install 'texttocad[kernel]'\n"
        )
        return 2

    sys.stdout.write(f"Checked fonts in: {', '.join(dirs)}\n")
    if not failures:
        sys.stdout.write("Every font is usable by build123d; none of them breaks the import.\n")
        return 0

    sys.stdout.write(f"\n{len(failures)} font file(s) build123d cannot use:\n")
    for path, error in failures:
        sys.stdout.write(f"  {path}\n      {error}\n")
    sys.stdout.write(
        "\nMove or rename these out of the font folder and rerun. build123d parses\n"
        "every font when it is imported, so one unreadable file blocks every cad\n"
        "command until it is out of the way.\n"
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
