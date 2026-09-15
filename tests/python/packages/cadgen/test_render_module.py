"""Embedded animation source and literal clip-name preflight."""

from __future__ import annotations

import unittest

from tests.python.support.paths import add_repo_path

add_repo_path("packages/cadgen/src")

from cadgen._internal.render_module import (  # noqa: E402
    declared_clip_ids,
    read_animation_source,
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


if __name__ == "__main__":
    unittest.main()
