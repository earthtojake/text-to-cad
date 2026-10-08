"""Written STEP bytes are a function of model content, not heap layout.

OCCT's STEPCAFControl_Writer registers each styled product's presentation
graph (MDGPR + styled items + colours) by iterating an ADDRESS-hashed shape
map, so an assembly with two or more styled products serializes its style
section in heap-address order — byte-different files for identical models,
varying per process and even per call. cadgen's package keys and export
records are content hashes of these bytes, so every wobble orphaned a store
package and dirtied committed fixtures.

``_style_tail_plan`` computes a content-derived order for that tail after
transfer (the same post-transfer canonicalization contract as
``_renumber_nauo_ids``). This test builds the same nested, multi-product,
per-occurrence-colored assembly from scratch repeatedly — fresh allocations
every time, exactly what flips the map order — and demands identical bytes.

The plan is applied in one of two places — to the written FILE (the tail
records alone in the normal path, the whole file when the fast path does not
recognize the file's shape) or to the MODEL via ``ChangeOrder`` (quadratic, the
backstop for a tail whose numbers straddle a digit-width boundary). Those two
must agree BYTE for byte, not merely semantically: the bytes are the store key,
so a formatting difference between them would re-key every package in every
store. ``test_both_appliers_write_identical_bytes`` is what makes deleting
neither path safe.

The same contract, one layer down in the numbers themselves: IEEE-754 has two
zeros, OCCT prints both, and which one a coordinate lands on follows the
operation path that produced the shape rather than the shape. The writer's last
canonicalization normalizes the sign of zero, and the tests at the bottom of
this file cover the pass on raw text and end to end.
"""

from __future__ import annotations

import contextlib
import hashlib
import os
import random
import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests.python.support.paths import add_repo_path

add_repo_path("packages/cadgen/src")


def _build_assembly(*, transparent_part: bool = False):
    """A minimal shape that hits the nondeterministic path: nested group
    products whose parts carry per-occurrence colors — several MDGPRs.

    ``transparent_part`` gives ONE part an alpha color. That is not a variation
    for its own sake: an alpha color makes OCCT append
    SURFACE_STYLE_RENDERING_WITH_PROPERTIES + SURFACE_STYLE_TRANSPARENT to the
    style tail, and the canonicalization only reorders a tail it fully
    recognizes — so a family list missing those two types silently disables
    canonicalization for every model with a transparent part, which is exactly
    what happened."""
    from build123d import Color, Compound
    from build123d.topology import Solid

    groups = []
    for group_index in range(3):
        parts = []
        for part_index in range(2):
            part = Solid.make_box(4 + group_index, 3 + part_index, 2)
            part = part.moved(part.location)  # fresh wrapper, shared TShape semantics
            part.label = f"part_{group_index}_{part_index}"
            if transparent_part and group_index == 0 and part_index == 0:
                part.color = Color(0.2, 0.9, 0.5, 0.4)
            else:
                part.color = Color(0.2 + 0.3 * group_index, 0.9 - 0.4 * part_index, 0.5)
            parts.append(part)
        group = Compound(children=parts)
        group.label = f"group_{group_index}"
        groups.append(group)
    root = Compound(children=groups)
    root.label = "determinism_rig"
    return root


