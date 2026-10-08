"""`cadgen glb build --animation`: the request's shape, and every refusal.

What this file pins of an animated export is the REQUEST — its closed key set,
its bounds, the clip name checked against the clips baked into the document's
sidecar, and the freshness variant that makes a rebaked animation a miss. What
the export makes of the clip is pinned in test_glb_animation.py.

Every test below is a file that would otherwise have been written: a clip
dropped into an STL, a bad span discovered after a tessellation, a typo'd clip
name surfacing after a minute of meshing, a GLB reported current with last
week's motion baked in.
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
    animation_variant_token,
    normalize_animation_request,
    parse_animation_option,
    resolve_animation,
)
from cadgen._internal.mesh_door import mesh_build  # noqa: E402
from cadgen._internal.mesh_export import GLB_SERIALIZATION_VERSION, MeshSource, mesh_variant_key  # noqa: E402
from cadgen.cli import glb_build  # noqa: E402

# The document sidecar's animation section, as a build bakes it: two clips of one part.
ANIMATION = {"clips": [
    {"id": "showcase", "label": "Showcase", "duration": 8, "loop": True,
     "tracks": [{"targets": ["o1.2"], "times": [0], "visible": [False]}]},
    {"id": "teardown", "label": "Teardown", "duration": 4, "loop": False,
     "tracks": [{"targets": ["o1.2"], "times": [0, 4], "opacity": [1, 0.25]}]},
]}
# What an export captures of it, and keys its variant on.
ANIMATION_DATA = json.dumps(ANIMATION, sort_keys=True, separators=(",", ":"))


class TheRequestShape(unittest.TestCase):
    """A closed key set, checked before a builder starts."""

    def test_a_bare_clip_name_is_the_whole_request(self):
        self.assertEqual(
            {"clip": "showcase", "seconds": None, "start": 0.0, "drop": []},
            parse_animation_option("showcase"),
        )

    def test_inline_json_and_a_real_dict_are_the_same_request(self):
        expected = {"clip": "showcase", "seconds": 3.0, "start": 1.5, "drop": ["opacity"]}
        request = {"clip": "showcase", "seconds": 3, "start": 1.5, "drop": ["opacity"]}
        self.assertEqual(expected, parse_animation_option(request))
        self.assertEqual(expected, parse_animation_option(json.dumps(request)))

    def test_seconds_stays_unresolved_because_only_the_clip_knows_its_duration(self):
        # The default is what is LEFT of the clip from `start`. None travels to
        # the export, which reads the clip and resolves it there.
        self.assertIsNone(parse_animation_option({"clip": "showcase", "start": 2})["seconds"])

    def test_an_unknown_key_names_the_ones_that_exist(self):
        with self.assertRaises(ValueError) as caught:
            parse_animation_option({"clip": "showcase", "quality": "high"})
        self.assertIn("unknown key(s): quality", str(caught.exception))
        # A video's vocabulary is not this one: quality means nothing to a file that
        # carries the clip itself.
        self.assertIn("clip, drop, seconds, start", str(caught.exception))

    def test_a_request_that_names_no_clip_is_refused(self):
        for value in ({}, {"seconds": 3}, {"clip": "   "}, ""):
            with self.subTest(value=value), self.assertRaises(ValueError):
                parse_animation_option(value)

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
            parse_animation_option({"clip": "showcase", "drop": ["texture"]})
        self.assertIn("only these effects can be baked static: opacity, visible", str(caught.exception))
        # A bare string is a common near-miss and is not a list of names.
        with self.assertRaises(ValueError):
            parse_animation_option({"clip": "showcase", "drop": "opacity"})
        self.assertEqual(
            ["opacity", "visible"],
            parse_animation_option({"clip": "showcase", "drop": ["visible", "opacity", "opacity"]})["drop"],
        )

    def test_a_frame_rate_or_a_deform_mode_is_not_a_request_key(self):
        # The file carries the clip's own keys, so there is no rate to sample at, and a
        # bending tube is always a skin, so there is no mode to choose.
        for key in ("fps", "deform", "deformTolerance"):
            with self.subTest(key=key), self.assertRaises(ValueError) as caught:
                parse_animation_option({"clip": "showcase", key: 1})
            self.assertIn(f"unknown key(s): {key}", str(caught.exception))

    def test_a_job_packet_and_the_flag_share_one_validator(self):
        with self.assertRaises(ValueError) as caught:
            normalize_animation_request({"clip": "showcase", "loop": True}, where="render job animation")
        self.assertIn("render job animation has unknown key(s): loop", str(caught.exception))


class TheFreshnessVariant(unittest.TestCase):
    """An animated GLB is not a function of the document's bytes alone."""

    def test_the_token_moves_with_the_keyframes_and_with_the_request(self):
        request = parse_animation_option("showcase")
        base = animation_variant_token(request, ANIMATION_DATA)
        self.assertEqual(base, animation_variant_token(dict(request), ANIMATION_DATA))
        # A rebaked animation is a DIFFERENT export of the same document bytes.
        rebaked = ANIMATION_DATA.replace('"duration":8', '"duration":9')
        self.assertNotEqual(ANIMATION_DATA, rebaked)
        self.assertNotEqual(base, animation_variant_token(request, rebaked))
        # So is a different span of the same clip.
        self.assertNotEqual(
            base, animation_variant_token(parse_animation_option({"clip": "showcase", "seconds": 4}), ANIMATION_DATA)
        )

    def test_an_export_ledgered_for_other_keyframes_is_not_current(self):
        from cadgen._internal.mesh_export import document_mesh_current, record_document_mesh
        from cadgen.store.records import note_document_tree
        from tests.python.support.tmp_root import generated_cad_directory

        request = parse_animation_option("showcase")
        ledgered = animation_variant_token(request, ANIMATION_DATA)
        rebaked = animation_variant_token(request, ANIMATION_DATA.replace('"duration":8', '"duration":9'))
        with generated_cad_directory(prefix="animation-ledger-admission-") as folder:
            root = Path(folder)
            output = root / "arm.glb"
            output.write_bytes(b"an export of the keyframes the sidecar held then")
            with mock.patch.dict("os.environ", {"CADGEN_CACHE_DIR": str(root / "store")}):
                note_document_tree("a" * 64, "b" * 64)
                variant = dict(document_hash="a" * 64, fmt="glb", mesh_tolerance=None,
                               mesh_angular_tolerance=None)
                record_document_mesh(output, **variant, animation_key=ledgered)
                self.assertTrue(document_mesh_current(output, **variant, animation_key=ledgered))
                self.assertFalse(document_mesh_current(output, **variant, animation_key=rebaked))

    def test_a_static_variant_binds_absent_appearance_and_an_animated_one_cannot_collide(self):
        from cadgen._internal.source_sidecar import appearance_digest

        static = mesh_variant_key("glb", None, None)
        self.assertEqual(
            f"glb|default|default|serializer:{GLB_SERIALIZATION_VERSION}|appearance:{appearance_digest(None)}",
            static,
        )
        animated = mesh_variant_key("glb", None, None, "deadbeef")
        self.assertNotEqual(static, animated)
        self.assertTrue(animated.startswith(static))


