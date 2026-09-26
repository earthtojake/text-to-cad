"""The derivation rules of ``cli_from_function``.

A generated CLI is only worth trusting if the derivation is a KNOWN, narrow
subset — a helper that quietly accepted richer annotations would grow into an
argument-parsing framework and stop being obviously correct. So the rejections
matter as much as the acceptances: anything outside the subset must fail loudly
at parser-build time, pushing the command to adapter status instead.
"""

from __future__ import annotations

import contextlib
import functools
import io
import json
import unittest
from dataclasses import dataclass
from pathlib import Path

from cadgen._internal.cli_from_function import (
    NotDerivable,
    RetiredOption,
    cli_from_function,
    parse_docstring,
    parser_dests,
    result_payload,
    retired_options,
    run_cli,
)


@dataclass(frozen=True)
class Result:
    ok: bool
    path: Path | None = None
    items: tuple[Path, ...] = ()

    def human_lines(self) -> list[str]:
        return [f"wrote {self.path}"]


def verb(
    target: Path,
    out: Path | None = None,
    *,
    mesh_tolerance: float | None = None,
    force: bool = False,
    label: str = "x",
) -> Result:
    """Do the thing to TARGET.

    target: what to operate on.
    out: where the output goes,
        wrapped onto a second line.
    force: ignore the ledger.
    """
    return Result(ok=True, path=out or target)


class Derivation(unittest.TestCase):
    def test_positionals_and_flags_come_from_the_signature(self):
        parser = cli_from_function(verb, prog="t")
        self.assertEqual(
            ("target", "out", "mesh_tolerance", "force", "label", "json_output"),
            parser_dests(parser),
        )

    def test_a_defaulted_positional_is_optional(self):
        parser = cli_from_function(verb, prog="t")
        self.assertEqual(Path("a.py"), parser.parse_args(["a.py"]).target)
        self.assertIsNone(parser.parse_args(["a.py"]).out)
        self.assertEqual(Path("b.stl"), parser.parse_args(["a.py", "b.stl"]).out)

    def test_a_required_positional_stays_required(self):
        parser = cli_from_function(verb, prog="t")
        with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
            parser.parse_args([])

    def test_bool_keywords_become_store_true(self):
        parser = cli_from_function(verb, prog="t")
        self.assertFalse(parser.parse_args(["a.py"]).force)
        self.assertTrue(parser.parse_args(["a.py", "--force"]).force)

    def test_underscores_become_kebab_case(self):
        parser = cli_from_function(verb, prog="t")
        self.assertEqual(0.25, parser.parse_args(["a.py", "--mesh-tolerance", "0.25"]).mesh_tolerance)

    def test_abbreviated_flags_are_rejected_instead_of_silently_dropped(self):
        parser = cli_from_function(verb, prog="t")
        with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
            parser.parse_args(["a.py", "--mesh-tol", "0.25"])

    def test_docstring_supplies_description_and_per_argument_help(self):
        summary, helps = parse_docstring(verb.__doc__)
        self.assertEqual("Do the thing to TARGET.", summary)
        self.assertEqual("what to operate on.", helps["target"])
        # Continuation lines fold into the argument they belong to.
        self.assertEqual("where the output goes, wrapped onto a second line.", helps["out"])
        self.assertIn("Do the thing to TARGET.", cli_from_function(verb, prog="t").format_help())


class Metavars(unittest.TestCase):
    """A flag's metavar is its parameter's last word -- until two flags of one
    command would share it; then each takes leading words until they differ."""

    def test_the_last_word_names_the_value(self):
        def one(target: Path, *, size_profile: str | None = None, focus: tuple[str, ...] = ()) -> Result:
            """Summary."""

        actions = {a.dest: a.metavar for a in cli_from_function(one, prog="t")._actions}
        self.assertEqual("PROFILE", actions["size_profile"])
        self.assertEqual("FOCUS", actions["focus"])

    def test_two_flags_never_share_a_metavar(self):
        def two(
            target: Path, *, mesh_tolerance: float | None = None,
            mesh_angular_tolerance: float | None = None, deform_tolerance: float | None = None,
        ) -> Result:
            """Summary."""

        actions = {a.dest: a.metavar for a in cli_from_function(two, prog="t")._actions}
        self.assertEqual("MESH_TOLERANCE", actions["mesh_tolerance"])
        self.assertEqual("ANGULAR_TOLERANCE", actions["mesh_angular_tolerance"])
        self.assertEqual("DEFORM_TOLERANCE", actions["deform_tolerance"])

    def test_every_generated_door_has_distinct_metavars(self):
        import collections
        import importlib

        from cadgen import cli

        for command, (module_name, _) in sorted(cli._COMMANDS.items()):
            module = importlib.import_module(module_name)
            if not hasattr(module, "VERB"):
                continue
            with self.subTest(command=command):
                metavars = collections.Counter(
                    a.metavar for a in module.build_parser()._actions if a.option_strings and a.metavar
                )
                self.assertEqual({}, {name: n for name, n in metavars.items() if n > 1})


