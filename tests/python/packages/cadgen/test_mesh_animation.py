"""`cadgen glb build --animation`: the request's shape, and every refusal.

What Python owns of an animated export is the REQUEST — its closed key set, its
bounds, the clip name checked against the module beside the document, and the
freshness variant that makes an edited `.step.js` a miss. The sampling itself is
JavaScript and is tested there (packages/cadgen-js/src/lib/export).

Every test below is a file that would otherwise have been written: a clip
dropped into an STL, a bad fps discovered after a tessellation, a typo'd clip
name surfacing as a Node stack trace, a GLB reported current with last week's
motion baked in.
"""

from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests.python.support.paths import add_repo_path

add_repo_path("packages/cadgen/src")

from cadgen._internal.mesh_animation import (  # noqa: E402
    DEFAULT_MORPH_TOLERANCE_MM,
    MAX_ANIMATION_SAMPLES,
    MAX_MORPH_TOLERANCE_MM,
    MIN_MORPH_TOLERANCE_MM,
    animation_variant_token,
    normalize_animation_request,
    parse_animation_option,
    resolve_animation,
)
from cadgen._internal.mesh_door import mesh_build  # noqa: E402
from cadgen._internal.mesh_export import mesh_variant_key  # noqa: E402
from cadgen.cli import glb_build  # noqa: E402

MODULE_SOURCE = """
export const clips = {
  showcase: { duration: 8, update(t, m) { m.get("arm").rotate([0, 0, 1], t); } },
  teardown: { duration: 4, update(t, m) { m.get("arm").translate([t, 0, 0]); } },
};
"""


