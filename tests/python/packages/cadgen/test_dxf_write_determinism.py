"""Written DXF bytes are a function of drawing content, not traversal order.

The engine owns DXF serialization (design/dxf-build123d.md): a ``@dxf``
function returns build123d 2D geometry and :mod:`cadgen._internal.dxf_emit`
writes it. Two things could make identical geometry write different bytes:

* **ezdxf's volatile provenance** — two random GUIDs, four Julian timestamps
  and two ``"<version> @ <iso>"`` marker comments, all stamped per save. The
  emitter pins them.
* **entity order** — ``ExportDXF`` converts ``shape.edges()`` in OCC traversal
  order, which is not a property of the drawing. The emitter sorts edges by
  geometric content instead, so an OCP upgrade that reorders traversal cannot
  churn a committed fixture.

The rig below is the shape of drawing that exercises both: several layers,
exact ARCs from a kerf offset, CIRCLEs, LINEs, and SPLINE text outlines. It is
rebuilt from scratch for every run — fresh kernel objects, fresh traversal —
and must hash identically, in-process and across processes.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests.python.support.paths import add_repo_path

CADGEN_SRC = add_repo_path("packages/cadgen/src")


_RIG_SOURCE = """
import build123d as bd


def build_drawing():
    with bd.BuildSketch() as cut:
        bd.Rectangle(60, 40)
        bd.Circle(8, mode=bd.Mode.SUBTRACT)
        with bd.Locations((-24, -14), (24, -14), (-24, 14), (24, 14)):
            bd.Circle(2.25, mode=bd.Mode.SUBTRACT)
    with bd.BuildSketch() as mark:
        bd.Text("REV B", font_size=6)
    # offset() keeps exact ARCs at the corners -- the entity kind the shapely
    # path could never produce.
    return {"CUT": bd.offset(cut.sketch, amount=0.15), "ENGRAVE": mark.sketch}