class StepWriteDeterminismTest(unittest.TestCase):
    def test_presentation_context_breaks_equal_geometry_target_ties(self) -> None:
        from cadgen.step_export import _StyleTailScan, _style_tail_order

        scan = _StyleTailScan(400, 401, {400: [], 401: []}, [400, 401], {})
        targets = {400: [60, 60], 401: [60, 60]}
        self.assertEqual(_style_tail_order(scan, targets, {400: 41, 401: 390}), [400, 401])
        # The same two blocks registered in the opposite heap order.
        self.assertEqual(_style_tail_order(scan, targets, {400: 390, 401: 41}), [401, 400])

    def test_colored_root_with_shared_geometry_is_deterministic_in_both_appliers(self) -> None:
        import build123d as bd
        from cadgen._internal.step_scene_loader import load_step_scene
        from cadgen._internal.step_scene_mesh import scene_leaf_occurrences
        from cadgen.step_export import export_build123d_step_file

        with tempfile.TemporaryDirectory(prefix="step-context-ties-") as tmp:
            digests = set()
            for applier in ("text", "model"):
                with mock.patch.dict(os.environ, {"CADGEN_STEP_STYLE_REORDER": applier}):
                    for run in range(4):
                        leaf = bd.Solid.make_box(2, 3, 4)
                        leaf.label, leaf.color = "leaf", bd.Color("red")
                        sibling = bd.Pos(0, 8, 0) * leaf
                        sibling.label, sibling.color = "sibling", bd.Color("blue")
                        group = bd.Pos(7, 11, 13) * bd.Rot(0, 90, 0) * bd.Compound(
                            children=[leaf, sibling], label="nested",
                        )
                        root = bd.Pos(40, 50, 60) * bd.Rot(17, 29, 83) * bd.Compound(
                            children=[group], label="root",
                        )
                        root.color = bd.Color("green")
                        path = Path(tmp) / f"{applier}-{run}.step"
                        export_build123d_step_file(root, path)
                        digests.add(hashlib.sha256(path.read_bytes()).hexdigest())
                        scene = load_step_scene(path)
                        self.assertEqual(
                            [(node.name, node.color) for node in scene_leaf_occurrences(scene)],
                            [("leaf", (1.0, 0.0, 0.0, 1.0)), ("sibling", (0.0, 0.0, 1.0, 1.0))],
                        )
            self.assertEqual(len(digests), 1)

    def test_repeated_fresh_builds_write_identical_bytes(self) -> None:
        from cadgen.step_export import export_build123d_step_file

        with tempfile.TemporaryDirectory(prefix="step-determinism-") as tmp:
            digests = set()
            for run in range(3):
                out = Path(tmp) / f"run{run}.step"
                export_build123d_step_file(_build_assembly(), out)
                digests.add(hashlib.sha256(out.read_bytes()).hexdigest())
            self.assertEqual(
                len(digests), 1,
                f"identical models wrote {len(digests)} distinct byte streams: {sorted(digests)}",
            )

    def test_transparent_part_still_writes_identical_bytes(self) -> None:
        """One alpha color must not switch canonicalization back off."""
        from cadgen.step_export import export_build123d_step_file

        with tempfile.TemporaryDirectory(prefix="step-determinism-alpha-") as tmp:
            digests = set()
            for run in range(4):
                out = Path(tmp) / f"run{run}.step"
                export_build123d_step_file(
                    _build_assembly(transparent_part=True), out
                )
                digests.add(hashlib.sha256(out.read_bytes()).hexdigest())
            self.assertEqual(
                len(digests), 1,
                "a model with one transparent part wrote "
                f"{len(digests)} distinct byte streams: {sorted(digests)}",
            )

    def test_transparent_part_emits_the_rendering_tail(self) -> None:
        """Guard the premise of the test above: if OCCT ever stops emitting
        these entities the alpha case would pass for the wrong reason."""
        from cadgen.step_export import export_build123d_step_file

        with tempfile.TemporaryDirectory(prefix="step-determinism-alpha-") as tmp:
            out = Path(tmp) / "alpha.step"
            export_build123d_step_file(_build_assembly(transparent_part=True), out)
            text = out.read_text(errors="replace")
            self.assertIn("SURFACE_STYLE_RENDERING_WITH_PROPERTIES(", text)
            self.assertIn("SURFACE_STYLE_TRANSPARENT(", text)

    def test_the_written_file_never_carries_platform_line_endings(self) -> None:
        """The written bytes are the store key, so they must not depend on the OS.

        The style-tail canonicalization reads the file OCCT wrote and writes it
        back. Doing that through ``Path.read_text``/``Path.write_text`` used the
        default universal-newline translation, which on Windows expanded every
        "\\n" OCCT emitted into "\\r\\n" -- so one model keyed two different
        packages depending on which machine built it, and the text applier
        disagreed byte-for-byte with the in-model applier (which never touches
        the file). Runs on every platform and only ever failed on one, which is
        the point: the assertion IS the cross-platform contract.
        """
        from cadgen.step_export import export_build123d_step_file

        with tempfile.TemporaryDirectory(prefix="step-eol-") as tmp:
            out = Path(tmp) / "eol.step"
            export_build123d_step_file(_build_assembly(), out)
            self.assertNotIn(b"\r\n", out.read_bytes())

    def _write_with(self, applier: str, path: Path, *, scrambled: list[int] | None = None, **rig_kwargs) -> bytes:
        """Export the rig with the style-tail permutation applied in `text` or
        in `model`. With ``scrambled`` (a list), the tail's MDGPR blocks are
        first laid out in the reverse of their canonical order, each in the DFS
        layout OCCT gives a block -- what another heap order would have written --
        and the number of blocks is appended."""
        import os

        import cadgen.step_export as step_export
        from cadgen.step_export import export_build123d_step_file

        previous = os.environ.get("CADGEN_STEP_STYLE_REORDER")
        if applier == "model":
            os.environ["CADGEN_STEP_STYLE_REORDER"] = "model"
        else:
            os.environ.pop("CADGEN_STEP_STYLE_REORDER", None)
        scan_tail = step_export._style_tail_scan
        busy = False

        def scrambling_scan(model):
            # Every scan of the writer's model scrambles its tail first. Not keyed by
            # model: each Model() call hands back a fresh Python wrapper.
            nonlocal busy
            if not busy:
                busy = True
                try:
                    plan = step_export._style_tail_plan(model)
                    if plan is not None:
                        tail_start, _total, canonical = plan
                        step_export._apply_style_tail_plan_in_model(model, tail_start, canonical)
                        scan = scan_tail(model)  # canonical numbering: blocks ascend
                        layout: list[int] = []
                        seen: set[int] = set()

                        def visit(number: int) -> None:
                            if number not in seen:
                                seen.add(number)
                                layout.append(number)
                                for child in scan.children[number]:
                                    visit(child)

                        for mdgpr in sorted(scan.mdgpr_nums, reverse=True):
                            visit(mdgpr)
                        if len(layout) == scan.size:
                            step_export._apply_style_tail_plan_in_model(model, tail_start, layout)
                            scrambled.append(len(scan.mdgpr_nums))
                finally:
                    busy = False
            return scan_tail(model)

        scrambling = (
            mock.patch.object(step_export, "_style_tail_scan", scrambling_scan)
            if scrambled is not None else contextlib.nullcontext()
        )
        try:
            with scrambling:
                export_build123d_step_file(_build_assembly(**rig_kwargs), path)
        finally:
            if previous is None:
                os.environ.pop("CADGEN_STEP_STYLE_REORDER", None)
            else:
                os.environ["CADGEN_STEP_STYLE_REORDER"] = previous
        return path.read_bytes()

    def test_both_appliers_write_identical_bytes(self) -> None:
        """The fast text path and the quadratic model path are the same file,
        whatever order the tail starts in.

        This is the gate on the text rewrite: the written bytes are the
        content-addressed store key, so "equivalent STEP" is not good enough —
        a different line wrap would orphan every package built before it.
        OCCT's own tail order comes from address-hashed maps and is sometimes
        already canonical, which would compare two untouched files; so each
        applier also starts from a tail whose blocks run backwards, never canonical.
        """
        with tempfile.TemporaryDirectory(prefix="step-appliers-") as tmp:
            for label, rig_kwargs in (
                ("opaque", {}),
                ("transparent", {"transparent_part": True}),
            ):
                with self.subTest(rig=label):
                    as_written = self._write_with("text", Path(tmp) / f"{label}.step", **rig_kwargs)
                    for applier in ("text", "model"):
                        sizes: list[int] = []
                        reordered = self._write_with(
                            applier, Path(tmp) / f"{label}-{applier}.step", scrambled=sizes, **rig_kwargs
                        )
                        self.assertTrue(sizes and min(sizes) > 1, f"the {applier} applier got no blocks to reorder")
                        self.assertEqual(
                            hashlib.sha256(reordered).hexdigest(),
                            hashlib.sha256(as_written).hexdigest(),
                            f"the {applier} applier wrote other bytes from a reversed tail",
                        )

    def test_unrecognized_file_shape_falls_back_to_the_whole_file_pass(self) -> None:
        """When the in-place applier refuses the written file, the writer runs
        the whole-file pass with the full model plan — and that must be the
        same bytes the normal path produces."""
        import cadgen.step_export as step_export

        with tempfile.TemporaryDirectory(prefix="step-fallback-") as tmp:
            expected = self._write_with("text", Path(tmp) / "normal.step")
            original = step_export._canonicalize_style_tail_in_file
            calls: list = []

            def refuse(path, scan):
                calls.append(path)
                return False

            step_export._canonicalize_style_tail_in_file = refuse
            try:
                fallback = self._write_with("text", Path(tmp) / "fallback.step")
            finally:
                step_export._canonicalize_style_tail_in_file = original
            self.assertEqual(len(calls), 1, "the in-file applier was not consulted")
            self.assertEqual(
                hashlib.sha256(fallback).hexdigest(),
                hashlib.sha256(expected).hexdigest(),
                "the rewrite after a refused file shape wrote different bytes",
            )

    def test_in_file_applier_refuses_a_reference_into_the_tail_from_outside(self) -> None:
        """The in-place applier rewrites only the tail records, which is exact
        only while nothing outside the tail spells a tail number. A file that
        does — here a part name — must be refused, not partially renumbered."""
        import cadgen.step_export as step_export

        with tempfile.TemporaryDirectory(prefix="step-guard-") as tmp:
            scans: list = []
            original = step_export._style_tail_scan

            def capture(model):
                scan = original(model)
                scans.append(scan)
                return scan

            step_export._style_tail_scan = capture
            try:
                out = Path(tmp) / "guarded.step"
                self._write_with("text", out)
            finally:
                step_export._style_tail_scan = original
            scan = scans[-1]
            self.assertIsNotNone(scan)
            canonical = out.read_bytes()
            # Already canonical: applying again is a no-op and is accepted.
            self.assertTrue(step_export._canonicalize_style_tail_in_file(out, scan))
            self.assertEqual(out.read_bytes(), canonical)
            # A pre-tail string that mentions a tail number is refused, even
            # though a reference regex would never have rewritten it: the
            # guard is deliberately conservative.
            tampered = canonical.replace(
                b"PRODUCT('determinism_rig'",
                b"PRODUCT('rig #%d'" % scan.tail_start,
                1,
            )
            self.assertNotEqual(tampered, canonical, "the rig's product name moved")
            out.write_bytes(tampered)
            self.assertFalse(step_export._canonicalize_style_tail_in_file(out, scan))
            self.assertEqual(out.read_bytes(), tampered, "a refused file must be untouched")

    def test_tail_reference_pattern_matches_exactly_the_tail_numbers(self) -> None:
        """The pre-tail guard is one compiled range pattern over the whole
        file; it must match every tail number (leading zeros included, since
        ``int()`` would map those into the tail too) and nothing else."""
        from cadgen.step_export import _tail_reference_pattern

        for tail_start, total in ((39957, 44756), (100, 999), (5, 5), (1000, 1000), (2960431, 3012345)):
            pattern = _tail_reference_pattern(tail_start, total)
            width = len(str(total))
            low = max(1, tail_start - 1500)
            for value in list(range(low, min(total, tail_start + 1500))) + list(range(max(low, total - 1500), total + 1500)):
                expected = tail_start <= value <= total
                for spelling in (b"#%d" % value, b"#00%d" % value):
                    self.assertEqual(
                        pattern.fullmatch(spelling) is not None, expected,
                        f"{spelling!r} against [{tail_start}, {total}]",
                    )
            self.assertIsNone(pattern.search(b"#%d0" % tail_start), "a longer number is not a tail reference")
            self.assertIsNotNone(pattern.search(b"(#%d,#%d)" % (tail_start - 1, total)))
            self.assertEqual(len(str(tail_start)), width, "fixture ranges are same-width")

    def test_styled_item_target_reads_the_third_parameter(self) -> None:
        from cadgen.step_export import _styled_item_target

        self.assertEqual(_styled_item_target(b"#39958 = STYLED_ITEM('color',(#39959),#196);\n"), 196)
        # OCCT wraps long records at a fixed column with an indented continuation.
        self.assertEqual(
            _styled_item_target(
                b"#39966 = OVER_RIDING_STYLED_ITEM('overriding color',(#39967),#196,#39958\n  );\n"
            ),
            196,
        )
        self.assertEqual(
            _styled_item_target(b"#7 = OVER_RIDING_STYLED_ITEM('a, (b) #9',(#1,\n  #2),\n  #44678,#3);\n"),
            44678,
        )
        self.assertIsNone(_styled_item_target(b"#7 = STYLED_ITEM('',(#1),$);\n"))
        self.assertIsNone(_styled_item_target(b"#7 = STYLED_ITEM('',(#1));\n"))

    def test_canonicalization_is_a_pure_reorder(self) -> None:
        """The canonical file must carry the same entity population — sorted
        entity RECORD bodies (numbers stripped) are invariant across runs even
        without canonicalization, so equality here plus byte-equality above
        means reordering, not rewriting."""
        from cadgen.step_export import export_build123d_step_file

        import re

        with tempfile.TemporaryDirectory(prefix="step-determinism-") as tmp:
            out = Path(tmp) / "one.step"
            export_build123d_step_file(_build_assembly(), out)
            text = out.read_text()
            styled = re.findall(r"= (?:OVER_RIDING_)?STYLED_ITEM\(", text)
            colours = re.findall(r"COLOUR_RGB\('',([^)]*)\)", text)
            self.assertGreaterEqual(len(styled), 6, "rig must exercise the styled path")
            self.assertEqual(len(set(colours)), 6, "all six authored colors survive")