class ResolvingTheClip(unittest.TestCase):
    """The keyframes in the document's sidecar, read before anything tessellates."""

    def setUp(self) -> None:
        stack = contextlib.ExitStack()
        self.addCleanup(stack.close)
        self.root = Path(stack.enter_context(tempfile.TemporaryDirectory())).resolve()
        self.document = self.root / "arm.step"
        self.document.write_text("ISO-10303-21;\n", encoding="utf-8")

    def _write_animation(self) -> None:
        from cadgen._internal.source_sidecar import write_source_sidecar
        write_source_sidecar(self.document, {"animation": ANIMATION})

    def test_a_document_with_no_animation_says_what_to_author(self):
        with self.assertRaises(ValueError) as caught:
            resolve_animation(self.document, parse_animation_option("showcase"))
        self.assertEqual(
            "arm.step has no animation in its sidecar. Declare animation= on @step.", str(caught.exception)
        )

    def test_a_clip_the_sidecar_does_not_hold_fails_with_the_ones_it_does(self):
        self._write_animation()
        with self.assertRaises(ValueError) as caught:
            resolve_animation(self.document, parse_animation_option("showcse"))
        self.assertEqual(
            "Unknown animation clip: showcse. This model declares: showcase, teardown", str(caught.exception)
        )

    def test_a_declared_clip_resolves_to_the_captured_keyframes_and_a_variant_token(self):
        import hashlib

        self._write_animation()
        snapshot, token = resolve_animation(self.document, parse_animation_option("teardown"))
        self.assertEqual(ANIMATION_DATA, snapshot.data)
        self.assertEqual(hashlib.sha256(self.document.read_bytes()).hexdigest(), snapshot.document_hash)
        self.assertEqual(animation_variant_token(parse_animation_option("teardown"), ANIMATION_DATA), token)