class TheRequestShape(unittest.TestCase):
    """A closed key set, checked before a builder starts."""

    def test_a_bare_clip_name_is_the_whole_request(self):
        self.assertEqual(
            {"clip": "showcase", "fps": 30, "seconds": None, "start": 0.0, "drop": [], "deform": "refuse"},
            parse_animation_option("showcase"),
        )

    def test_inline_json_and_a_real_dict_are_the_same_request(self):
        expected = {
            "clip": "showcase", "fps": 24, "seconds": 3.0, "start": 1.5,
            "drop": ["opacity"], "deform": "rest",
        }
        request = {"clip": "showcase", "fps": 24, "seconds": 3, "start": 1.5,
                   "drop": ["opacity"], "deform": "rest"}
        self.assertEqual(expected, parse_animation_option(request))
        self.assertEqual(expected, parse_animation_option(json.dumps(request)))

    def test_seconds_stays_unresolved_because_only_the_clip_knows_its_duration(self):
        # The default is what is LEFT of the clip from `start`, which lives in
        # JavaScript. None travels to the builder, which resolves it there.
        self.assertIsNone(parse_animation_option({"clip": "showcase", "start": 2})["seconds"])

    def test_an_unknown_key_names_the_ones_that_exist(self):
        with self.assertRaises(ValueError) as caught:
            parse_animation_option({"clip": "showcase", "quality": "high"})
        self.assertIn("unknown key(s): quality", str(caught.exception))
        # A video's vocabulary is not this one: fps means a different thing and
        # quality means nothing at all.
        self.assertIn("clip, deform, deformTolerance, drop, fps, seconds, start", str(caught.exception))

    def test_a_request_that_names_no_clip_is_refused(self):
        for value in ({}, {"fps": 30}, {"clip": "   "}, ""):
            with self.subTest(value=value), self.assertRaises(ValueError):
                parse_animation_option(value)

    def test_fps_is_a_whole_number_inside_its_bounds(self):
        for fps in (0, 121, 29.97, True, "30"):
            with self.subTest(fps=fps), self.assertRaises(ValueError) as caught:
                parse_animation_option({"clip": "showcase", "fps": fps})
            self.assertIn("fps must be", str(caught.exception))

    def test_a_span_past_the_sample_ceiling_is_refused_by_name(self):
        # fps alone bounds nothing: the count is fps TIMES seconds, and a caller
        # writing milliseconds reaches six figures through the other one.
        with self.assertRaises(ValueError) as caught:
            parse_animation_option({"clip": "showcase", "fps": 30, "seconds": 3000})
        self.assertIn("90000 samples", str(caught.exception))
        self.assertIn(f"{MAX_ANIMATION_SAMPLES}-sample ceiling", str(caught.exception))
        # The ceiling itself is reachable.
        self.assertEqual(
            float(MAX_ANIMATION_SAMPLES) / 30,
            parse_animation_option(
                {"clip": "showcase", "fps": 30, "seconds": MAX_ANIMATION_SAMPLES / 30}
            )["seconds"],
        )

    def test_seconds_and_start_must_be_real_spans(self):
        for request in (
            {"clip": "showcase", "seconds": 0},
            {"clip": "showcase", "seconds": -1},
            {"clip": "showcase", "seconds": float("inf")},
            {"clip": "showcase", "start": -0.5},
            {"clip": "showcase", "start": "soon"},
        ):
            with self.subTest(request=request), self.assertRaises(ValueError):
                parse_animation_option(request)

    def test_drop_names_only_effects_this_export_can_bake_static(self):
        with self.assertRaises(ValueError) as caught:
            parse_animation_option({"clip": "showcase", "drop": ["deformTube"]})
        self.assertIn("only these effects can be baked static: opacity, visible", str(caught.exception))
        # A bare string is a common near-miss and is not a list of names.
        with self.assertRaises(ValueError):
            parse_animation_option({"clip": "showcase", "drop": "opacity"})
        self.assertEqual(
            ["opacity", "visible"],
            parse_animation_option({"clip": "showcase", "drop": ["visible", "opacity", "opacity"]})["drop"],
        )

    def test_deform_is_one_of_three_words(self):
        with self.assertRaises(ValueError) as caught:
            parse_animation_option({"clip": "showcase", "deform": "freeze"})
        self.assertIn("deform must be one of: refuse, morph, rest", str(caught.exception))
        self.assertEqual("refuse", parse_animation_option("showcase")["deform"])

    def test_a_morph_bake_carries_its_tolerance_and_nothing_else_does(self):
        # The tolerance is how close the baked targets must stay to the clip's own
        # deformation, so it means nothing without a bake. Accepting it anywhere
        # else would read as a promise about the file that the file does not keep.
        morph = parse_animation_option({"clip": "showcase", "deform": "morph"})
        self.assertEqual(DEFAULT_MORPH_TOLERANCE_MM, morph["deformTolerance"])
        self.assertEqual(
            0.25,
            parse_animation_option(
                {"clip": "showcase", "deform": "morph", "deformTolerance": 0.25}
            )["deformTolerance"],
        )
        for mode in ("refuse", "rest"):
            request = parse_animation_option({"clip": "showcase", "deform": mode})
            self.assertNotIn("deformTolerance", request)
            with self.assertRaises(ValueError) as caught:
                parse_animation_option(
                    {"clip": "showcase", "deform": mode, "deformTolerance": 0.5}
                )
            self.assertIn('deform is ' + repr(mode), str(caught.exception))
            self.assertIn('pass deform: "morph"', str(caught.exception))

    def test_the_morph_tolerance_is_bounded_in_millimetres(self):
        for bad in (0, MIN_MORPH_TOLERANCE_MM / 2, MAX_MORPH_TOLERANCE_MM * 2, -1):
            with self.assertRaises(ValueError) as caught:
                parse_animation_option(
                    {"clip": "showcase", "deform": "morph", "deformTolerance": bad}
                )
            self.assertIn("deformTolerance must be", str(caught.exception))
        with self.assertRaises(ValueError) as caught:
            parse_animation_option(
                {"clip": "showcase", "deform": "morph", "deformTolerance": "fine"}
            )
        self.assertIn("deformTolerance must be a number", str(caught.exception))

    def test_the_tolerance_re_keys_the_export_but_a_static_request_is_untouched(self):
        # Two bakes of one clip at two tolerances are two different files, so the
        # ledger must not serve one for the other. A request that never asked for
        # a bake keeps exactly the canonical form -- and the token -- it always had.
        loose = animation_variant_token(
            parse_animation_option({"clip": "showcase", "deform": "morph", "deformTolerance": 1.0}),
            MODULE_SOURCE,
        )
        tight = animation_variant_token(
            parse_animation_option({"clip": "showcase", "deform": "morph", "deformTolerance": 0.25}),
            MODULE_SOURCE,
        )
        self.assertNotEqual(loose, tight)
        self.assertEqual(
            {"clip": "showcase", "fps": 30, "seconds": None, "start": 0.0, "drop": [], "deform": "rest"},
            parse_animation_option({"clip": "showcase", "deform": "rest"}),
        )

    def test_a_job_packet_and_the_flag_share_one_validator(self):
        with self.assertRaises(ValueError) as caught:
            normalize_animation_request({"clip": "showcase", "loop": True}, where="render job animation")
        self.assertIn("render job animation has unknown key(s): loop", str(caught.exception))


