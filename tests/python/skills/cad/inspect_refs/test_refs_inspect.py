import contextlib
import io
import shutil
import unittest
from array import array
from pathlib import Path
from unittest import mock

from tests.python.support.paths import add_repo_path


from cadgen.cli.step_inspect import cli as inspect_cli
from cadgen.cli.step_inspect import inspect as refs_inspect
from cadgen import cad_ref_syntax as refs_syntax
from cadgen._internal import assembly_spec
from cadgen._internal import generation as cad_generation
from cadgen import step_targets
from cadgen._internal.glb_topology import STEP_TOPOLOGY_SCHEMA_VERSION
from cadgen.catalog import result_view_dir
from cadgen.selector_types import SelectorBundle, SelectorProfile
from cadgen._internal.source_hash import python_source_hash
from tests.python.support.cad_test_roots import IsolatedCadRoots


def _refs_manifest(cad_ref: str) -> dict[str, object]:
    return {
        "schemaVersion": STEP_TOPOLOGY_SCHEMA_VERSION,
        "profile": "refs",
        "cadPath": cad_ref,
        "stepPath": f"{cad_ref}.step",
        "stepHash": "step-hash-123",
        "bbox": {"min": [0.0, 0.0, 0.0], "max": [10.0, 10.0, 10.0]},
        "stats": {
            "occurrenceCount": 2,
            "leafOccurrenceCount": 1,
            "shapeCount": 1,
            "faceCount": 2,
            "edgeCount": 2,
            "vertexCount": 1,
        },
        "tables": {
            "occurrenceColumns": [
                "id",
                "path",
                "name",
                "sourceName",
                "parentId",
                "transform",
                "bbox",
                "shapeStart",
                "shapeCount",
                "faceStart",
                "faceCount",
                "edgeStart",
                "edgeCount",
                "vertexStart",
                "vertexCount",
            ],
            "shapeColumns": [
                "id",
                "occurrenceId",
                "ordinal",
                "kind",
                "bbox",
                "center",
                "area",
                "volume",
                "faceStart",
                "faceCount",
                "edgeStart",
                "edgeCount",
                "vertexStart",
                "vertexCount",
            ],
            "faceColumns": [
                "id",
                "occurrenceId",
                "shapeId",
                "ordinal",
                "surfaceType",
                "area",
                "center",
                "normal",
                "bbox",
                "edgeStart",
                "edgeCount",
                "relevance",
                "flags",
                "params",
                "triangleStart",
                "triangleCount",
            ],
            "edgeColumns": [
                "id",
                "occurrenceId",
                "shapeId",
                "ordinal",
                "curveType",
                "length",
                "center",
                "bbox",
                "faceStart",
                "faceCount",
                "vertexStart",
                "vertexCount",
                "relevance",
                "flags",
                "params",
                "segmentStart",
                "segmentCount",
            ],
            "vertexColumns": [
                "id",
                "occurrenceId",
                "shapeId",
                "ordinal",
                "center",
                "bbox",
                "edgeStart",
                "edgeCount",
                "relevance",
                "flags",
            ],
        },
        "occurrences": [
            [
                "o1",
                "1",
                "Root",
                "Root",
                None,
                [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1],
                {"min": [0.0, 0.0, 0.0], "max": [10.0, 10.0, 10.0]},
                0,
                1,
                0,
                2,
                0,
                2,
                0,
                1,
            ],
            [
                "o1.2",
                "1.2",
                "Bracket",
                "Bracket",
                "o1",
                [1, 0, 0, 5, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1],
                {"min": [5.0, 0.0, 0.0], "max": [10.0, 10.0, 10.0]},
                0,
                1,
                0,
                2,
                0,
                2,
                0,
                1,
            ],
        ],
        "shapes": [
            [
                "o1.2.s1",
                "o1.2",
                1,
                "solid",
                {"min": [5.0, 0.0, 0.0], "max": [10.0, 10.0, 10.0]},
                [7.5, 5.0, 5.0],
                100.0,
                250.0,
                0,
                2,
                0,
                2,
                0,
                1,
            ]
        ],
        "faces": [
            [
                "o1.2.f1",
                "o1.2",
                "o1.2.s1",
                1,
                "plane",
                20.0,
                [6.0, 1.0, 0.0],
                [0.0, 0.0, 1.0],
                {"min": [5.0, 0.0, 0.0], "max": [7.0, 2.0, 0.0]},
                0,
                2,
                80,
                0,
                {"origin": [5.0, 0.0, 0.0], "axis": [0.0, 0.0, 1.0]},
                0,
                0,
            ],
            [
                "o1.2.f2",
                "o1.2",
                "o1.2.s1",
                2,
                "cylinder",
                12.0,
                [7.0, 2.0, 1.0],
                [1.0, 0.0, 0.0],
                {"min": [6.0, 1.0, 0.0], "max": [8.0, 3.0, 2.0]},
                1,
                0,
                60,
                0,
                {"center": [7.0, 2.0, 1.0], "axis": [1.0, 0.0, 0.0], "radius": 1.0},
                0,
                0,
            ],
        ],
        "edges": [
            [
                "o1.2.e1",
                "o1.2",
                "o1.2.s1",
                1,
                "line",
                4.0,
                [6.0, 1.0, 0.0],
                {"min": [5.0, 0.0, 0.0], "max": [7.0, 2.0, 0.0]},
                0,
                2,
                0,
                1,
                90,
                0,
                {"origin": [5.0, 0.0, 0.0], "direction": [1.0, 0.0, 0.0]},
                0,
                0,
            ],
            [
                "o1.2.e2",
                "o1.2",
                "o1.2.s1",
                2,
                "line",
                3.0,
                [5.5, 0.5, 0.0],
                {"min": [5.0, 0.0, 0.0], "max": [6.0, 1.0, 0.0]},
                2,
                1,
                1,
                1,
                75,
                0,
                {"origin": [5.0, 0.0, 0.0], "direction": [0.0, 1.0, 0.0]},
                0,
                0,
            ],
        ],
        "vertices": [
            [
                "o1.2.v1",
                "o1.2",
                "o1.2.s1",
                1,
                [5.0, 0.0, 0.0],
                {"min": [5.0, 0.0, 0.0], "max": [5.0, 0.0, 0.0]},
                0,
                2,
                95,
                0,
            ]
        ],
        "relations": {
            "faceEdgeRows": [0, 1, 0],
            "edgeFaceRows": [0, 1, 0],
            "edgeVertexRows": [0, 0],
            "vertexEdgeRows": [0, 1],
        },
    }


