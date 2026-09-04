"""The freshness verdict, the state machine, and where progress is read from.

Ports ``artifactStatus.test.mjs`` and ``buildProgress.test.mjs``, and adds the
fixtures over the store: a document's result is a tree plus a record, and the
verdict reads them (STORE.md).
"""

from __future__ import annotations

import json
import os
import tempfile
import time
import unittest
from pathlib import Path

from cadgen.viewer import store_paths
from cadgen.viewer.artifact_status import (
    artifact_status,
    owns_artifact_path,
    owns_dxf_path,
    owns_step_path,
    resolve_artifact_verdict,
)
from cadgen.viewer.backend import ForbiddenAssetError

from tests.python.support.store_fixtures import seed_result

STEP_BYTES = b"ISO-10303-21;\nHEADER;\nENDSEC;\nDATA;\nENDSEC;\nEND-ISO-10303-21;\n"


class _Tree:
    """A models root plus its own private cache, wired through the environment."""

    def __init__(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name, "models")
        self.root.mkdir()
        self.cache = Path(self.tmp.name, "cache")
        self.cache.mkdir()
        self._previous = os.environ.get("CADGEN_CACHE_DIR")
        os.environ["CADGEN_CACHE_DIR"] = str(self.cache)
        # Progress records live in the daemon's state dir, not the store; give this
        # tree its own so a peer record from another run cannot leak in.
        self._previous_state = os.environ.get("CADGEN_DAEMON_STATE_DIR")
        os.environ["CADGEN_DAEMON_STATE_DIR"] = str(Path(self.tmp.name, "state"))

    def close(self) -> None:
        if self._previous is None:
            os.environ.pop("CADGEN_CACHE_DIR", None)
        else:
            os.environ["CADGEN_CACHE_DIR"] = self._previous
        if self._previous_state is None:
            os.environ.pop("CADGEN_DAEMON_STATE_DIR", None)
        else:
            os.environ["CADGEN_DAEMON_STATE_DIR"] = self._previous_state
        self.tmp.cleanup()

    def step(self, name="model.step", body=STEP_BYTES) -> str:
        path = self.root / name
        path.write_bytes(body)
        return str(path)

    def package(self, step_path, *, kind="assembly-package", components=("c0.surf",), write_payloads=True):
        """Seed the document's result: a tree (one component per name) and a
        record keyed by the document itself. Returns the tree hash."""
        import hashlib

        descriptor = {"kind": kind, "components": {f"k{i}": {} for i, _name in enumerate(components)}}
        tree = seed_result(step_path, descriptor, surf=b"SURF\x00")
        if not write_payloads:
            from cadgen.store.objects import object_path

            object_path(hashlib.sha256(b"SURF\x00").hexdigest()).unlink()
        return tree

class ArtifactStatusTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.tree = _Tree()
        self.addCleanup(self.tree.close)


class Ownership(ArtifactStatusTestCase):
    def test_step_and_stp_are_owned_case_insensitively(self):
        for name in ("a.step", "a.STEP", "a.stp", "a.Stp"):
            self.assertTrue(owns_step_path(name), name)
        for name in ("a.py", "a.dxf", "a.stl", "astep", ""):
            self.assertFalse(owns_step_path(name), name)

    def test_dxf_is_never_owned(self):
        # A plain .dxf renders directly and generated-DXF entries were scripts,
        # which are not entries at all any more.
        self.assertFalse(owns_dxf_path("a.dxf"))
        self.assertFalse(owns_artifact_path("a.dxf"))

    def test_a_trailing_newline_is_not_a_step_path(self):
        r"""The pattern is anchored with ``\Z``, not ``$``.

        Python's ``$`` also matches immediately before a final newline, so
        ``a.step\n`` matched here where JavaScript's ``/\.(step|stp)$/`` did
        not. What is owned is the whole name ending in the suffix, never the
        suffix plus a stray line ending.
        """
        for name in ("a.step\n", "a.stp\n", "a.step\r\n", "a.step\n\n"):
            self.assertFalse(owns_step_path(name), repr(name))
            self.assertFalse(owns_artifact_path(name), repr(name))
        # Still owned when a newline sits INSIDE the name: that is a (bizarre)
        # filename, not a line ending after the suffix.
        self.assertTrue(owns_step_path("a\nb.step"))