"""

exec(compile(_RIG_SOURCE, "<dxf-determinism-rig>", "exec"), globals())  # noqa: S102


def _digest() -> str:
    from cadgen._internal.dxf_emit import emit_dxf

    payload, _ = emit_dxf(build_drawing(), label="determinism-rig")  # noqa: F821
    return hashlib.sha256(payload).hexdigest()


class DxfWriteDeterminismTest(unittest.TestCase):
    def test_three_fresh_builds_write_identical_bytes(self) -> None:
        digests = {_digest() for _ in range(3)}
        self.assertEqual(
            len(digests),
            1,
            f"identical drawings wrote {len(digests)} distinct byte streams: {sorted(digests)}",
        )

    def test_digest_matches_across_processes(self) -> None:
        """A separate interpreter — different heap, different hash seed — must
        agree. Byte-determinism is engineered here, so the PYTHONHASHSEED
        re-exec the old ezdxf pipeline needed is gone; this is what replaced it.

        The unset seed (``"random"``) is the case that matters and the one that
        caught the CLASSES-section ordering: ezdxf registers required classes by
        iterating a SET of entity-type strings, so a cold run wrote one of two
        byte streams at random until the emitter sorted that registry.
        """
        script = "\n".join(
            [
                "import hashlib, json, sys",
                f"sys.path.insert(0, {str(CADGEN_SRC)!r})",
                _RIG_SOURCE,
                "from cadgen._internal.dxf_emit import emit_dxf",
                'payload, _ = emit_dxf(build_drawing(), label="determinism-rig")',
                'print(json.dumps({"digest": hashlib.sha256(payload).hexdigest()}))',
            ]
        )
        expected = _digest()
        for seed in ("0", "12345", "random", "random", "random", "random"):
            environment = dict(os.environ)
            environment.pop("PYTHONHASHSEED", None)
            if seed != "random":
                environment["PYTHONHASHSEED"] = seed
            environment["CADGEN_DAEMON"] = "0"
            completed = subprocess.run(
                [sys.executable, "-c", script],
                env=environment,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            payload = json.loads(completed.stdout.strip().splitlines()[-1])
            self.assertEqual(
                payload["digest"],
                expected,
                f"cross-process digest differs at PYTHONHASHSEED={seed}",
            )

    def test_layer_and_edge_order_do_not_reach_the_bytes(self) -> None:
        """The same drawing described in a different ORDER is the same file."""
        from cadgen._internal.dxf_emit import emit_dxf

        forward = build_drawing()  # noqa: F821
        reversed_layers = dict(reversed(list(build_drawing().items())))  # noqa: F821
        first, _ = emit_dxf(forward, label="rig")
        second, _ = emit_dxf(reversed_layers, label="rig")
        self.assertEqual(hashlib.sha256(first).hexdigest(), hashlib.sha256(second).hexdigest())

    def test_sort_key_is_content_only(self) -> None:
        """The ordering key must not encode traversal position or identity.

        Two independently constructed copies of one edge — different objects,
        different traversal history — must produce the same key, and shuffling
        an edge list must not change the sorted result.
        """
        import random

        import build123d as bd

        from cadgen._internal.dxf_emit import _edge_sort_key

        left = bd.Line((0, 0), (10, 0)).edges()[0]
        right = bd.Line((0, 0), (10, 0)).edges()[0]
        self.assertIsNot(left, right)
        self.assertEqual(_edge_sort_key(left), _edge_sort_key(right))

        with bd.BuildSketch() as sketch:
            bd.Rectangle(20, 10)
            bd.Circle(3, mode=bd.Mode.SUBTRACT)
        edges = list(sketch.sketch.edges())
        canonical = [_edge_sort_key(edge) for edge in sorted(edges, key=_edge_sort_key)]
        shuffled = list(edges)
        random.Random(7).shuffle(shuffled)
        self.assertEqual(
            canonical, [_edge_sort_key(edge) for edge in sorted(shuffled, key=_edge_sort_key)]
        )

    def test_volatile_provenance_is_pinned(self) -> None:
        """The six volatile header fields carry their pinned constants.

        Probed empirically (build123d 0.11.1 / ezdxf 1.4.4): two exports of one
        drawing differ ONLY in $FINGERPRINTGUID, $VERSIONGUID and the two marker
        comments, with the four $TD* Julian stamps volatile across days.
        """
        from cadgen._internal.dxf_emit import emit_dxf

        payload, _ = emit_dxf(build_drawing(), label="rig")  # noqa: F821
        text = payload.decode("utf-8")
        lines = [line.strip() for line in text.split("\n")]
        for header in ("$FINGERPRINTGUID", "$VERSIONGUID"):
            self.assertIn(header, lines)
            self.assertEqual(lines[lines.index(header) + 2], "{00000000-0000-0000-0000-000000000000}")
        for header in ("$TDCREATE", "$TDUCREATE", "$TDUPDATE", "$TDUUPDATE"):
            self.assertIn(header, lines)
            self.assertEqual(lines[lines.index(header) + 2], "2451545.0")
        self.assertEqual(text.count("0.0 @ 2000-01-01T00:00:00.000000+00:00"), 2)

    def test_class_registry_is_sorted(self) -> None:
        """The CLASSES section is emitted in class-name order, not set order."""
        from cadgen._internal.dxf_emit import emit_dxf

        payload, _ = emit_dxf(build_drawing(), label="rig")  # noqa: F821
        lines = [line.strip() for line in payload.decode("utf-8").split("\n")]
        start = lines.index("CLASSES")
        end = lines.index("ENDSEC", start)
        # A CLASS record is "CLASS", group code "1", then the class name.
        names = [lines[index + 2] for index in range(start, end) if lines[index] == "CLASS"]
        self.assertGreaterEqual(len(names), 2, "rig must register several classes")
        self.assertEqual(names, sorted(names))

    def test_offset_keeps_exact_arcs(self) -> None:
        """Kerf compensation must survive as true ARCs, not polygonized noise —
        the whole reason the shapely path stops being primary."""
        from cadgen._internal.dxf_emit import emit_dxf

        _, document = emit_dxf(build_drawing(), label="rig")  # noqa: F821
        kinds = {entity.dxftype() for entity in document.modelspace()}
        self.assertIn("ARC", kinds)
        self.assertIn("CIRCLE", kinds)
        self.assertIn("SPLINE", kinds)


class DxfEmitContractTest(unittest.TestCase):
    def test_off_plane_geometry_raises_with_a_relocation_hint(self) -> None:
        import build123d as bd

        from cadgen._internal.dxf_emit import OffPlaneGeometryError, emit_dxf

        with bd.BuildSketch() as sketch:
            bd.Rectangle(10, 5)
        lifted = bd.Location((0, 0, 5)) * sketch.sketch
        with self.assertRaises(OffPlaneGeometryError) as caught:
            emit_dxf(lifted, label="lifted.py")
        message = str(caught.exception)
        self.assertIn("off the XY plane", message)
        self.assertIn("bd.Location((0, 0, -z))", message)

    def test_bare_shape_lands_on_the_cut_layer(self) -> None:
        import build123d as bd

        from cadgen._internal.dxf_emit import emit_dxf

        with bd.BuildSketch() as sketch:
            bd.Rectangle(10, 5)
        bare, _ = emit_dxf(sketch.sketch, label="rig")
        named, _ = emit_dxf({"CUT": sketch.sketch}, label="rig")
        self.assertEqual(bare, named)

    def test_labelled_compound_normalizes_like_the_dict(self) -> None:
        import build123d as bd

        from cadgen._internal.dxf_emit import emit_dxf

        cut = bd.Rectangle(10, 5).face()
        cut.label = "CUT"
        engrave = bd.Rectangle(4, 2).face()
        engrave.label = "ENGRAVE"
        compound, _ = emit_dxf(bd.Compound(children=[cut, engrave]), label="rig")
        mapping, _ = emit_dxf({"CUT": cut, "ENGRAVE": engrave}, label="rig")
        self.assertEqual(compound, mapping)

    def test_an_ezdxf_document_return_fails_the_geometry_contract(self) -> None:
        """No recognition of what an ezdxf document once meant here: it is
        simply not build123d 2D geometry, and ordinary validation says so."""
        import ezdxf

        from cadgen._internal.dxf_emit import DxfContractError, emit_dxf

        for value in (ezdxf.new("R2010"), {"document": ezdxf.new("R2010")}):
            with self.assertRaises(DxfContractError) as caught:
                emit_dxf(value, label="old_drawing.py")
            message = str(caught.exception)
            self.assertIn("build123d", message)
            self.assertNotIn("removed", message)

    def test_non_geometry_return_raises(self) -> None:
        from cadgen._internal.dxf_emit import DxfContractError, emit_dxf

        with self.assertRaises(DxfContractError):
            emit_dxf(42, label="rig")
        with self.assertRaises(DxfContractError):
            emit_dxf({"CUT": "not geometry"}, label="rig")

    def test_invalid_layer_names_raise(self) -> None:
        import build123d as bd

        from cadgen._internal.dxf_emit import DxfContractError, emit_dxf

        with bd.BuildSketch() as sketch:
            bd.Rectangle(10, 5)
        for name in ("", "   ", "CUT/2"):
            with self.assertRaises(DxfContractError):
                emit_dxf({name: sketch.sketch}, label="rig")

    def test_a_layer_name_that_looks_like_a_header_field_is_harmless(self) -> None:
        """A layer called ``$TDCREATE`` must not corrupt the file.

        The volatile-field pin used to REWRITE matching lines, and a layer with a
        header variable's name put its own table record in range: the layer's flag
        line and four entity subclass markers came out as Julian dates. The pin
        verifies instead of rewriting, so the only thing this layer name can do
        now is look odd.
        """
        import build123d as bd

        from cadgen._internal.dxf_emit import emit_dxf

        with bd.BuildSketch() as sketch:
            bd.Rectangle(10, 5)
        payload, _ = emit_dxf({"$TDCREATE": sketch.sketch}, label="rig")
        self.assertNotIn(b"2451545.0\r\nAcDbEntity", payload)

        import ezdxf

        with tempfile.TemporaryDirectory(prefix="dxf-layer-name-") as tmp:
            path = Path(tmp) / "odd.dxf"
            path.write_bytes(payload)
            document = ezdxf.readfile(str(path))
        self.assertEqual(
            {str(entity.dxf.layer) for entity in document.modelspace()}, {"$TDCREATE"}
        )

    def test_a_partly_labelled_compound_raises_instead_of_merging(self) -> None:
        """Labelling some children is a mistake with two silent readings."""
        import build123d as bd

        from cadgen._internal.dxf_emit import DxfContractError, emit_dxf

        cut = bd.Rectangle(10, 5).face()
        cut.label = "CUT"
        unnamed = bd.Pos(20, 0) * bd.Rectangle(4, 2).face()
        with self.assertRaises(DxfContractError) as caught:
            emit_dxf(bd.Compound(children=[cut, unnamed]), label="half_labelled.py")
        self.assertIn("unlabelled", str(caught.exception))

        twin = bd.Pos(20, 0) * bd.Rectangle(4, 2).face()
        twin.label = "CUT"
        with self.assertRaises(DxfContractError) as caught:
            emit_dxf(bd.Compound(children=[cut, twin]), label="duplicate_labels.py")
        self.assertIn("repeat the layer label", str(caught.exception))

    def test_a_lost_class_registry_raises_rather_than_degrading(self) -> None:
        """Determinism must fail loudly, never quietly.

        If ezdxf renames the registry this emitter sorts, skipping the sort would
        leave the bytes seed-dependent again — and only a lucky hash seed would
        make any test notice.
        """
        from unittest import mock

        import build123d as bd

        from cadgen._internal.dxf_emit import DxfDeterminismError, emit_dxf

        with bd.BuildSketch() as sketch:
            bd.Rectangle(10, 5)
        with mock.patch(
            "cadgen._internal.dxf_emit._canonicalize_class_registry",
            side_effect=DxfDeterminismError("registry shape changed"),
        ):
            with self.assertRaises(DxfDeterminismError):
                emit_dxf(sketch.sketch, label="rig")

    def test_unpinned_provenance_raises(self) -> None:
        """The check is the guarantee: without ezdxf's fixed-metadata mode the
        build must fail rather than emit bytes that rehash on every rebuild."""
        from cadgen._internal.dxf_emit import (
            DxfDeterminismError,
            _assert_volatile_fields_pinned,
        )

        volatile = "\n".join(
            [
                "0", "SECTION", "2", "HEADER",
                "9", "$FINGERPRINTGUID", "2", "{1D5A0B2C-0000-0000-0000-000000000001}",
                "0", "ENDSEC",
            ]
        )
        with self.assertRaises(DxfDeterminismError) as caught:
            _assert_volatile_fields_pinned(volatile, label="rig")
        self.assertIn("$FINGERPRINTGUID", str(caught.exception))

    def test_shape_order_within_a_layer_does_not_reach_the_bytes(self) -> None:
        """A layer may hold several shapes; which order they arrive in is the
        author's incidental choice, not part of the drawing."""
        import build123d as bd

        from cadgen._internal.dxf_emit import emit_dxf

        left = bd.Rectangle(10, 5).face()
        right = bd.Pos(20, 0) * bd.Rectangle(4, 2).face()
        forward, _ = emit_dxf({"CUT": [left, right]}, label="rig")
        backward, _ = emit_dxf({"CUT": [right, left]}, label="rig")
        self.assertEqual(forward, backward)