def _summary_manifest(cad_ref: str) -> dict[str, object]:
    return {
        "schemaVersion": STEP_TOPOLOGY_SCHEMA_VERSION,
        "profile": "summary",
        "cadPath": cad_ref,
        "stepPath": f"{cad_ref}.step",
        "stepHash": "step-hash-123",
        "bbox": {"min": [0.0, 0.0, 0.0], "max": [10.0, 10.0, 10.0]},
        "stats": {
            "occurrenceCount": 1,
            "leafOccurrenceCount": 1,
            "shapeCount": 1,
            "faceCount": 2,
            "edgeCount": 2,
            "vertexCount": 1,
        },
        "tables": {
            "occurrenceColumns": [
                "id",
                "path",
                "name",
                "sourceName",
                "parentId",
                "transform",
                "bbox",
                "shapeStart",
                "shapeCount",
                "faceStart",
                "faceCount",
                "edgeStart",
                "edgeCount",
                "vertexStart",
                "vertexCount",
            ],
            "shapeColumns": [],
            "faceColumns": [],
            "edgeColumns": [],
            "vertexColumns": [],
        },
        "occurrences": [
            [
                "o1",
                "1",
                "Part",
                "Part",
                None,
                [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1],
                {"min": [0.0, 0.0, 0.0], "max": [10.0, 10.0, 10.0]},
                0,
                1,
                0,
                2,
                0,
                2,
                0,
                1,
            ]
        ],
        "shapes": [],
        "faces": [],
        "edges": [],
        "vertices": [],
    }


class InspectRefsSyntaxTests(unittest.TestCase):
    def test_normalize_selector_list_inherits_occurrence_prefix(self) -> None:
        selectors = refs_syntax.normalize_selector_list("o1.2.f12,f13,e7,v2,s3")

        self.assertEqual(
            ["o1.2.f12", "o1.2.f13", "o1.2.e7", "o1.2.v2", "o1.2.s3"],
            selectors,
        )

