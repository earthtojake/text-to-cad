"""No source file carries a NUL byte, so every source file stays greppable.

This shipped. A group-key sentinel in the GLB writer was written as the raw byte
``0x00`` instead of the escape ``\\0``, which turned
``packages/cadgen-js/src/lib/glb/writeGlb.js`` from UTF-8 text into a binary
file. The consequences are all silence:

* ``rg`` skips binary files, so every later search of the module that writes
  every GLB the product ships returned nothing — for a developer and for an
  agent alike, the code simply did not exist;
* ``grep`` prints ``Binary file ... matches`` and no line numbers;
* ``git diff`` renders the byte as a blank space, so the line reads as a
  harmless leading-space sentinel in review;
* bundlers escape it on the way out, so the packaged runtime is correct and no
  behavioural test can fail.

Nothing else in the suite can see it, which is why it is policy-checked here.
The fix is always to write the escape sequence the language already has, or to
pick a sentinel that is not a control character.
"""

from __future__ import annotations

import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]

# The trees we author. Generated bundles under them are in scope on purpose: a
# raw byte reaching one of those is the same loss of greppability.
ROOTS = ("apps", "packages", "scripts", "skills", "tests")

# Suffixes whose files are TEXT by definition. Anything else in these trees may
# legitimately be binary (a font, an icon, a fixture), and guessing which is
# which is how a policy check starts failing on someone's PNG.
TEXT_SUFFIXES = {
    ".c", ".cjs", ".css", ".h", ".html", ".js", ".json", ".jsx", ".md", ".mjs",
    ".py", ".sh", ".svg", ".toml", ".ts", ".tsx", ".txt", ".yaml", ".yml",
}

SKIP_DIRS = {".git", "__pycache__", "node_modules", ".venv", ".vite", "dist", "build"}


def _sources() -> list[Path]:
    found: list[Path] = []
    for root in ROOTS:
        base = REPO_ROOT / root
        if not base.is_dir():
            continue
        for path in base.rglob("*"):
            if path.suffix.lower() not in TEXT_SUFFIXES:
                continue
            if SKIP_DIRS.intersection(path.parts):
                continue
            if path.is_file():
                found.append(path)
    return sorted(found)


class SourceFilesAreText(unittest.TestCase):
    def test_no_source_file_contains_a_nul_byte(self):
        offenders = []
        for path in _sources():
            data = path.read_bytes()
            index = data.find(b"\x00")
            if index >= 0:
                offenders.append(f"{path.relative_to(REPO_ROOT)} (byte {index})")
        self.assertEqual(
            [],
            offenders,
            "a raw NUL makes the file binary to grep and invisible in review; "
            "write the language's escape instead:\n  " + "\n  ".join(offenders),
        )


if __name__ == "__main__":
    unittest.main()