class TheFreshnessVariant(unittest.TestCase):
    """An animated GLB is not a function of the document's bytes alone."""

    def test_the_token_moves_with_the_clip_source_and_with_the_request(self):
        request = parse_animation_option("showcase")
        base = animation_variant_token(request, MODULE_SOURCE)
        self.assertEqual(base, animation_variant_token(dict(request), MODULE_SOURCE))
        # An edited .step.js is a DIFFERENT export of the same document bytes.
        self.assertNotEqual(base, animation_variant_token(request, MODULE_SOURCE + "\n"))
        # So is a different span of the same clip.
        self.assertNotEqual(
            base, animation_variant_token(parse_animation_option({"clip": "showcase", "fps": 24}), MODULE_SOURCE)
        )

    def test_a_static_variant_key_is_unchanged_and_an_animated_one_cannot_collide(self):
        static = mesh_variant_key("glb", None, None)
        self.assertEqual("glb|default|default", static)
        animated = mesh_variant_key("glb", None, None, "deadbeef")
        self.assertNotEqual(static, animated)
        self.assertTrue(animated.startswith(static))


class ResolvingTheClip(unittest.TestCase):
    """The render module beside the document, read before anything tessellates."""

    def setUp(self) -> None:
        stack = contextlib.ExitStack()
        self.addCleanup(stack.close)
        self.root = Path(stack.enter_context(tempfile.TemporaryDirectory())).resolve()
        self.document = self.root / "arm.step"
        self.document.write_text("ISO-10303-21;\n", encoding="utf-8")

    def _write_module(self) -> Path:
        module = self.root / "arm.step.js"
        module.write_text(MODULE_SOURCE, encoding="utf-8")
        return module

    def test_a_document_with_no_render_module_says_what_to_author(self):
        with self.assertRaises(ValueError) as caught:
            resolve_animation(self.document, parse_animation_option("showcase"))
        self.assertIn("arm.step has no render module", str(caught.exception))
        self.assertIn("arm.step.js", str(caught.exception))

    def test_a_clip_the_module_does_not_declare_fails_with_the_ones_it_does(self):
        self._write_module()
        with self.assertRaises(ValueError) as caught:
            resolve_animation(self.document, parse_animation_option("showcse"))
        self.assertIn("Unknown animation clip: showcse", str(caught.exception))
        self.assertIn("This model declares: showcase, teardown", str(caught.exception))

    def test_a_declared_clip_resolves_to_the_module_and_a_variant_token(self):
        module = self._write_module()
        path, token = resolve_animation(self.document, parse_animation_option("teardown"))
        self.assertEqual(module, path)
        self.assertEqual(animation_variant_token(parse_animation_option("teardown"), MODULE_SOURCE), token)


