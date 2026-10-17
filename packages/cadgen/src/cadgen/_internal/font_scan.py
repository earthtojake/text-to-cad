"""Name the font file that made ``import build123d`` fail.

build123d parses EVERY font in the system font folders at import time:
``build123d/text.py`` ends with ``available_fonts = FontManager().available_fonts``,
whose ``__init__`` calls ``register_system_fonts() -> register_folder() ->
register_font()``, and ``register_font`` hands each file straight to
``fontTools.ttLib.TTFont`` with no per-file guard. One malformed file therefore takes
down ``import build123d`` itself, and with it every cadgen command -- on Windows,
where that scan is the one platform build123d runs it on (OCCT does not pick up user
fonts there).

The failure a user sees is ``TTLibError: Not a TrueType or OpenType font (bad
sfntVersion)``, which names no file. There is nothing to fix here: the guard belongs
in build123d's ``register_folder`` loop, and until it lands the only recovery is to
move the offending file out of the font folder. So this module does the one useful
thing available downstream -- it finds the file and says so.

Deliberately NOT a workaround. Patching around it downstream needs
``fontTools.ttLib.TTFont`` replaced before build123d binds it, and a stand-in that
survives ``_get_font_faces`` would register an empty-named ``Font_SystemFont`` into
OCCT's global font manager. A clear error beats a silently poisoned font table.

Reading four bytes per file, this never parses a font, so it cannot fail the way the
thing it is diagnosing does.
"""

from __future__ import annotations

import os
import platform

# The first four bytes of a valid sfnt container. build123d globs ttf/otf/ttc, so
# these are the tags those extensions can legitimately carry.
_SFNT_MAGIC = (
    b"\x00\x01\x00\x00",  # TrueType outlines
    b"OTTO",              # CFF outlines
    b"true",              # older Apple TrueType
    b"typ1",              # Type 1 in an sfnt wrapper
    b"ttcf",              # TrueType Collection
)

_FONT_EXTENSIONS = (".ttf", ".otf", ".ttc")


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


def unparseable_fonts(dirs: list[str] | None = None) -> list[str]:
    """Font files whose sfnt header is not one build123d's parser can read.

    Non-recursive, matching ``register_folder``'s single-level glob: a file build123d
    never opens is not a file that can have broken the import.
    """
    bad: list[str] = []
    for directory in system_font_dirs() if dirs is None else dirs:
        try:
            names = sorted(os.listdir(directory))
        except OSError:
            continue
        for name in names:
            if not name.lower().endswith(_FONT_EXTENSIONS):
                continue
            path = os.path.join(directory, name)
            try:
                with open(path, "rb") as handle:
                    header = handle.read(4)
            except OSError:
                # Unreadable is a different problem, and build123d would raise its own
                # error for it; only claim the ones we can positively identify.
                continue
            if header not in _SFNT_MAGIC:
                bad.append(path)
    return bad


# build123d's register_folder globs `"*" + ext` with NO dot, so the patterns it passes
# end in a bare "ttf"/"otf"/"ttc". Matching on ".ttf" here silently disables the guard,
# which is exactly how the first version of it did nothing.
_GLOB_PATTERN_SUFFIXES = ("ttf", "otf", "ttc")

_ENV_DISABLE = "CADGEN_FONT_GUARD"

# What OCCT raises when build123d hands its Font_SystemFont an empty name (#636).
_EMPTY_NAME_TEXT = "Font_SystemFont constructor called with empty font name"

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


def _font_parses(path: str) -> bool:
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
    so filtering that one listing keeps an unparseable file from ever being opened --
    the file is skipped, the rest of the folder still registers, and nothing malformed
    reaches OCCT's font table.

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
            if _font_parses(path):
                keep.append(path)
            elif path not in skipped_fonts:
                skipped_fonts.append(path)
        return keep

    guarded_glob._cadgen_font_guard = True  # type: ignore[attr-defined]
    glob.glob = guarded_glob  # type: ignore[assignment]
    return True


def skipped_fonts_warning() -> str:
    """A one-line note for fonts the guard dropped, or "" when it dropped none."""
    if not skipped_fonts:
        return ""
    listed = ", ".join(skipped_fonts[:3])
    more = f" (and {len(skipped_fonts) - 3} more)" if len(skipped_fonts) > 3 else ""
    return (
        f"cadgen skipped {len(skipped_fonts)} unreadable font file(s) so build123d could "
        f"import: {listed}{more}"
    )


def is_font_scan_failure(exc: BaseException) -> bool:
    """True when this exception came out of fontTools, or OCCT refused an empty font name.

    Matched on the exception's defining module rather than by importing fontTools to
    compare classes: this runs on an error path, and importing to diagnose an import
    failure is how a diagnostic becomes a second traceback. OCCT's error is matched on
    its text, since it does not come from fontTools.
    """
    for error in (exc, *_causes(exc)):
        if type(error).__module__.split(".")[0] == "fontTools":
            return True
    return _names_an_empty_font(exc)


def _names_an_empty_font(exc: BaseException) -> bool:
    return any(_EMPTY_NAME_TEXT in str(error) for error in (exc, *_causes(exc)))


def _causes(exc: BaseException) -> list[BaseException]:
    seen: list[BaseException] = []
    current = exc
    while True:
        current = current.__cause__ or current.__context__
        if current is None or current in seen:
            return seen
        seen.append(current)


def font_scan_failure_message(exc: BaseException, dirs: list[str] | None = None) -> str:
    """An actionable message for a font-scan import failure, or "" for anything else."""
    if not is_font_scan_failure(exc):
        return ""

    if _names_an_empty_font(exc):
        return "\n".join([
            "cadgen could not import build123d: a font file on this machine has no family name.",
            "",
            f"  {type(exc).__name__}: {exc}",
            "",
            "OCCT refuses a font with an empty name, so the import fails with it.",
            "",
            "Run this to list the file(s) with no family name:",
            "",
            "  python -m cadgen.check_fonts",
            "",
            "Move them out of the font folder and rerun.",
        ])

    lines = [
        "cadgen could not import build123d: a font file on this machine failed to parse.",
        "",
        f"  {type(exc).__name__}: {exc}",
        "",
        "build123d parses every font in the system font folders when it is imported, and",
        "one unreadable file aborts the import (and so every cadgen command). This is a",
        "build123d bug, not a problem with your model or your install.",
    ]

    bad = unparseable_fonts(dirs)
    if bad:
        lines += ["", "Files with an invalid font header:"]
        lines += [f"  {path}" for path in bad[:10]]
        if len(bad) > 10:
            lines.append(f"  ... and {len(bad) - 10} more")
        lines += [
            "",
            "Move or rename the file(s) above out of the font folder and rerun. They are",
            "not fonts any application can use, so nothing else loses a font by it.",
        ]
    else:
        searched = ", ".join(system_font_dirs() if dirs is None else dirs)
        lines += [
            "",
            f"No file with an invalid header was found in {searched}, so the bad font is",
            "malformed past its first four bytes. This finds it by parsing each one the",
            "way build123d does:",
            "",
            "  python -m cadgen.check_fonts",
        ]
    return "\n".join(lines)
