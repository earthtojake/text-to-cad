"""Keep the fonts build123d cannot register out of the scan ``import build123d`` runs.

build123d registers EVERY font in the system font folders at import time:
``build123d/text.py`` ends with ``available_fonts = FontManager().available_fonts``,
whose ``__init__`` calls ``register_system_fonts() -> register_folder() ->
register_font()``, and ``register_font`` hands each file straight to
``fontTools.ttLib.TTFont`` with no per-file guard. One malformed file, or one font with
no family name (whose empty name OCCT refuses, #636), therefore takes down
``import build123d`` itself, and with it every cadgen command -- on Windows, where that
scan is the one platform build123d runs it on (OCCT does not pick up user fonts there).

``install_font_guard`` hides such a file from the one folder listing build123d makes;
``python -m cad.check_fonts`` names it. The permanent fix belongs upstream, in
``register_folder``.
"""

from __future__ import annotations

import os
import platform


def system_font_dirs() -> list[str]:
    """The folders build123d scans, mirrored from ``register_system_fonts``.

    Kept in the same order so the report matches the order the scan would hit them.
    ``os.getlogin()`` is what build123d uses for the per-user Windows folder; it
    raises with no controlling terminal, so the fallback keeps the diagnostic alive
    where the thing it describes still runs.
    """
    if platform.system() == "Windows":
        try:
            user = os.getlogin()
        except OSError:
            user = os.environ.get("USERNAME", "")
        dirs = ["C:/Windows/Fonts"]
        if user:
            dirs.append(f"C:/Users/{user}/AppData/Local/Microsoft/Windows/Fonts")
        return dirs
    if platform.system() == "Darwin":
        return ["/System/Library/Fonts", "/Library/Fonts"]
    return ["/system/fonts", "/usr/share/fonts", "/usr/local/share/fonts"]


# build123d's register_folder globs `"*" + ext` with NO dot, so the patterns it passes
# end in a bare "ttf"/"otf"/"ttc". Matching on ".ttf" here silently disables the guard,
# which is exactly how the first version of it did nothing.
_GLOB_PATTERN_SUFFIXES = ("ttf", "otf", "ttc")

_ENV_DISABLE = "CADGEN_FONT_GUARD"

skipped_fonts: list[str] = []


def family_name(font) -> str:
    """The family name build123d registers a font under, or "" when it has none.

    Follows ``_get_font_faces`` in build123d/text.py: the first decodable, non-empty
    nameID 16 (preferred family), else the first decodable, non-empty nameID 1. The empty
    check runs on the raw value and the strip comes last, as there, so a blank preferred
    name is "" even when nameID 1 has one. OCCT refuses an empty name, which is #636.
    """
    family = ""
    preferred = ""
    for record in font["name"].names:
        try:
            value = record.toUnicode()
        except UnicodeDecodeError:
            continue
        if record.nameID == 1 and family == "":
            family = value
        elif record.nameID == 16 and preferred == "":
            preferred = value
    return (preferred if preferred != "" else family).strip()


def _font_registers(path: str) -> bool:
    """Whether build123d could register this file: it parses, and every face has a name.

    The name table is read, not just the file opened: ``TTFont`` is lazy, so a broken
    table directory behind a valid sfnt header constructs fine and fails later, inside
    ``_get_font_faces``, whose first act is ``ft_font["name"].names``. A face with no
    family name fails there too, when OCCT is handed its empty name.
    """
    try:
        from fontTools.ttLib import TTFont, ttCollection
    except ImportError:
        # No fontTools means no font scan to protect; let everything through.
        return True
    try:
        if os.path.splitext(path)[1].strip(".").lower() == "ttc":
            fonts = list(ttCollection.TTCollection(path))
        else:
            fonts = [TTFont(path)]
        for font in fonts:
            if not family_name(font):
                return False
    except Exception:  # noqa: BLE001 - any parse failure is one build123d would hit
        return False
    return True


def install_font_guard() -> bool:
    """Hide fonts build123d cannot register from the scan it runs at import time.

    ``register_folder`` lists a folder with ``glob.glob`` and hands every result
    straight to ``fontTools``. ``glob`` is resolved on the module object at call time,
    so filtering that one listing keeps a file build123d cannot register from ever being
    opened -- the file is skipped, the rest of the folder still registers, and neither a
    malformed font nor an empty name reaches OCCT's font table.

    This is the seam because it is the only point between "list the files" and "open
    one". Replacing ``TTFont`` instead cannot work: a stand-in has to survive
    ``_get_font_faces``, and one with an empty name table registers an empty-named
    ``Font_SystemFont`` into OCCT's global manager.

    Returns True when the guard is installed. Idempotent, and a no-op when
    ``CADGEN_FONT_GUARD=0``.
    """
    if os.environ.get(_ENV_DISABLE) == "0":
        return False

    import glob

    if getattr(glob.glob, "_cadgen_font_guard", False):
        return True

    real_glob = glob.glob

    def guarded_glob(pathname, *args, **kwargs):
        results = real_glob(pathname, *args, **kwargs)
        # One string check for every other glob in the process. Only a font listing
        # pays for a parse, and only build123d asks for one.
        if not str(pathname).lower().endswith(_GLOB_PATTERN_SUFFIXES):
            return results
        keep = []
        for path in results:
            if _font_registers(path):
                keep.append(path)
            elif path not in skipped_fonts:
                skipped_fonts.append(path)
        return keep

    guarded_glob._cadgen_font_guard = True  # type: ignore[attr-defined]
    glob.glob = guarded_glob  # type: ignore[assignment]
    return True