class WhatCannotCarryAClip(unittest.TestCase):
    """Refused by name at every shared surface a clip could be dropped at."""

    def setUp(self) -> None:
        stack = contextlib.ExitStack()
        self.addCleanup(stack.close)
        stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
        root = Path(stack.enter_context(tempfile.TemporaryDirectory())).resolve()
        self.document = root / "arm.step"
        self.document.write_text("ISO-10303-21;\n", encoding="utf-8")
        (root / "arm.step.js").write_text(MODULE_SOURCE, encoding="utf-8")

    def test_the_stl_and_3mf_doors_refuse_a_clip_rather_than_dropping_it(self):
        # mesh_build IS those doors' body, so this is where a clip reaching a
        # format with nowhere to put one has to stop.
        for fmt in ("stl", "3mf"):
            with self.subTest(format=fmt), self.assertRaises(ValueError) as caught:
                mesh_build(
                    fmt, self.document, None,
                    mesh_tolerance=None, mesh_angular_tolerance=None,
                    animation="showcase", force=False, verbose=False,
                )
            self.assertIn(f"{fmt} carries no animation", str(caught.exception))
            self.assertIn("cadgen glb build --animation", str(caught.exception))

    def test_the_engine_refuses_a_clip_against_a_non_glb_output(self):
        from cadgen.step_export_target import export_cad_target

        with self.assertRaises(ValueError) as caught:
            export_cad_target(self.document, [("stl", None)], animation="showcase")
        self.assertIn("stl carries no animation", str(caught.exception))

    def test_an_animated_export_requires_an_out_path(self):
        # With no OUT a mesh door writes the model's DECLARED @glb, which is its
        # static output at a committed path. An animated file there is a
        # different artifact -- one node per occurrence, opening at the clip's
        # first frame -- sitting dirty in the tree until the next script run.
        with self.assertRaises(ValueError) as caught:
            mesh_build(
                "glb", self.document, None,
                mesh_tolerance=None, mesh_angular_tolerance=None,
                animation="showcase", force=False, verbose=False,
            )
        self.assertIn("an animated export is ad hoc: name an OUT path", str(caught.exception))

    def test_the_engine_refuses_an_animated_declaration_too(self):
        from cadgen.step_export_target import export_cad_target

        with self.assertRaises(ValueError) as caught:
            export_cad_target(self.document, [("glb", None)], animation="showcase")
        self.assertIn("an animated export is ad hoc", str(caught.exception))

    def test_an_unknown_clip_fails_the_glb_door_before_any_meshing(self):
        # The whole point of resolving the clip in Python: a typo must not cost a
        # tessellation, and must not surface as a Node stack trace.
        stderr = io.StringIO()
        with mock.patch(
            "cadgen.step_export_target._resolve_mesh_package",
            side_effect=AssertionError("the clip must be resolved before the package is"),
        ), contextlib.redirect_stderr(stderr):
            self.assertEqual(1, glb_build.main([
                str(self.document), str(self.document.with_suffix(".glb")),
                "--animation", "nope",
            ]))
        self.assertIn("Unknown animation clip: nope", stderr.getvalue())
        self.assertIn("showcase, teardown", stderr.getvalue())