# Every real spelling OCCT's writer can put in a numeric field, paired with
# what the canonical file must carry.
NEGATIVE_ZERO_CASES = [
    (b"DIRECTION('',(-0.,1.,0.));", b"DIRECTION('',(0.,1.,0.));"),
    (b"DIRECTION('',(-0.,-0.,1.));", b"DIRECTION('',(0.,0.,1.));"),
    (b"CARTESIAN_POINT('',(-0.0,2.5,-0.000));", b"CARTESIAN_POINT('',(0.0,2.5,0.000));"),
    (b"VECTOR('',#7,-0.);", b"VECTOR('',#7,0.);"),
    (b"(-0.E-5,-0.0E+10,1.)", b"(0.E-5,0.0E+10,1.)"),
    (b"(-.0,1.)", b"(.0,1.)"),
    # Genuinely negative reals keep their sign, however small.
    (b"DIRECTION('',(-0.5,-1.,0.));", b"DIRECTION('',(-0.5,-1.,0.));"),
    (b"(-0.000000000001,-6.123233995737E-17)", b"(-0.000000000001,-6.123233995737E-17)"),
    # A number inside a name is not a number.
    (b"PRODUCT('rev-0.','-0.',(#6));", b"PRODUCT('rev-0.','-0.',(#6));"),
    (b"PRODUCT('bracket-0.1','x''-0.',(#6));", b"PRODUCT('bracket-0.1','x''-0.',(#6));"),
    # Token boundaries: neither of these is a real of its own.
    (b"(1.-0.,1.E-0,1.E-05)", b"(1.-0.,1.E-0,1.E-05)"),
    (b"(#10,-0,3)", b"(#10,-0,3)"),
]


