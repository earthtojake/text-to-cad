"""Embedded animation source: literal clip-name preflight, and the exports a
build refuses because the renderer would."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from tests.python.support.cad_test_roots import IsolatedCadRoots
from tests.python.support.paths import add_repo_path, repo_path

add_repo_path("packages/cadgen/src")

from cadgen._internal.animation_source import (  # noqa: E402
    ANIMATION_MODULE_EXPORTS,
    check_animation_exports,
    declared_clip_ids,
    module_exports,
    read_animation_source,
)

# The renderer's suite (renderModule.test.js) compiles these same sources for real.
PARITY = json.loads(
    repo_path("packages", "core", "src", "common", "renderModule.parity.json").read_text(encoding="utf-8")
)


class AnimationSidecarTests(unittest.TestCase):
    def test_reads_bound_animation_and_ignores_adjacent_javascript(self):
        import tempfile
        from pathlib import Path
        from cadgen._internal.source_sidecar import write_source_sidecar, SidecarBindingError

        with tempfile.TemporaryDirectory() as tmp:
            document = Path(tmp) / "arm.step"
            document.write_text("ISO-10303-21;", encoding="utf-8")
            document.with_suffix(".step.js").write_text("export const clips = {};", encoding="utf-8")
            self.assertIsNone(read_animation_source(document))
            source = "export const clips = { spin: {duration: 2, update(t,m) {}} };"
            write_source_sidecar(document, {"animation": {"language": "javascript", "source": source}})
            self.assertEqual(source, read_animation_source(document))
            document.write_text("different document", encoding="utf-8")
            with self.assertRaises(SidecarBindingError):
                read_animation_source(document)


class DeclaredClipIdsTests(unittest.TestCase):
    def test_reads_the_contract_form_in_declaration_order(self) -> None:
        text = """
        // embedded source
        export const clips = {
          demo: { label: "Demo", duration: 8, loop: true, update(t, m) { m.get("forearm").rotate([0, 0, 1], t); } },
          teardown: { duration: 5, update: (t, m) => { m.get("lid").opacity(1 - t / 5); } },
        };
        """
        self.assertEqual(["demo", "teardown"], declared_clip_ids(text))

    def test_nested_braces_strings_templates_and_comments_do_not_split_an_entry(self) -> None:
        text = (
            "export const clips = {\n"
            "  demo: { label: 'Demo }', duration: 8, update(t, m) {\n"
            "    if (t > 1) { m.get(`part-${Math.floor(t)}`).rotate([0, 0, 1], 90); } // not a key: }\n"
            "    /* nor this: spin: { */\n"
            "  } },\n"
            "  'spin-fast': { duration: 2, update() {} },\n"
            '  "hold": { duration: 1, update() {} }\n'
            "};\n"
        )
        self.assertEqual(["demo", "spin-fast", "hold"], declared_clip_ids(text))

    def test_helpers_declared_before_the_clips_are_not_mistaken_for_clips(self) -> None:
        text = """
        const TARGETS = { arm: "o1.2", lid: "o1.3" };
        function swing(m, t) { m.get(TARGETS.arm).rotate([0, 1, 0], 30 * t); }
        export const clips = { swingLoop: { duration: 4, update(t, m) { swing(m, t); } } };
        """
        self.assertEqual(["swingLoop"], declared_clip_ids(text))

    def test_an_empty_literal_declares_no_clips(self) -> None:
        self.assertEqual([], declared_clip_ids("export const clips = {};"))

    def test_anything_but_the_literal_form_defers_to_the_runtime(self) -> None:
        for text in (
            "",
            "export default { demo: { update() {} } };",
            "export const clips = build();",
            "export const clips = { ...base, extra: { update() {} } };",
            "export const clips = { [computed]: { update() {} } };",
            "export const clips = { demo: { update() {} }",  # unterminated
        ):
            with self.subTest(text=text):
                self.assertIsNone(declared_clip_ids(text))


class ExportsCheckTests(unittest.TestCase):
    def test_refuses_what_the_renderer_refuses_in_its_words(self) -> None:
        self.assertEqual(tuple(PARITY["exports"]), ANIMATION_MODULE_EXPORTS)
        for case in PARITY["cases"]:
            with self.subTest(why=case["why"]):
                if case["error"] is None:
                    check_animation_exports(case["source"], name=PARITY["name"])
                    continue
                with self.assertRaises(ValueError) as refused:
                    check_animation_exports(case["source"], name=PARITY["name"])
                self.assertEqual(case["error"], str(refused.exception))

    def test_what_only_an_engine_can_read_is_left_to_the_renderer(self) -> None:
        for source in (
            "const o = { clips: {}, helper: 1 };\nexport const { clips, helper } = o;",  # destructured
            'export * from "./other.js";',  # another module's names
            'import other from "./other.js";\nexport const helper = other;',  # refused at import
            "export const clips = {",  # a syntax error
            "export const clips = {};\nexport const clips = 1;",  # a duplicate
        ):
            with self.subTest(source=source):
                self.assertIsNone(module_exports(source))
                check_animation_exports(source, name="arm.py::arm animation")


MODEL = """
from cadgen import build123d as bd
from cadgen import label_shape, step