_DRAWING_MODEL = '''"""A repo-shaped drawing: several layers, arcs from a kerf offset, text."""

from cadgen import build123d as bd
from cadgen import dxf


KERF = 0.15


@dxf
def bracket_plate():
    with bd.BuildSketch() as cut:
        bd.Rectangle(60, 40)
        bd.Circle(8, mode=bd.Mode.SUBTRACT)
        with bd.Locations((-24, -14), (24, -14), (-24, 14), (24, 14)):
            bd.Circle(2.25, mode=bd.Mode.SUBTRACT)
    with bd.BuildSketch() as mark:
        bd.Text("REV B", font_size=6)
    return {"CUT": bd.offset(cut.sketch, amount=KERF), "ENGRAVE": mark.sketch}


if __name__ == "__main__":
    bracket_plate()
'''


class DxfRunPathDeterminismTest(unittest.TestCase):
    """The determinism that ships: a model script, run the way a user runs it.

    Everything above tests the emitter directly. This runs the whole ``@dxf``
    path — decorator, freshness gate, runner, drawing validation, atomic write —
    in separate COLD processes under different hash seeds, and compares the file
    on disk. That is the surface the deleted ``PYTHONHASHSEED`` re-exec used to
    protect, so it is the surface that has to hold without it.
    """

    def _build(self, seed: str | None) -> bytes:
        with tempfile.TemporaryDirectory(prefix="dxf-run-path-") as tmp:
            project = Path(tmp)
            script = project / "bracket_plate.py"
            script.write_text(_DRAWING_MODEL, encoding="utf-8")
            environment = dict(os.environ)
            environment.pop("PYTHONHASHSEED", None)
            if seed is not None:
                environment["PYTHONHASHSEED"] = seed
            environment["CADGEN_DAEMON"] = "0"  # a warm worker would serve another checkout
            environment["CADGEN_CACHE_DIR"] = str(project / "store")
            environment["PYTHONPATH"] = str(CADGEN_SRC)
            completed = subprocess.run(
                [sys.executable, str(script)],
                cwd=str(project),
                env=environment,
                capture_output=True,
                text=True,
                timeout=600,
                check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
            written = project / "bracket_plate.dxf"
            self.assertTrue(written.is_file(), completed.stdout + completed.stderr)
            return written.read_bytes()

    def test_cold_runs_under_different_seeds_write_identical_files(self) -> None:
        digests = {
            hashlib.sha256(self._build(seed)).hexdigest()
            for seed in (None, "0", "12345", None)
        }
        self.assertEqual(
            len(digests),
            1,
            f"the same drawing model wrote {len(digests)} distinct files: {sorted(digests)}",
        )

    def test_the_written_file_matches_the_emitter(self) -> None:
        """No transformation sits between the emitter and the file on disk."""
        from cadgen._internal.dxf_emit import emit_dxf
        from cadgen.authoring import building

        namespace: dict = {}
        exec(compile(_DRAWING_MODEL, "<drawing-model>", "exec"), namespace)  # noqa: S102
        # Calling the decorated name outside a build would BUILD it; inside
        # `building()` it composes and returns the drawing, which is what the
        # emitter comparison needs.
        with building():
            expected, _ = emit_dxf(namespace["bracket_plate"](), label="bracket_plate.py")
        self.assertEqual(self._build(None), expected)


if __name__ == "__main__":
    unittest.main()