class Containment(ArtifactStatusTestCase):
    """An out-of-root ref is refused here, before any package is looked at.

    The whole HTTP chain lives in ``test_security.py`` class L; these pin the
    resolver itself, which is where the refusal has to land — every compile
    door is downstream of it.
    """

    def test_an_absolute_ref_outside_the_root_raises(self):
        outside = Path(self.tree.tmp.name, "outside")
        outside.mkdir()
        victim = outside / "secret.step"
        victim.write_bytes(STEP_BYTES)
        with self.assertRaises(ForbiddenAssetError):
            resolve_artifact_verdict(str(victim), str(self.tree.root))
        with self.assertRaises(ForbiddenAssetError):
            artifact_status(str(victim), str(self.tree.root))

    def test_a_relative_ref_that_walks_out_raises(self):
        for ref in ("../outside/secret.step", "sub/../../outside/secret.step"):
            with self.subTest(ref=ref), self.assertRaises(ForbiddenAssetError):
                resolve_artifact_verdict(ref, str(self.tree.root))

    def test_a_name_prefix_sibling_of_the_root_is_outside(self):
        sibling = Path(str(self.tree.root) + "-evil")
        sibling.mkdir()
        stolen = sibling / "stolen.step"
        stolen.write_bytes(STEP_BYTES)
        with self.assertRaises(ForbiddenAssetError):
            resolve_artifact_verdict(str(stolen), str(self.tree.root))

    def test_an_absolute_in_root_ref_still_resolves(self):
        # The judgement call: absolute IS the normal spelling here, because the
        # catalog absolutizes every entry's file and the client echoes it back.
        step = self.tree.step()
        verdict = resolve_artifact_verdict(step, str(self.tree.root))
        self.assertEqual(verdict["candidate"], os.path.abspath(step))

    def test_a_missing_in_root_ref_is_still_a_soft_no(self):
        # Containment raises; a file that simply is not there must not.
        self.assertEqual(
            artifact_status("absent.step", str(self.tree.root)),
            {"state": "failed", "error": "Artifact source not found: absent.step"},
        )


class Verdicts(ArtifactStatusTestCase):
    def test_a_fresh_package_is_ready(self):
        step = self.tree.step()
        self.tree.package(step)
        self.assertEqual(artifact_status(step, str(self.tree.root)), {"state": "rendered"})

    def test_editing_the_file_unresolves_the_package(self):
        step = self.tree.step()
        self.tree.package(step)
        Path(step).write_bytes(STEP_BYTES + b"\n")
        # The record lists the document's sha (gate clause 5): different bytes,
        # no result for them.
        self.assertEqual(
            artifact_status(step, str(self.tree.root)),
            {"state": "not-compiled", "reason": "missing_glb"},
        )

    def test_restoring_the_bytes_makes_it_ready_again_with_nothing_rebuilt(self):
        step = self.tree.step()
        self.tree.package(step)
        Path(step).write_bytes(STEP_BYTES + b"\n")
        Path(step).write_bytes(STEP_BYTES)
        self.assertEqual(artifact_status(step, str(self.tree.root)), {"state": "rendered"})

    def test_a_missing_candidate_is_an_error_naming_the_raw_ref(self):
        self.assertEqual(
            artifact_status("nope.step", str(self.tree.root)),
            {"state": "failed", "error": "Artifact source not found: nope.step"},
        )

    def test_an_unowned_format_is_an_error(self):
        path = self.tree.root / "notes.py"
        path.write_text("x = 1", encoding="utf-8")
        self.assertEqual(
            artifact_status(str(path), str(self.tree.root)),
            {"state": "failed", "error": f"No render-artifact format owns this entry: {path}"},
        )

    def test_the_gate_order_missing_then_components_then_ready(self):
        step = self.tree.step()
        self.assertEqual(artifact_status(step, str(self.tree.root))["reason"], "missing_glb")

        self.tree.package(step, components=())
        self.assertEqual(artifact_status(step, str(self.tree.root))["reason"], "missing_glb")

        self.tree.package(step)
        self.assertEqual(artifact_status(step, str(self.tree.root)), {"state": "rendered"})

    def test_a_component_whose_surf_payload_is_absent_is_missing_glb(self):
        step = self.tree.step()
        self.tree.package(step, write_payloads=False)
        self.assertEqual(artifact_status(step, str(self.tree.root))["reason"], "missing_glb")