class TheDoorPassesItThrough(unittest.TestCase):
    """`cadgen glb build --animation` reaches the engine as itself."""

    def setUp(self) -> None:
        stack = contextlib.ExitStack()
        self.addCleanup(stack.close)
        stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
        root = Path(stack.enter_context(tempfile.TemporaryDirectory())).resolve()
        self.document = root / "arm.step"
        self.document.write_text("ISO-10303-21;\n", encoding="utf-8")
        (root / "arm.step.js").write_text(MODULE_SOURCE, encoding="utf-8")
        self.out = root / "arm-demo.glb"

    @contextlib.contextmanager
    def _engine(self):
        payload = {
            "ok": True,
            "files": [{
                "format": "glb", "path": "/abs/arm.glb", "skipped": False,
                "meshTolerance": None, "meshAngularTolerance": None,
            }],
        }
        with mock.patch(
            "cadgen.step_export_target.export_cad_target", return_value=payload
        ) as export:
            yield export

    def test_a_clip_name_and_an_inline_request_both_reach_the_engine(self):
        for value in ("showcase", '{"clip": "showcase", "fps": 24}'):
            with self.subTest(value=value), self._engine() as export:
                self.assertEqual(0, glb_build.main([
                    str(self.document), str(self.out), "--animation", value,
                ]))
            self.assertEqual(value, export.call_args.kwargs["animation"])

    def test_no_animation_is_the_default_and_stays_None(self):
        with self._engine() as export:
            self.assertEqual(0, glb_build.main([str(self.document)]))
        self.assertIsNone(export.call_args.kwargs["animation"])

    def test_the_result_names_the_clip_and_the_schedule_it_baked(self):
        # The span is DERIVED (a clip states its own duration), so a wrong clip
        # or a wrong span has to show without opening the file — the same reason
        # a video reports its frame count.
        payload = {
            "ok": True,
            "files": [{
                "format": "glb", "path": "/abs/arm.glb", "skipped": False,
                "meshTolerance": None, "meshAngularTolerance": None,
                "animation": {
                    "clip": "showcase", "fps": 30, "samples": 240,
                    "seconds": 8.0, "start": 0.0, "channels": 3,
                },
            }],
        }
        out = io.StringIO()
        with mock.patch(
            "cadgen.step_export_target.export_cad_target", return_value=payload
        ), contextlib.redirect_stdout(out):
            self.assertEqual(0, glb_build.main([
                str(self.document), str(self.out), "--animation", "showcase",
            ]))
        self.assertEqual(
            [f"wrote GLB: {Path('/abs/arm.glb')} (showcase, 240 samples @ 30 fps, 8s, 3 moving)"],
            out.getvalue().splitlines(),
        )

    def test_a_morph_bake_says_what_it_cost_and_which_of_the_moving_are_tubes(self):
        # Without this clause the line is wrong twice: each deforming tube's
        # weights channel counts toward "moving" exactly like a part that
        # travels, and the numbers that decide whether the file is any good --
        # the target count, how close they track, and the playback texture a GPU
        # has to hold -- appear nowhere a human reads.
        payload = {
            "ok": True,
            "files": [{
                "format": "glb", "path": "/abs/hand.glb", "skipped": False,
                "meshTolerance": None, "meshAngularTolerance": None,
                "animation": {
                    "clip": "fist", "fps": 24, "samples": 145, "seconds": 6.0,
                    "start": 0.0, "channels": 51,
                    "deform": {
                        "mode": "morph", "nodes": 48, "targets": 1523,
                        "bytes": 41943040, "runtimeBytes": 728330240,
                        "refinedTriangles": 1252544, "deviationMm": 0.987,
                        "toleranceMm": 1.0, "fitGridHz": 96,
                    },
                },
            }],
        }
        out = io.StringIO()
        with mock.patch(
            "cadgen.step_export_target.export_cad_target", return_value=payload
        ), contextlib.redirect_stdout(out):
            self.assertEqual(0, glb_build.main([
                str(self.document), str(self.out), "--animation", "fist",
            ]))
        self.assertEqual(
            [
                f"wrote GLB: {Path('/abs/hand.glb')} (fist, 145 samples @ 24 fps, 6s, "
                "51 moving, morph on 48 of them: 1523 targets, 0.987mm of 1mm, "
                "694.6 MiB at playback)"
            ],
            out.getvalue().splitlines(),
        )

    def test_what_the_sampling_could_not_carry_is_in_the_result_itself(self):
        # The builder's warnings used to go to the log and nowhere else, so
        # `--json` -- the surface an agent reads -- said nothing about a frozen
        # opacity or a tube shipped at rest. For a door whose whole premise is
        # that the file must not lie about the model, that is the one place the
        # drops had to be.
        payload = {
            "ok": True,
            "files": [{
                "format": "glb", "path": "/abs/arm.glb", "skipped": False,
                "meshTolerance": None, "meshAngularTolerance": None,
                "animation": {
                    "clip": "showcase", "fps": 30, "samples": 240,
                    "seconds": 8.0, "start": 0.0, "channels": 3,
                },
            }],
            "warnings": [".opacity() is not an animated glTF channel: o1.1 carries its value"],
        }
        out = io.StringIO()
        with mock.patch(
            "cadgen.step_export_target.export_cad_target", return_value=payload
        ), contextlib.redirect_stdout(out):
            self.assertEqual(0, glb_build.main([
                str(self.document), str(self.out),
                "--animation", '{"clip": "showcase", "drop": ["opacity"]}',
            ]))
        self.assertIn("warning: .opacity() is not an animated glTF channel", out.getvalue())