{decorator}
def arm():
    return label_shape(bd.Box(2, 3, 4), "arm")


if __name__ == "__main__":
    arm()
"""
CLIPS = "export const clips = { swing: { duration: 2, update(t, m) {} } };"
WITH_HELPER = CLIPS + "\nexport function ease(t) { return t; }"


class ExportsAtBuildTests(unittest.TestCase):
    def test_the_build_refuses_a_module_the_renderer_would_and_writes_nothing(self) -> None:
        from cadgen._internal.annotation_refresh import refresh_annotations
        from cadgen._internal.generation import _selected_specs_for_targets
        from cadgen._internal.source_sidecar import read_source_sidecar, source_sidecar_path
        from cadgen.catalog import StepImportOptions
        from cadgen.generation import generate_step_targets
        from cadgen.render import relative_to_cwd

        roots = IsolatedCadRoots(self, prefix="animation-exports-")
        temp = roots.temporary_cad_directory(prefix="animation-exports-")
        self.addCleanup(temp.cleanup)
        script = Path(temp.name) / "arm.py"
        document, sidecar = script.with_suffix(".step"), source_sidecar_path(script.with_suffix(".step"))

        def build(decorator: str) -> int:
            script.write_text(MODEL.format(decorator=decorator), encoding="utf-8")
            return generate_step_targets([str(script)], step_options=StepImportOptions(), verbose=False)

        # A module exporting only its clips builds, and the sidecar carries it.
        self.assertEqual(0, build(f"@step(animation={CLIPS!r})"))
        self.assertEqual(CLIPS, read_source_sidecar(document)["animation"]["source"])
        saved = (document.read_bytes(), sidecar.read_bytes())
        _, (spec,) = _selected_specs_for_targets([str(script)])

        # One helper exported beside them: refused in the renderer's words, naming the
        # model, by the import that declares it -- and by the annotation refresh, which
        # reads the literal from the script itself -- and nothing is written.
        refusal = f"{relative_to_cwd(script)}::arm animation: unknown export ease — the renderer understands: clips"
        with self.assertRaises(ValueError) as refused:
            build(f"@step(animation={WITH_HELPER!r})")
        self.assertEqual(refusal, str(refused.exception))
        with self.assertRaises(ValueError) as refreshed:
            refresh_annotations(spec)
        self.assertEqual(refusal, str(refreshed.exception))
        self.assertEqual(saved, (document.read_bytes(), sidecar.read_bytes()))

        # A model with no animation is untouched by the check.
        self.assertEqual(0, build("@step"))
        self.assertEqual(saved[0], document.read_bytes())
        self.assertFalse(sidecar.exists())


if __name__ == "__main__":
    unittest.main()