class NegativeZeroNormalizationTest(unittest.TestCase):
    """The text pass, on raw STEP text."""

    def test_every_spelling_normalizes_or_survives(self) -> None:
        from cadgen.step_export import _normalize_negative_zero_reals

        for source, expected in NEGATIVE_ZERO_CASES:
            with self.subTest(source=source):
                self.assertEqual(expected, _normalize_negative_zero_reals(source))

    def test_the_pass_is_idempotent(self) -> None:
        from cadgen.step_export import _normalize_negative_zero_reals

        text = b"\n".join(source for source, _expected in NEGATIVE_ZERO_CASES)
        once = _normalize_negative_zero_reals(text)
        self.assertEqual(once, _normalize_negative_zero_reals(once))

    def test_the_file_pass_matches_the_text_pass_across_block_boundaries(self) -> None:
        """The in-place rewrite streams in blocks; a block boundary must not
        split a token or let a rewritten block desynchronize the rest."""
        from cadgen import step_export

        text = b"\n".join(source for source, _expected in NEGATIVE_ZERO_CASES) + b"\n"
        expected = b"\n".join(expected for _source, expected in NEGATIVE_ZERO_CASES) + b"\n"
        with tempfile.TemporaryDirectory(prefix="step-negative-zero-") as tmp:
            for block in (7, 16, 41, 1 << 20):
                path = Path(tmp) / f"block{block}.step"
                path.write_bytes(text)
                with mock.patch.object(step_export, "_NEGATIVE_ZERO_BLOCK", block):
                    changed = step_export._normalize_negative_zero_reals_in_file(path)
                self.assertTrue(changed)
                self.assertEqual(expected, path.read_bytes(), f"block size {block}")

    def test_a_file_with_no_negative_zero_is_left_alone(self) -> None:
        from cadgen import step_export

        text = b"#1 = DIRECTION('',(0.,1.,-0.5));\n"
        with tempfile.TemporaryDirectory(prefix="step-negative-zero-") as tmp:
            path = Path(tmp) / "clean.step"
            path.write_bytes(text)
            self.assertFalse(step_export._normalize_negative_zero_reals_in_file(path))
            self.assertEqual(text, path.read_bytes())


