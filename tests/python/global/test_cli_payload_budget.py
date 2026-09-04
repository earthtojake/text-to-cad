"""stdout is an agent's context window, so payload size is a feature with a budget.

Almost every CLI output here is O(1) -- `gen` prints the same ~100 bytes for a 600-part
assembly that it prints for a single part. The parts inventory from `snapshot --mode list`
is the one exception: it grows with the model, and on a 600-part assembly it was 294 KB
(~73k tokens) of which most was redundancy -- `id`, `occurrenceId` and `ref` were the same
string three times over, `label` duplicated `name`, coordinates carried 16 significant
figures for a dimension in millimetres, and the whole thing was pretty-printed.

These tests measure the shape rather than the bytes of a real render, so they run without a
browser: what a part is allowed to carry, and how a payload is serialised.
"""

from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

from tests.python.support.paths import add_repo_path, repo_path

add_repo_path("packages/cadgen/src")

RENDER_MESH_SCENE_JS = Path(repo_path("packages/cadgen-js/src/common/renderMeshScene.js"))

# Every field a listed part may carry. Adding one is a real decision: it is multiplied by
# the part count, so a field that duplicates another costs thousands of tokens per call.
ALLOWED_PART_FIELDS = {"ref", "name", "triangleCount", "vertexCount", "bounds"}

# Fields deleted because they carried no information. Named individually so a
# reintroduction fails here with the reason rather than silently regrowing the payload.
DELETED_PART_FIELDS = {
    "id": "identical to ref without the '#' in 600/600 parts measured",
    "occurrenceId": "identical to ref without the '#' in 600/600 parts measured",
    "label": "identical to name in 600/600 parts measured",
}


def _list_parts_source() -> str:
    source = RENDER_MESH_SCENE_JS.read_text(encoding="utf-8")
    start = source.index("export function listRenderableParts")
    return source[start:source.index("\n}", start)]


class ListPayloadShapeTests(unittest.TestCase):
    def test_a_listed_part_carries_only_the_allowed_fields(self):
        body = _list_parts_source()
        emitted = set(re.findall(r"^\s{6}(\w+):", body, flags=re.MULTILINE))
        self.assertEqual(
            ALLOWED_PART_FIELDS,
            emitted,
            "listRenderableParts emits a different field set than the budget allows",
        )

    def test_the_deleted_duplicates_stay_deleted(self):
        body = _list_parts_source()
        for field, why in DELETED_PART_FIELDS.items():
            with self.subTest(field=field):
                self.assertNotRegex(
                    body,
                    rf"^\s{{6}}{field}:",
                    f"{field} is back in the parts payload; it was removed because it is {why}",
                )

    def test_coordinates_are_rounded(self):
        source = RENDER_MESH_SCENE_JS.read_text(encoding="utf-8")
        self.assertIn("LIST_BOUNDS_DECIMALS", source)
        self.assertIn("roundedBounds", _list_parts_source())


class CompactStdoutTests(unittest.TestCase):
    """No CLI pretty-prints JSON to stdout. Indentation was 38% of a 294 KB payload."""

    # Every source that writes JSON to stdout. `cad artifact` and `dxf artifact` were
    # missed by the first pass of this test and were still pretty-printing.
    STDOUT_JSON_SOURCES = (
        # Result dataclasses whose human_lines() are a JSON document -- the
        # `--mode list` parts inventory, and each inspection's report.
        "packages/cadgen/src/cadgen/results.py",
        "packages/cadgen/src/cadgen/step_artifact_cli.py",
        "packages/cadgen/src/cadgen/cli/step_inspect/cli.py",
        # Every GENERATED CLI (`cadgen <format> <verb>`) serializes its Result
        # here rather than in its own module, so one entry covers all of them.
        "packages/cadgen/src/cadgen/_internal/cli_from_function.py",
        "packages/cadgen/src/cadgen/cli/_run_model.py",
        "packages/cadgen/src/cadgen/cli/daemon_status.py",
        "packages/cadgen/src/cadgen/cli/store.py",
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

    def test_a_realistic_part_entry_stays_small(self):
        # The shape above, priced. 600 of these is the payload an agent pays for.
        entry = {
            "ref": "#o1.1.1",
            "name": "terrain_regolith_slab",
            "triangleCount": 172,
            "vertexCount": 516,
            "bounds": {"min": [-2450.0, -1800.0, -90.0], "max": [2750.0, 1800.0, 0.0]},
        }
        encoded = json.dumps(entry, separators=(",", ":"))
        self.assertLess(
            len(encoded),
            200,
            f"a listed part costs {len(encoded)}B; at 600 parts that is "
            f"{len(encoded) * 600 // 1024} KB of an agent's context",
        )


if __name__ == "__main__":
    unittest.main()