class WhatTheLedgerServes(unittest.TestCase):
    """A skipped animated export still says what the file on disk carries."""

    def setUp(self) -> None:
        stack = contextlib.ExitStack()
        self.addCleanup(stack.close)
        stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
        stack.enter_context(contextlib.redirect_stderr(io.StringIO()))
        root = Path(stack.enter_context(tempfile.TemporaryDirectory())).resolve()
        self.document = root / "arm.step"
        self.document.write_text("ISO-10303-21;\n", encoding="utf-8")
        (root / "arm.step.js").write_text(MODULE_SOURCE, encoding="utf-8")
        self.out = root / "arm-demo.glb"

    def _run(self, animation, *, written, baked):
        """``export_cad_target`` with the tessellation stubbed out.

        The clip resolves for real against the module beside the document; only
        the meshing is replaced, because what is under test is what the door
        REPORTS about a job the ledger already satisfied.
        """
        from cadgen import step_export_target

        spec = mock.Mock()
        spec.step_path = self.document
        with mock.patch.object(
            step_export_target, "_resolve_mesh_package", return_value=(spec, Path("/pkg"), None)
        ), mock.patch.object(
            step_export_target, "_effective_export_tolerances", return_value=(None, None)
        ), mock.patch.object(
            step_export_target, "_export_mesh_jobs", return_value=(written, baked)
        ):
            return step_export_target.export_cad_target(
                self.document, [("glb", self.out)], animation=animation
            )

    def test_a_ledgered_animated_file_reports_its_clip_not_a_static_export(self):
        # `animation: None` is documented as "a static export", so reporting it
        # for a file with a clip baked in tells an agent the opposite of the
        # truth -- and the same command said the opposite thing the run before.
        payload = self._run("showcase", written=frozenset(), baked={})
        entry = payload["files"][0]
        self.assertTrue(entry["skipped"])
        self.assertEqual(
            {"clip": "showcase", "fps": 30, "samples": None,
             "seconds": None, "start": 0.0, "channels": None},
            entry["animation"],
        )

    def test_a_skipped_export_that_baked_effects_static_says_it_is_not_repeating_them(self):
        payload = self._run(
            {"clip": "showcase", "drop": ["opacity"]}, written=frozenset(), baked={}
        )
        self.assertEqual(1, len(payload["warnings"]))
        self.assertIn("is current for clip showcase", payload["warnings"][0])
        # A clean request has nothing it failed to repeat, so it stays quiet.
        quiet = self._run("showcase", written=frozenset(), baked={})
        self.assertEqual([], quiet["warnings"])

    def test_a_skipped_morph_export_has_nothing_frozen_to_warn_about(self):
        # A morph bake FREEZES NOTHING: that is the whole point of the mode, and
        # the warning it used to draw claims the file has occurrences standing
        # still that the re-run would have named. `deform: "rest"` is the mode
        # that freezes, and `refuse` never wrote a file at all.
        for deform, expected in (("morph", []), ("refuse", []), ("rest", 1)):
            with self.subTest(deform=deform):
                payload = self._run(
                    {"clip": "showcase", "deform": deform}, written=frozenset(), baked={}
                )
                if expected == []:
                    self.assertEqual([], payload["warnings"])
                else:
                    self.assertEqual(expected, len(payload["warnings"]))
                    self.assertIn("is current for clip showcase", payload["warnings"][0])
        # ...and a drop still speaks up whatever the deform mode is.
        payload = self._run(
            {"clip": "showcase", "deform": "morph", "drop": ["opacity"]},
            written=frozenset(), baked={},
        )
        self.assertEqual(1, len(payload["warnings"]))

    def test_a_freshly_written_file_reports_the_schedule_and_lifts_its_warnings_out(self):
        payload = self._run(
            "showcase",
            written=frozenset({self.out}),
            baked={self.out: {
                "clip": "showcase", "fps": 30, "samples": 240, "seconds": 8.0,
                "start": 0.0, "channels": 3, "warnings": ["o1.2 has no geometry"],
            }},
        )
        entry = payload["files"][0]
        self.assertFalse(entry["skipped"])
        # The warnings ride out of the per-file block into the run's own, so one
        # place answers "what did this export not carry".
        self.assertNotIn("warnings", entry["animation"])
        self.assertEqual(["o1.2 has no geometry"], payload["warnings"])


if __name__ == "__main__":
    unittest.main()