class SnapshotShapes(ArtifactStatusTestCase):
    def test_writing_beats_a_resolvable_package(self):
        step = self.tree.step()
        self.tree.package(step)
        status = artifact_status(
            step,
            str(self.tree.root),
            snapshot={"writing": True, "busy": False, "runId": "r1", "progress": {"phase": "x"}},
        )
        self.assertEqual(
            status, {"state": "compiling", "runId": "r1", "progress": {"phase": "x"}}
        )

    def test_absent_run_id_and_progress_are_ABSENT_not_null(self):
        step = self.tree.step()
        status = artifact_status(
            step,
            str(self.tree.root),
            snapshot={"writing": True, "busy": False, "runId": None, "progress": None},
        )
        self.assertEqual(status, {"state": "compiling"})

    def test_busy_over_an_ok_package_is_ready_plus_busy(self):
        step = self.tree.step()
        self.tree.package(step)
        status = artifact_status(
            step,
            str(self.tree.root),
            snapshot={"writing": False, "busy": True, "runId": "r2", "progress": None},
        )
        self.assertEqual(status, {"state": "rendered", "busy": True, "runId": "r2"})

    def test_busy_over_an_unbuilt_package_is_needs_build_plus_blocked(self):
        step = self.tree.step()
        status = artifact_status(
            step,
            str(self.tree.root),
            snapshot={"writing": False, "busy": True, "runId": None, "progress": None},
        )
        self.assertEqual(
            status, {"state": "not-compiled", "reason": "missing_glb", "blocked": True}
        )


class InvalidUtf8(ArtifactStatusTestCase):
    """A byte that is not UTF-8 must not change the answer the client acts on.

    Node read every one of these files with ``fs.readFileSync(path, "utf8")``,
    which substitutes U+FFFD and carries on. The port decoded strictly, and
    because ``UnicodeDecodeError`` is a ``ValueError`` it landed in the same
    ``except`` clause as "the file is missing" — so one bad byte silently became
    ABSENT, and absent is a DIFFERENT state, not a degraded one.

    Product names in a STEP file are arbitrary bytes and flow into the tree
    descriptor, so these are real files, not hypothetical ones.
    """

    #: Latin-1 ``é``: a lone 0xE9 with no continuation byte, invalid as UTF-8.
    BAD = b"\xe9"

    def _corrupt(self, path, marker: bytes = b"NAME_HERE") -> None:
        path = Path(path)
        body = path.read_bytes()
        self.assertIn(marker, body, "precondition: the fixture carries the marker")
        path.write_bytes(body.replace(marker, self.BAD))


    def test_no_backend_reader_opens_a_text_file_strictly(self):
        """The sweep, as a rule rather than three cases.

        ``scanner.py`` has always used ``errors="replace"``; while the status
        readers did not, the SAME file was a valid sidecar to the catalog and a
        missing one to the artifact route. A reader added later with Python's
        default strictness would reopen exactly that split, so the check is
        structural rather than a list of the three sites that had it.

        Scoped to FILE reads: ``open`` for reading and ``read_text``. A bytes
        decode is a separate judgement with its own local answer — ``encoding.py``
        implements ``decodeURIComponent``, which is REQUIRED to throw on invalid
        UTF-8, and ``compile_client`` decodes frames its own child just encoded.
        """
        import ast

        allowed = {
            # A shipped runtime asset with a single writer: this repo. A bad
            # byte in it is a broken build to surface, not a state to degrade.
            "natural_sort.py",
        }
        offenders = []
        import cadgen.viewer

        for path in sorted(Path(cadgen.viewer.__file__).parent.glob("*.py")):
            if path.name in allowed:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                name = ast.unparse(node.func)
                if name != "open" and not name.endswith(".read_text"):
                    continue
                arguments = [ast.unparse(argument) for argument in node.args]
                keywords = {keyword.arg: ast.unparse(keyword.value) for keyword in node.keywords}
                mode = keywords.get("mode") or (arguments[1] if len(arguments) > 1 else "'r'")
                if any(character in mode for character in "wax+"):
                    continue  # a write, which has no decoding to get wrong
                if "b" in mode:
                    continue  # binary, which has no decoding at all
                if keywords.get("errors"):
                    continue
                offenders.append(f"{path.name}:{node.lineno} {ast.unparse(node)}")
        self.assertEqual(
            offenders,
            [],
            "a backend reader of a shared text file must pass errors='replace', as Node did",
        )


if __name__ == "__main__":
    unittest.main()