class InspectRefsTests(unittest.TestCase):
    def setUp(self) -> None:
        self._isolated_roots = IsolatedCadRoots(self, prefix="refs-inspect-")
        tempdir = self._isolated_roots.temporary_cad_directory(prefix="tmp-refs-inspect-")
        self._tempdir = tempdir
        self.temp_root = Path(tempdir.name)
        self.relative_dir = self.temp_root.relative_to(Path.cwd()).as_posix()
        self.lookup_ref = f"{self.relative_dir}/sample"
        self.cad_ref = self.lookup_ref
        self.step_path = self.temp_root / "sample.step"
        # Unique per test: content keying would otherwise resolve same-bytes
        # fixtures from earlier tests to one shared store package.
        self.step_path.write_text(f"ISO-10303-21; /* {self.temp_root} */ END-ISO-10303-21;\n")
        self.addCleanup(self._tempdir.cleanup)
        self.addCleanup(lambda: shutil.rmtree(self.temp_root, ignore_errors=True))

    @contextlib.contextmanager
    def _mock_glb_topology(
        self,
        manifest: dict[str, object],
        *,
        step_path: Path | None = None,
        buffers: dict[str, array] | None = None,
        include_selector: bool = True,
        strip_selector_keys: tuple[str, ...] = (),
    ):
        """Serve `manifest` as the entry's topology artifact.

        Mocks at the one live boundary — ``ensure_step_topology_artifact`` —
        which in production returns the assembly.json with a
        assembly.json-backed selector bundle (selector rows composed on demand
        from the per-component .surf files). Everything below that boundary
        (grammar, lookup, measure, align) runs for real.
        """
        resolved_step_path = step_path or self.step_path
        edge_rendering = {
            "visibilityClasses": ["feature", "tangent", "seam", "degenerate"],
            "generatedVisibilityClasses": ["feature"],
            "visibilityClassCounts": {"feature": 1},
            "generatedVisibilityClassCounts": {"feature": 1},
        }
        topology_manifest = {"schemaVersion": STEP_TOPOLOGY_SCHEMA_VERSION, **manifest}
        source_kind = str(topology_manifest.get("sourceKind") or "step").strip().lower()
        source_path = resolved_step_path.with_suffix(".py") if source_kind == "python" else resolved_step_path
        topology_manifest.setdefault("sourceKind", source_kind)
        topology_manifest.setdefault("sourcePath", self._manifest_path(source_path))
        topology_manifest.setdefault("stepPath", self._manifest_path(resolved_step_path))
        topology_manifest.setdefault("edgeRendering", edge_rendering)
        selector_topology_manifest = {
            key: value for key, value in topology_manifest.items() if key not in strip_selector_keys
        }

        from cadgen.step_targets import StepTopologyArtifact

        def fake_ensure(target, *, require_selector=True, **_kwargs):
            bundle = (
                SelectorBundle(manifest=selector_topology_manifest, buffers=buffers or {})
                if include_selector and require_selector
                else None
            )
            return StepTopologyArtifact(
                cad_path=target.cad_path,
                kind=target.kind,
                source_path=target.source_path,
                step_path=target.step_path,
                artifact_path=__import__("cadgen.catalog", fromlist=["result_view_dir"]).result_view_dir(resolved_step_path),
                manifest=topology_manifest,
                selector_bundle=bundle,
            )

        stack = contextlib.ExitStack()
        with stack:
            stack.enter_context(mock.patch.object(step_targets, "find_step_path", return_value=resolved_step_path))
            stack.enter_context(
                mock.patch("cadgen.step_topology_artifact.ensure_step_topology_artifact", side_effect=fake_ensure)
            )
            yield

    def _manifest_path(self, path: Path) -> str:
        resolved = path.resolve()
        try:
            return resolved.relative_to(Path.cwd().resolve()).as_posix()
        except ValueError:
            return resolved.as_posix()

    def test_whole_entry_summary_uses_glb_index(self) -> None:
        with self._mock_glb_topology(_summary_manifest(self.cad_ref), include_selector=False):
            result = refs_inspect.inspect_cad_refs(self.cad_ref)

        self.assertTrue(result["ok"])
        token = result["tokens"][0]
        self.assertEqual(1, token["summary"]["occurrenceCount"])
        self.assertEqual(2, token["summary"]["faceCount"])
        self.assertEqual([], token["selections"])

    def test_facts_kind_falls_back_to_index_manifest_for_assembly(self) -> None:
        manifest = {**_refs_manifest(self.cad_ref), "entryKind": "assembly"}

        with self._mock_glb_topology(manifest, strip_selector_keys=("entryKind", "assembly")):
            result = refs_inspect.inspect_cad_refs(self.cad_ref, facts=True)

        self.assertTrue(result["ok"])
        token = result["tokens"][0]
        self.assertEqual("assembly", token["summary"]["kind"])
        self.assertEqual("assembly", token["entryFacts"]["kind"])

    def test_python_backed_glb_only_entry_inspects_without_step_file(self) -> None:
        self.step_path.unlink()
        script_path = self.step_path.with_suffix(".py")
        script_path.write_text(
            "from cadgen import step\n@step\ndef model():\n    return object()\n",
            encoding="utf-8",
        )
        source_identity = python_source_hash(script_path)
        manifest = {
            **_summary_manifest(self.cad_ref),
            "sourceKind": "python",
            "sourceHash": source_identity.source_hash,
        }

        with self._mock_glb_topology(manifest, include_selector=False):
            result = refs_inspect.inspect_cad_refs(self.cad_ref)

        self.assertTrue(result["ok"])
        token = result["tokens"][0]
        self.assertEqual(refs_inspect._display_path(self.step_path), token["stepPath"])
        self.assertEqual(1, token["summary"]["occurrenceCount"])

    def test_context_provider_can_supply_in_memory_entry_context(self) -> None:
        requested_profiles = []

        def provider(cad_path, profile):
            requested_profiles.append(profile)
            if cad_path != self.cad_ref:
                return None
            manifest = _summary_manifest(cad_path)
            return refs_inspect.EntryContext(
                cad_path=cad_path,
                kind="part",
                source_path=self.step_path,
                step_path=self.step_path,
                manifest=manifest,
                selector_index=refs_inspect.lookup.build_selector_index(manifest),
            )

        result = refs_inspect.inspect_cad_refs(self.cad_ref, context_provider=provider)

        self.assertTrue(result["ok"])
        self.assertEqual([SelectorProfile.SUMMARY], requested_profiles)
        self.assertEqual(2, result["tokens"][0]["summary"]["faceCount"])

    def test_face_lookup_resolves_single_occurrence_alias_and_detail(self) -> None:
        with self._mock_glb_topology(_refs_manifest(self.cad_ref)):
            result = refs_inspect.inspect_cad_refs(self.cad_ref, "#o1.2.f1", detail=True)

        self.assertTrue(result["ok"])
        selection = result["tokens"][0]["selections"][0]
        self.assertEqual("face", selection["selectorType"])
        self.assertEqual("o1.2.f1", selection["normalizedSelector"])
        self.assertEqual("plane area=20.0", selection["summary"])
        self.assertEqual(["e1", "e2"], selection["detail"]["adjacentEdgeSelectors"])

    def test_vertex_lookup_resolves_corner_detail(self) -> None:
        with self._mock_glb_topology(_refs_manifest(self.cad_ref)):
            result = refs_inspect.inspect_cad_refs(self.cad_ref, "#o1.2.v1", detail=True)

        self.assertTrue(result["ok"])
        selection = result["tokens"][0]["selections"][0]
        self.assertEqual("vertex", selection["selectorType"])
        self.assertEqual("o1.2.v1", selection["normalizedSelector"])
        self.assertEqual("corner edges=2", selection["summary"])
        self.assertEqual(["e1", "e2"], selection["detail"]["adjacentEdgeSelectors"])
        self.assertEqual(["f1", "f2"], selection["detail"]["adjacentFaceSelectors"])

    def test_single_occurrence_alias_is_compacted_in_copy_text(self) -> None:
        with self._mock_glb_topology(_summary_manifest(self.cad_ref)):
            result = refs_inspect.inspect_cad_refs(self.cad_ref, "#f2", detail=True)

        self.assertFalse(result["ok"])

        with self._mock_glb_topology(
            {
                **_refs_manifest(self.cad_ref),
                "stats": {
                    "occurrenceCount": 1,
                    "leafOccurrenceCount": 1,
                    "shapeCount": 1,
                    "faceCount": 2,
                    "edgeCount": 2,
                    "vertexCount": 1,
                },
                "occurrences": [_refs_manifest(self.cad_ref)["occurrences"][1]],
            },
        ):
            result = refs_inspect.inspect_cad_refs(self.cad_ref, "#v1", detail=True)

        self.assertTrue(result["ok"])
        selection = result["tokens"][0]["selections"][0]
        self.assertEqual("v1", selection["displaySelector"])
        self.assertEqual("#v1", selection["copyText"])

    def test_old_part_selector_syntax_is_rejected(self) -> None:
        with self._mock_glb_topology(_refs_manifest(self.cad_ref)):
            result = refs_inspect.inspect_cad_refs(self.cad_ref, "#p:legacy.f1")

        self.assertFalse(result["ok"])
        self.assertEqual("selector", result["errors"][0]["kind"])

    def test_topology_flag_returns_full_selector_lists(self) -> None:
        with self._mock_glb_topology(_refs_manifest(self.cad_ref)):
            result = refs_inspect.inspect_cad_refs(self.cad_ref, include_topology=True)

        self.assertTrue(result["ok"])
        topology = result["tokens"][0]["topology"]
        self.assertIn("f1", topology["faces"])
        self.assertIn("e1", topology["edges"])
        self.assertIn("v1", topology["vertices"])

    def test_detail_uses_glb_buffer_backed_relation_rows(self) -> None:
        manifest = {
            **_refs_manifest(self.cad_ref),
            "relations": {
                "faceEdgeRowsView": "faceEdgeRows",
                "edgeFaceRowsView": "edgeFaceRows",
                "edgeVertexRowsView": "edgeVertexRows",
                "vertexEdgeRowsView": "vertexEdgeRows",
            },
        }
        buffers = {
            "faceEdgeRows": array("I", [0, 1, 0]),
            "edgeFaceRows": array("I", [0, 1, 0]),
            "edgeVertexRows": array("I", [0, 0]),
            "vertexEdgeRows": array("I", [0, 1]),
        }

        with self._mock_glb_topology(manifest, buffers=buffers):
            result = refs_inspect.inspect_cad_refs(self.cad_ref, "#o1.2.f1", detail=True)

        self.assertTrue(result["ok"])
        selection = result["tokens"][0]["selections"][0]
        self.assertEqual(["e1", "e2"], selection["detail"]["adjacentEdgeSelectors"])

    def test_missing_glb_topology_is_an_inspect_error(self) -> None:
        result = refs_inspect.inspect_cad_refs(self.cad_ref)

        self.assertFalse(result["ok"])
        error = result["errors"][0]
        self.assertEqual("glb_regeneration_failed", error["code"])
        # A door never tells the user to run anything: the message is the
        # compile's own failure and nothing else travels beside it.
        self.assertNotIn("Regenerate", error["message"])
        self.assertNotIn("regenerateCommand", error)

    def test_legacy_cad_ref_mismatch_is_accepted_when_hash_matches(self) -> None:
        with self._mock_glb_topology({**_refs_manifest("other/ref"), "stepHash": "step-hash-123"}):
            result = refs_inspect.inspect_cad_refs(self.cad_ref)

        self.assertTrue(result["ok"])
        self.assertEqual(self.cad_ref, result["tokens"][0]["cadPath"])

    def test_non_leaf_occurrence_detail_reports_children(self) -> None:
        with self._mock_glb_topology(_refs_manifest(self.cad_ref)):
            result = refs_inspect.inspect_cad_refs(self.cad_ref, "#o1", detail=True)

        self.assertTrue(result["ok"])
        selection = result["tokens"][0]["selections"][0]
        self.assertEqual("occurrence", selection["selectorType"])
        self.assertEqual("o1", selection["normalizedSelector"])
        self.assertEqual(1, selection["detail"]["childCount"])
        self.assertEqual(["o1.2"], selection["detail"]["descendantOccurrenceIds"])

    def test_assembly_topology_lookup_resolves_from_generated_step(self) -> None:
        assembly_cad_ref = f"{self.relative_dir}/sample-assembly"
        assembly_path = self.temp_root / "sample-assembly.py"
        assembly_step_path = self.temp_root / "sample-assembly.step"
        assembly_path.write_text(
            "from build123d import Box, Compound\n"
            "from cadgen import step\n"
            "@step\n"
            "def model():\n"
            "    return Compound(children=[Box(1, 1, 1), Box(1, 1, 1)], label='sample')\n",
            encoding="utf-8",
        )
        assembly_step_path.write_text("ISO-10303-21; END-ISO-10303-21;\n", encoding="utf-8")
        source_identity = python_source_hash(assembly_path)

        with mock.patch.object(
            step_targets,
            "resolve_cad_source_path",
            return_value=("assembly", assembly_path),
        ), self._mock_glb_topology(
            {
                **_refs_manifest(assembly_cad_ref),
                "sourceKind": "python",
                "sourceHash": source_identity.source_hash,
                "stepHash": cad_generation.step_file_hash(assembly_step_path),
            },
            step_path=assembly_step_path,
        ):
            result = refs_inspect.inspect_cad_refs(assembly_cad_ref, "#o1.2.f1", detail=True)

        self.assertTrue(result["ok"])
        selection = result["tokens"][0]["selections"][0]
        self.assertEqual("assembly", result["tokens"][0]["summary"]["kind"])
        self.assertEqual("face", selection["selectorType"])
        self.assertEqual("o1.2.f1", selection["normalizedSelector"])

    def test_positioning_flag_returns_plane_facts(self) -> None:
        with self._mock_glb_topology(_refs_manifest(self.cad_ref)):
            result = refs_inspect.inspect_cad_refs(
                self.cad_ref,
                "#o1.2.f1",
                positioning=True,
            )

        self.assertTrue(result["ok"])
        positioning = result["tokens"][0]["selections"][0]["positioning"]
        self.assertEqual("plane", positioning["kind"])
        self.assertEqual("z", positioning["axis"])
        self.assertEqual(0.0, positioning["coordinate"])
        self.assertEqual([0.0, 0.0, 1.0], positioning["normal"])

    def test_planes_flag_returns_entry_planes(self) -> None:
        with self._mock_glb_topology(_refs_manifest(self.cad_ref)):
            result = refs_inspect.inspect_cad_refs(
                self.cad_ref,
                planes=True,
                plane_coordinate_tolerance=0.01,
                plane_min_area_ratio=0.0,
                plane_limit=1,
            )

        self.assertTrue(result["ok"])
        planes = result["tokens"][0]["planes"]
        self.assertEqual(1, len(planes))
        self.assertEqual("z", planes[0]["axis"])

    def test_refs_text_format_includes_entry_reports(self) -> None:
        result = {
            "ok": True,
            "tokens": [
                {
                    "cadPath": self.cad_ref,
                    "summary": {"faceCount": 2, "edgeCount": 2},
                    "entryFacts": {
                        "size": [10.0, 10.0, 10.0],
                        "center": [5.0, 5.0, 5.0],
                        "extentAxis": "x",
                        "diag": 17.320508,
                        "kind": "part",
                    },
                    "planes": [
                        {
                            "axis": "z",
                            "coordinate": 0.0,
                            "normalSign": 1,
                            "faceCount": 1,
                            "totalArea": 100.0,
                        }
                    ],
                    "selections": [],
                }
            ],
            "errors": [],
        }

        text = inspect_cli._format_refs_text(result, quiet=False, verbose=False)

        self.assertIn("facts: size=[10, 10, 10]", text)
        self.assertIn("planes: 1 major groups", text)
        self.assertIn("z=0", text)

    def test_diff_planes_returns_entry_planes(self) -> None:
        with self._mock_glb_topology(_refs_manifest(self.cad_ref)):
            result = refs_inspect.diff_entry_targets(
                self.cad_ref,
                self.cad_ref,
                planes=True,
                plane_limit=1,
            )

        self.assertTrue(result["ok"])
        self.assertEqual(1, len(result["diff"]["leftMajorPlanes"]))
        self.assertEqual(1, len(result["diff"]["rightMajorPlanes"]))

    def test_cli_parses_current_agentic_commands(self) -> None:
        parser = inspect_cli.build_parser()

        refs_args = parser.parse_args(["refs", "entry.step", "#f1", "--detail", "--facts"])
        self.assertEqual("refs", refs_args.command)
        self.assertTrue(refs_args.detail)
        self.assertTrue(refs_args.facts)

        diff_args = parser.parse_args(
            ["diff", "left", "right", "--planes", "--plane-coordinate-tolerance", "0.02", "--plane-limit", "3"]
        )
        self.assertTrue(diff_args.planes)
        self.assertEqual(0.02, diff_args.plane_coordinate_tolerance)
        self.assertEqual(3, diff_args.plane_limit)

        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as render_exit:
            parser.parse_args(["render", "list", "part.step", "--format", "text"])
        self.assertEqual(2, render_exit.exception.code)

        top_level_verbose_args = parser.parse_args(["--verbose", "refs", "entry.step", "#f1"])
        self.assertTrue(top_level_verbose_args.verbose)

        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as verbose_render_exit:
            parser.parse_args(["--verbose", "render", "view", "part.step", "--output", "part.png"])
        self.assertEqual(2, verbose_render_exit.exception.code)

    def test_command_result_wraps_inspect_errors(self) -> None:
        # The in-process runner (what the daemon dispatch relies on) must wrap
        # failures into a payload rather than raising through the worker pool.
        exit_code, result = inspect_cli.inspect_command_result(["refs"])

        self.assertEqual(2, exit_code)
        self.assertFalse(result["ok"])
        self.assertIn("No STEP/CAD entry target provided", result["errors"][0]["message"])

    def test_frame_command_returns_occurrence_axes(self) -> None:
        with self._mock_glb_topology(_refs_manifest(self.cad_ref)):
            result = refs_inspect.inspect_target_frame(self.cad_ref, "#o1.2")

        self.assertTrue(result["ok"])
        self.assertEqual([5.0, 0.0, 0.0], result["frame"]["translation"])
        self.assertEqual([1.0, 0.0, 0.0], result["frame"]["localAxes"]["x"])

    def test_measure_targets_returns_signed_axis_distance(self) -> None:
        with self._mock_glb_topology(_refs_manifest(self.cad_ref)):
            result = refs_inspect.measure_targets(
                self.cad_ref,
                "#o1.2.f1",
                "#o1.2.f2",
                axis="x",
            )

        self.assertTrue(result["ok"])
        self.assertEqual("x", result["axis"])
        self.assertEqual(5.0, result["from"]["coordinate"])
        self.assertEqual(7.0, result["to"]["coordinate"])
        self.assertEqual(2.0, result["measurement"]["signedDistance"])

    def test_align_targets_returns_flush_translation_delta(self) -> None:
        with self._mock_glb_topology(_refs_manifest(self.cad_ref)):
            result = refs_inspect.align_targets(
                self.cad_ref,
                "#o1.2.f1",
                "#o1.2.f2",
                axis="x",
            )

        self.assertTrue(result["ok"])
        self.assertEqual([2.0, 0.0, 0.0], result["alignment"]["translationVector"])
        self.assertEqual(2.0, result["alignment"]["transformTranslationDelta"]["3"])


