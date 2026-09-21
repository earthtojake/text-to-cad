"""Every cadgen source parses on the OLDEST Python the wheel says it supports.

This shipped. ``cadgen/cli/store.py`` printed a clause with an f-string nesting
the same quote character inside its replacement field -- syntax PEP 701 made
legal in 3.12 and nothing earlier. CI runs 3.12, so every test passed; the
wheel declares ``requires-python >= 3.11``, so ``pip install cadgen`` succeeded
on 3.11 and then ``cadgen store why`` died with a SyntaxError at import.

Nothing behavioural can catch this, because the interpreter running the suite
is the interpreter that accepts the syntax. So it is policy-checked here:
``ast.parse(..., feature_version=...)`` asks the CURRENT interpreter to parse
with an older grammar, which is exactly the question "would the floor accept
this file?".

The floor is read from the package's own ``requires-python``, so raising the
declared minimum automatically relaxes this check -- the two can never
disagree.
"""

from __future__ import annotations

import ast
import re
import sys
import tomllib
import unittest
from pathlib import Path

from tests.python.support.paths import repo_path

CADGEN_ROOT = repo_path("packages/cadgen")
CADGEN_SRC = CADGEN_ROOT / "src"

# ast.parse only honours feature_version back to 3.7, and only forward to the
# running interpreter. A floor outside that window is not a failure of the
# sources, so the test says so rather than pretending to have checked.
_OLDEST_SUPPORTED_FEATURE_VERSION = (3, 7)


def _declared_floor() -> tuple[int, int]:
    """The (major, minor) of the package's declared ``requires-python``."""
    metadata = tomllib.loads((CADGEN_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    requires = metadata["project"]["requires-python"]
    match = re.search(r">=\s*(\d+)\.(\d+)", requires)
    if not match:
        raise AssertionError(
            f"cadgen's requires-python ({requires!r}) has no '>=<major>.<minor>' floor; "
            "this check needs one to know which grammar to parse against",
        )
    return int(match.group(1)), int(match.group(2))


def _sources() -> list[Path]:
    return sorted(
        path for path in CADGEN_SRC.rglob("*.py")
        if "__pycache__" not in path.parts
    )


class CadgenParsesOnItsDeclaredFloor(unittest.TestCase):
    def test_every_module_parses_with_the_declared_minimum_grammar(self) -> None:
        floor = _declared_floor()
        if floor < _OLDEST_SUPPORTED_FEATURE_VERSION or floor > sys.version_info[:2]:
            self.skipTest(
                f"cannot parse against {floor[0]}.{floor[1]} from "
                f"{sys.version_info.major}.{sys.version_info.minor}",
            )

        sources = _sources()
        self.assertTrue(sources, f"no cadgen sources found under {CADGEN_SRC}")

        offenders = []
        for path in sources:
            source = path.read_text(encoding="utf-8")
            try:
                ast.parse(source, filename=str(path), feature_version=floor)
            except SyntaxError as error:
                offenders.append(
                    f"{path.relative_to(CADGEN_SRC)}:{error.lineno}: {error.msg}",
                )

        self.assertEqual(
            [],
            offenders,
            f"cadgen declares requires-python >= {floor[0]}.{floor[1]}, so every module "
            f"must parse under that grammar; these do not:\n  " + "\n  ".join(offenders),
        )


if __name__ == "__main__":
    unittest.main()
