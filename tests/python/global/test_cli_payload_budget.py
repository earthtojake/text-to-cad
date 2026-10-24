"""stdout is an agent's context window, so payload size is a feature with a budget.

A parts inventory once grew with the model: on a 600-part assembly it was 294 KB (~73k tokens),
38% of it indentation. So no command's module pretty-prints JSON to stdout.
"""

from __future__ import annotations

import unittest
from pathlib import Path

from tests.python.support.paths import add_repo_path, repo_path

add_repo_path("packages/cadgen/src")

class CompactStdoutTests(unittest.TestCase):
    """No CLI pretty-prints JSON to stdout. Indentation was 38% of a 294 KB payload."""

    # Every source that writes JSON to stdout. `cad artifact` and `dxf artifact` were
    # missed by the first pass of this test and were still pretty-printing.
    STDOUT_JSON_SOURCES = (
        # The validators' Result dataclasses.
        "packages/cadgen/src/cadgen/results.py",
        # Every GENERATED CLI (`cadgen <format> <verb>`) serializes its Result
        # here rather than in its own module, so one entry covers all of them.
        "packages/cadgen/src/cadgen/_internal/cli_from_function.py",
    )

    def test_the_source_list_covers_every_json_emitting_cli(self):
        """A new JSON-emitting CLI must be added above, or it is silently unchecked.

        The list is hand-written, which is how `cad artifact` and `dxf artifact` went
        unchecked the first time. Derive the expectation instead: anything under
        `cadgen.cli` that serialises JSON is in scope, plus the generated-CLI
        serializer every `<format> <verb>` command prints through.
        """
        repo = Path(repo_path("."))
        cli_dir = Path(repo_path("packages/cadgen/src/cadgen/cli"))
        sources = [
            *cli_dir.rglob("*.py"),
            Path(repo_path("packages/cadgen/src/cadgen/_internal/cli_from_function.py")),
        ]
        emitters = {
            path.relative_to(repo).as_posix()
            for path in sources
            if "json.dumps" in path.read_text(encoding="utf-8")
        }
        missing = emitters - set(self.STDOUT_JSON_SOURCES)
        self.assertFalse(missing, f"add these to STDOUT_JSON_SOURCES: {sorted(missing)}")

    def test_no_indented_json_reaches_stdout(self):
        for rel in self.STDOUT_JSON_SOURCES:
            with self.subTest(source=rel):
                source = Path(repo_path(rel)).read_text(encoding="utf-8")
                offenders = [
                    line.strip()
                    for line in source.splitlines()
                    # A descriptor written to a FILE may be indented -- it is an artifact,
                    # not output. Only stdout is budgeted.
                    if "indent=" in line and "json.dump" in line and "handle" not in line
                ]
                self.assertEqual([], offenders, f"{rel} pretty-prints JSON")


if __name__ == "__main__":
    unittest.main()