# The pass that defined the canonical bytes, kept here as the oracle: one regex
# that consumed every string literal whole, exact and slow (a few tens of MB/s).
# The candidate-driven pass must write its bytes for ANY block -- the bytes are
# the store key -- including one that ends inside a literal OCCT wrapped.
_REGEX_PASS = re.compile(
    rb"'(?:[^']|'')*'"
    rb"|(?<![0-9.eE+-])-(?:0+\.0*|0*\.0+)(?:[eE][-+]?[0-9]+)?(?![0-9.eE])"
)


def _regex_pass(text: bytes) -> bytes:
    return _REGEX_PASS.sub(lambda match: match[0] if match[0].startswith(b"'") else match[0][1:], text)


# Building blocks for random STEP-like text: reals of every spelling, numbers
# glued together, literals with escaped quotes and lone quotes that leave a
# block unbalanced, and line breaks that wrap a record or a literal.
_FUZZ_TOKENS = [
    b"-0.", b"-0.0", b"-00.", b"-.0", b"-0.E+00", b"-0.0E+00", b"-0.e-3", b"-0.E", b"-0.0E+0.",
    b"-0.5", b"-0.0001", b"-1.E-03", b"-0", b"-.", b"0.", b"1.-0.", b"E-0", b"5.E-05",
    b"'", b"''", b"'''", b"'a'", b"'rev-0.0'", b"'x''-0.'",
    b"(", b")", b",", b" ", b"\n", b"\n  ", b"=", b"#12", b"CARTESIAN_POINT",
    b".", b"e", b"E", b"+", b"-", b"0", b"9",
]