class GroupOccurrenceRefTests(unittest.TestCase):
    """A ref naming a SUBASSEMBLY, which no selector row carries.

    One document, two occurrence namespaces: the instance tree, and the flat selector
    rows that are its LEAVES, because only a leaf owns geometry. `o1.1` below is an
    interior node -- the viewer copies it, `snapshot --focus` takes it, a kinematics mate
    poses it -- and `inspect` used to refuse it as "did not resolve", which reads as "no
    such branch" rather than "that branch has no row of its own".

    An occurrence id IS its path through the tree, so a group is an id prefix, which is
    how kinematicsModule.js and cadScene.js resolve one. The shared derivation lives in
    cadgen.occurrence_groups, alongside snapshot's use of it.
    """

    CAD_REF = "tmp-groups/nested"

    # Three leaves under two branches: o1.1 groups two parts, o1.2 stands alone. The
    # boxes are placed apart so a group's union extent is checkable and cannot be
    # confused with any single member's.
    LEAVES = (
        # id, name, bbox min, bbox max, translation
        ("o1.1.1", "BarLeft", [0.0, 0.0, 0.0], [2.0, 2.0, 2.0], [0.0, 0.0, 0.0]),
        ("o1.1.2", "BarRight", [4.0, 0.0, 0.0], [6.0, 2.0, 2.0], [4.0, 0.0, 0.0]),
        ("o1.2", "Post", [0.0, 0.0, 10.0], [2.0, 2.0, 12.0], [0.0, 0.0, 10.0]),
    )

    def _manifest(self) -> dict[str, object]:
        occurrences = []
        shapes = []
        for index, (occ_id, name, low, high, translation) in enumerate(self.LEAVES):
            occurrences.append([
                occ_id,
                occ_id.lstrip("o"),
                name,
                name,
                occ_id.rpartition(".")[0] or None,
                [1, 0, 0, translation[0], 0, 1, 0, translation[1], 0, 0, 1, translation[2], 0, 0, 0, 1],
                {"min": low, "max": high},
                index, 1, 0, 0, 0, 0, 0, 0,
            ])
            shapes.append([
                f"{occ_id}.s1", occ_id, 1, "solid",
                {"min": low, "max": high},
                [(low[axis] + high[axis]) / 2 for axis in range(3)],
                24.0, 8.0, 0, 0, 0, 0, 0, 0,
            ])
        return {
            "schemaVersion": STEP_TOPOLOGY_SCHEMA_VERSION,
            "profile": "refs",
            "cadPath": self.CAD_REF,
            "stepPath": f"{self.CAD_REF}.step",
            "stepHash": "step-hash-groups",
            "entryKind": "assembly",
            "bbox": {"min": [0.0, 0.0, 0.0], "max": [6.0, 2.0, 12.0]},
            "stats": {
                "occurrenceCount": len(self.LEAVES),
                "leafOccurrenceCount": len(self.LEAVES),
                "shapeCount": len(self.LEAVES),
                "faceCount": 0,
                "edgeCount": 0,
                "vertexCount": 0,
            },
            "tables": {
                "occurrenceColumns": [
                    "id", "path", "name", "sourceName", "parentId", "transform", "bbox",
                    "shapeStart", "shapeCount", "faceStart", "faceCount",
                    "edgeStart", "edgeCount", "vertexStart", "vertexCount",
                ],
                "shapeColumns": [
                    "id", "occurrenceId", "ordinal", "kind", "bbox", "center", "area",
                    "volume", "faceStart", "faceCount", "edgeStart", "edgeCount",
                    "vertexStart", "vertexCount",
                ],
                "faceColumns": [],
                "edgeColumns": [],
                "vertexColumns": [],
            },
            "occurrences": occurrences,
            "shapes": shapes,
            "faces": [],
            "edges": [],
            "vertices": [],
        }

    def _provider(self):
        manifest = self._manifest()

        def provider(cad_path, profile):
            if cad_path != self.CAD_REF:
                return None
            return refs_inspect.EntryContext(
                cad_path=cad_path,
                kind="assembly",
                source_path=Path(f"{cad_path}.step"),
                step_path=Path(f"{cad_path}.step"),
                manifest=manifest,
                selector_index=refs_inspect.lookup.build_selector_index(manifest),
            )

        return provider

    def test_refs_expands_a_group_to_the_parts_beneath_it(self) -> None:
        result = refs_inspect.inspect_cad_refs(
            self.CAD_REF, "#o1.1", context_provider=self._provider()
        )

        self.assertTrue(result["ok"], result.get("errors"))
        selections = result["tokens"][0]["selections"]
        self.assertEqual(
            ["o1.1.1", "o1.1.2"],
            [selection["normalizedSelector"] for selection in selections],
        )
        # Each one says where it came from, so a reader can tell two parts reported
        # because a group was named from two parts they asked for individually.
        self.assertEqual({"o1.1"}, {selection["fromGroup"] for selection in selections})
        self.assertEqual({"resolved"}, {selection["status"] for selection in selections})

    def test_a_leaf_ref_still_answers_for_itself(self) -> None:
        result = refs_inspect.inspect_cad_refs(
            self.CAD_REF, "#o1.1.2", context_provider=self._provider()
        )

        self.assertTrue(result["ok"], result.get("errors"))
        selections = result["tokens"][0]["selections"]
        self.assertEqual(["o1.1.2"], [item["normalizedSelector"] for item in selections])
        self.assertNotIn("fromGroup", selections[0])

    def test_the_reported_counts_stay_leaf_based(self) -> None:
        # Accepting group refs must not start counting interior nodes: `occurrenceCount`
        # is what this index can resolve to geometry, and a group resolves by expanding
        # to leaves that are already counted.
        result = refs_inspect.inspect_cad_refs(
            self.CAD_REF, "#o1.1", facts=True, context_provider=self._provider()
        )

        summary = result["tokens"][0]["summary"]
        self.assertEqual(len(self.LEAVES), summary["occurrenceCount"])

    def test_frame_answers_for_the_branch(self) -> None:
        result = refs_inspect.inspect_target_frame(
            self.CAD_REF, "#o1.1", context_provider=self._provider()
        )

        self.assertTrue(result["ok"])
        self.assertEqual("group", result["occurrenceKind"])
        self.assertEqual(["o1.1.1", "o1.1.2"], result["members"])
        frame = result["frame"]
        # The branch's own extent: both bars, not either one.
        self.assertEqual({"min": [0.0, 0.0, 0.0], "max": [6.0, 2.0, 2.0]}, frame["bbox"])
        self.assertEqual([3.0, 1.0, 1.0], frame["center"])
        # A subassembly node carries no transform of its own -- group placement is baked
        # into each leaf's absolute transform -- so none is invented for it.
        self.assertNotIn("translation", frame)

    def test_measure_uses_the_whole_branch(self) -> None:
        result = refs_inspect.measure_targets(
            self.CAD_REF, "#o1.1", "#o1.2", axis="z", context_provider=self._provider()
        )

        self.assertTrue(result["ok"])
        self.assertEqual("group", result["from"]["occurrenceKind"])
        self.assertEqual(1.0, result["from"]["coordinate"])
        self.assertEqual(11.0, result["to"]["coordinate"])
        self.assertEqual(10.0, result["measurement"]["signedDistance"])

    def test_an_unknown_ref_names_what_does_exist(self) -> None:
        result = refs_inspect.inspect_cad_refs(
            self.CAD_REF, "#o1.9", context_provider=self._provider()
        )

        self.assertFalse(result["ok"])
        message = result["errors"][0]["message"]
        self.assertIn("did not resolve", message)
        self.assertIn("o1 does exist, and holds: o1.1, o1.2", message)

    def test_an_entity_ref_under_a_group_is_not_expanded(self) -> None:
        # `o1.1.f1` would be face 1 of a subassembly, and face numbering is per
        # occurrence -- expanding it to each part's f1 would answer about four different
        # faces as though they were one. It stays an unresolved ref, with the hint.
        result = refs_inspect.inspect_cad_refs(
            self.CAD_REF, "#o1.1.f1", context_provider=self._provider()
        )

        self.assertFalse(result["ok"])
        self.assertEqual(1, len(result["tokens"][0]["selections"]))

    def test_frame_on_an_unknown_ref_fails_with_the_hint(self) -> None:
        with self.assertRaises(refs_inspect.CadRefError) as raised:
            refs_inspect.inspect_target_frame(
                self.CAD_REF, "#o1.1.9", context_provider=self._provider()
            )
        self.assertIn("o1.1 does exist, and holds: o1.1.1, o1.1.2", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