class WhatCannotCarryAClip(unittest.TestCase):
    """Refused by name at every shared surface a clip could be dropped at."""

    def setUp(self) -> None:
        stack = contextlib.ExitStack()
        self.addCleanup(stack.close)
        stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
        root = Path(stack.enter_context(tempfile.TemporaryDirectory())).resolve()
        self.document = root / "arm.step"
        self.document.write_text("ISO-10303-21;\n", encoding="utf-8")
        from cadgen._internal.source_sidecar import write_source_sidecar
        write_source_sidecar(self.document, {"animation": ANIMATION})

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
        # No OUT is reserved for the static sibling export. A clip changes the
        # artifact's structure and initial pose, so it needs an explicit path.
        with self.assertRaises(ValueError) as caught:
            mesh_build(
                "glb", self.document, None,
                mesh_tolerance=None, mesh_angular_tolerance=None,
                animation="showcase", force=False, verbose=False,
            )
        self.assertIn("an animated export is ad hoc: name an OUT path", str(caught.exception))

    def test_the_engine_requires_an_explicit_animated_output_too(self):
        from cadgen.step_export_target import export_cad_target

        with self.assertRaises(ValueError) as caught:
            export_cad_target(self.document, [("glb", None)], animation="showcase")
        self.assertIn("an animated export is ad hoc", str(caught.exception))

    def test_an_unknown_clip_fails_the_glb_door_before_any_meshing(self):
        # The whole point of resolving the clip first: a typo must not cost a
        # tessellation before it is reported.
        stderr = io.StringIO()
        with mock.patch(
            "cadgen.step_export_target._mesh_package",
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
        from cadgen._internal.source_sidecar import write_source_sidecar
        write_source_sidecar(self.document, {"animation": ANIMATION})
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
        for value in ("showcase", '{"clip": "showcase", "seconds": 4}'):
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
                    "clip": "showcase", "seconds": 8.0, "start": 0.0, "pivots": 3, "skins": 1, "joints": 11,
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
            [f"wrote GLB: {Path('/abs/arm.glb')} (showcase, 8s, 3 moving, 1 tube on 11 joints)"],
            out.getvalue().splitlines(),
        )

    def test_what_the_export_could_not_carry_is_in_the_result_itself(self):
        # The export's warnings used to go to the log and nowhere else, so
        # `--json` -- the surface an agent reads -- said nothing about a frozen
        # opacity. For a door whose whole premise is that the file must not lie
        # about the model, that is the one place the drops had to be.
        payload = {
            "ok": True,
            "files": [{
                "format": "glb", "path": "/abs/arm.glb", "skipped": False,
                "meshTolerance": None, "meshAngularTolerance": None,
                "animation": {"clip": "showcase", "seconds": 8.0, "start": 0.0, "pivots": 3, "skins": 0, "joints": 0},
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
        from cadgen._internal.source_sidecar import write_source_sidecar
        write_source_sidecar(self.document, {"animation": ANIMATION})
        self.out = root / "arm-demo.glb"

    def _run(self, animation, *, written, baked):
        """``export_cad_target`` with the tessellation stubbed out.

        The clip resolves for real against the document's sidecar; only
        the meshing is replaced, because what is under test is what the door
        REPORTS about a job the ledger already satisfied.
        """
        from cadgen import step_export_target

        spec = mock.Mock()
        spec.step_path = self.document
        with mock.patch.object(
            step_export_target, "_mesh_package", return_value=(spec, MeshSource("b" * 64, "a" * 64)),
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
            {"clip": "showcase", "seconds": None, "start": 0.0, "pivots": None, "skins": None, "joints": None},
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

    def test_a_freshly_written_file_reports_the_schedule_and_lifts_its_warnings_out(self):
        payload = self._run(
            "showcase",
            written=frozenset({self.out}),
            baked={self.out: {
                "clip": "showcase", "seconds": 8.0, "start": 0.0, "pivots": 3, "skins": 0, "joints": 0,
                "warnings": ["o1.2 has no geometry"],
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