class CandidatePassWritesTheRegexBytesTest(unittest.TestCase):
    def test_spellings_literals_escapes_and_wrapped_records(self) -> None:
        from cadgen.step_export import _normalize_negative_zero_reals

        blocks = [
            *(source for source, _expected in NEGATIVE_ZERO_CASES),
            b"(-0.,-0.0,-00.,-.0,-0.E+00,-0.0E+00,-000.000E-000,-0.e7,-.0e+5)",
            b"(-0.0E+0.5,-0.E,-0.E+,-0.Ex,1.E-0.,-0.-0.,-0.5,-.5,-1.)",
            b"PRODUCT('-0.','a -0.0E+00 b',(#6),-0.);",
            # Escaped quotes: a literal that is one quote, one that ends in one.
            b"PRODUCT('it''s -0.','''-0.''','''',-0.,'x''','-0.',-0.E+00);",
            # A record OCCT wrapped across lines.
            b"#5 = B_SPLINE_CURVE_WITH_KNOTS('',3,(#6,#7,\n  #8),.UNSPECIFIED.,.F.,.F.,(4,4),(-0.,\n  -0.0E+00),.U.);\n",
            # A literal OCCT wrapped, whole, then split across two blocks.
            b"#9 = PRODUCT('a long name -0.\nstill the name -0.','',(#2));\n#10 = DIRECTION('',(-0.,1.,-0.));\n",
            b"#9 = PRODUCT('a long name -0.\n",
            b"still the name -0.','',(#2));\n#10 = DIRECTION('',(-0.,1.,-0.));\n",
        ]
        for block in blocks:
            with self.subTest(block=block):
                self.assertEqual(_regex_pass(block), _normalize_negative_zero_reals(block))

    def test_random_blocks(self) -> None:
        from cadgen.step_export import _normalize_negative_zero_reals

        rng = random.Random(20261001)
        rewritten = unbalanced = 0
        for _ in range(30_000):
            block = b"".join(rng.choice(_FUZZ_TOKENS) for _ in range(rng.randint(0, 60)))
            expected = _regex_pass(block)
            if expected != _normalize_negative_zero_reals(block):
                self.fail(f"the passes disagree on {block!r}")
            rewritten += expected != block
            unbalanced += block.count(b"'") % 2
        # Guards the generator as much as the pass.
        self.assertGreater(rewritten, 1_000)
        self.assertGreater(unbalanced, 1_000)