class OutsideTheSubset(unittest.TestCase):
    """Each of these must be an ADAPTER, and the helper has to say so."""

    def test_a_richer_annotation_is_rejected(self):
        def bad(target: "list[str]") -> Result: ...

        with self.assertRaises(NotDerivable):
            cli_from_function(bad, prog="t")

    def test_a_three_way_union_is_rejected(self):
        def bad(target: "Path | str | None" = None) -> Result: ...

        with self.assertRaises(NotDerivable):
            cli_from_function(bad, prog="t")

    def test_an_unannotated_parameter_is_rejected(self):
        def bad(target) -> Result: ...  # noqa: ANN001

        with self.assertRaises(NotDerivable):
            cli_from_function(bad, prog="t")

    def test_variadics_are_rejected(self):
        def bad(*args: str) -> Result: ...

        with self.assertRaises(NotDerivable):
            cli_from_function(bad, prog="t")

    def test_a_bool_flag_defaulting_to_true_is_rejected(self):
        # A store_true flag can only turn something ON; deriving one from a
        # True default would silently produce a flag that does nothing.
        def bad(target: Path, *, force: bool = True) -> Result: ...

        with self.assertRaises(NotDerivable):
            cli_from_function(bad, prog="t")

    def test_a_positional_bool_is_rejected(self):
        def bad(force: bool) -> Result: ...

        with self.assertRaises(NotDerivable):
            cli_from_function(bad, prog="t")