class WrittenStepCarriesNoNegativeZeroTest(unittest.TestCase):
    def test_the_writer_emits_negative_zero_and_the_pass_removes_it(self) -> None:
        """Guards the fixture as much as the fix: with the pass switched off the
        rig must still write a negative zero, or an assertion that the canonical
        file carries none would hold over a file that never had one."""
        from cadgen import step_export

        with tempfile.TemporaryDirectory(prefix="step-negative-zero-") as tmp:
            raw = Path(tmp) / "raw.step"
            with mock.patch.object(
                step_export, "_normalize_negative_zero_reals_in_file", lambda path: False
            ):
                step_export.export_build123d_step_file(_build_assembly(), raw)
            self.assertIn(b"-0.,", raw.read_bytes(), "fixture no longer reaches the defect")

            canonical = Path(tmp) / "canonical.step"
            step_export.export_build123d_step_file(_build_assembly(), canonical)
            written = canonical.read_bytes()
            self.assertNotIn(b"-0.,", written)
            self.assertNotIn(b"-0.)", written)
            # A pure sign-of-zero rewrite: the raw file normalizes to the
            # canonical one and nothing else moved.
            self.assertEqual(
                written,
                step_export._normalize_negative_zero_reals(raw.read_bytes()),
            )


if __name__ == "__main__":
    unittest.main()