class RetiredFlags(unittest.TestCase):
    """A flag the verb USED to take: gone from the signature, still answered.

    A deleted parameter leaves nothing to derive from, so without this the
    hard cutover reaches the caller as argparse's ``unrecognized arguments``,
    which names neither the reason nor the replacement. These assert the
    MESSAGE, not just that something failed.
    """

    TEACHING = "gizmos posed a 3D scene; this door draws a flat picture. Pass --appearance instead."

    def door(self):
        def snapshot(target: Path, *, appearance: str = "light") -> Result:
            """Summary."""
            return Result(ok=True, path=target)

        snapshot.__cadgen_retired_options__ = {"--gizmo": self.TEACHING}
        return snapshot

    def test_the_declaration_is_read_off_the_verb(self):
        self.assertEqual({"--gizmo": self.TEACHING}, retired_options(self.door()))
        self.assertEqual({}, retired_options(verb))

    def test_help_does_not_advertise_a_retired_flag(self):
        help_text = cli_from_function(self.door(), prog="t").format_help()
        self.assertNotIn("--gizmo", help_text)
        self.assertIn("--appearance", help_text)

    def test_a_retired_flag_is_not_part_of_the_signature_surface(self):
        # The signature-sync policy test compares these against the verb's
        # parameters; a retirement that leaked in would read as a flag the
        # function cannot express.
        parser = cli_from_function(self.door(), prog="t")
        self.assertEqual(("target", "appearance", "json_output"), parser_dests(parser))

    def test_every_spelling_the_flag_ever_had_is_refused_with_the_teaching(self):
        parser = cli_from_function(self.door(), prog="cadgen thing snapshot")
        for argv in (
            ["a.dxf", "--gizmo", "iso"],   # a flag that took a value
            ["a.dxf", "--gizmo=iso"],      # ...spelled with an equals sign
            ["a.dxf", "--gizmo"],          # a flag that took none
            ["--gizmo", "a.dxf"],          # before the positional
        ):
            with self.subTest(argv=argv):
                with self.assertRaises(RetiredOption) as raised:
                    parser.parse_args(argv)
                message = str(raised.exception)
                self.assertIn("cadgen thing snapshot no longer takes --gizmo", message)
                self.assertIn(self.TEACHING, message)

    def test_the_refusal_is_the_message_alone_and_a_failing_exit(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            code = run_cli(self.door(), ["a.dxf", "--gizmo", "iso"], prog="t", stdout=io.StringIO())
        self.assertEqual(2, code)
        printed = err.getvalue()
        self.assertIn(self.TEACHING, printed)
        # The two things the caller was getting instead of an explanation.
        self.assertNotIn("unrecognized arguments", printed)
        self.assertNotIn("usage:", printed)

    def test_a_live_flag_still_parses_beside_a_retired_one(self):
        parser = cli_from_function(self.door(), prog="t")
        self.assertEqual("dark", parser.parse_args(["a.dxf", "--appearance", "dark"]).appearance)

    def test_a_retirement_the_signature_still_declares_is_rejected(self):
        # Both would mean the flag works AND teaches that it does not.
        def confused(target: Path, *, appearance: str = "light") -> Result:
            """Summary."""

        confused.__cadgen_retired_options__ = {"--appearance": "gone"}
        with self.assertRaisesRegex(NotDerivable, r"--appearance is declared retired"):
            cli_from_function(confused, prog="t")

    def test_a_retirement_must_name_a_long_flag(self):
        def confused(target: Path) -> Result:
            """Summary."""

        confused.__cadgen_retired_options__ = {"gizmo": "gone"}
        with self.assertRaisesRegex(NotDerivable, r"must be a --long spelling"):
            cli_from_function(confused, prog="t")


class Serialization(unittest.TestCase):
    def test_generated_invocation_preserves_explicit_default_valued_keywords(self):
        calls = []

        def declared(target: Path, *, mode: str = "view", force: bool = False) -> Result:
            return Result(ok=True, path=target)

        @functools.wraps(declared)
        def recording(*args, **kwargs):
            calls.append(dict(kwargs))
            return declared(*args, **kwargs)

        self.assertEqual(0, run_cli(recording, ["a.py"], prog="t", stdout=io.StringIO()))
        self.assertEqual({}, calls.pop())
        self.assertEqual(
            0,
            run_cli(
                recording,
                ["a.py", "--mode", "view", "--force"],
                prog="t",
                stdout=io.StringIO(),
            ),
        )
        self.assertEqual({"mode": "view", "force": True}, calls.pop())

    def test_json_carries_the_dataclass_with_paths_as_strings(self):
        # A Path serializes as str(Path) -- the NATIVE spelling, backslashes and
        # all on Windows -- so the expectation is built the same way rather than
        # hardcoding the POSIX separator.
        payload = result_payload(Result(ok=True, path=Path("/a/b.stl"), items=(Path("/c.glb"),)))
        self.assertEqual(
            {"ok": True, "path": str(Path("/a/b.stl")), "items": [str(Path("/c.glb"))]},
            payload,
        )

    def test_run_cli_prints_one_json_line(self):
        out = io.StringIO()
        self.assertEqual(0, run_cli(verb, ["a.py", "--json"], prog="t", stdout=out))
        self.assertEqual({"ok": True, "path": "a.py", "items": []}, json.loads(out.getvalue()))

    def test_run_cli_prints_human_lines_without_json(self):
        out = io.StringIO()
        self.assertEqual(0, run_cli(verb, ["a.py"], prog="t", stdout=out))
        self.assertEqual("wrote a.py\n", out.getvalue())

    def test_an_exception_becomes_the_error_envelope_under_json(self):
        def boom(target: Path) -> Result:
            raise RuntimeError("nope")

        out = io.StringIO()
        self.assertEqual(1, run_cli(boom, ["a.py", "--json"], prog="t", stdout=out))
        self.assertEqual({"ok": False, "error": "nope"}, json.loads(out.getvalue()))

    def test_an_exception_reports_cleanly_without_json(self):
        def boom(target: Path) -> Result:
            raise RuntimeError("nope")

        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            self.assertEqual(1, run_cli(boom, ["a.py"], prog="t"))
        self.assertIn("nope", err.getvalue())
        self.assertNotIn("Traceback", err.getvalue())

    def test_a_not_ok_result_exits_one(self):
        def failing(target: Path) -> Result:
            return Result(ok=False)

        out = io.StringIO()
        self.assertEqual(1, run_cli(failing, ["a.py", "--json"], prog="t", stdout=out))


if __name__ == "__main__":
    unittest.main()
