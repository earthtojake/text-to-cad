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
    cli_from_function,
    parse_docstring,
    parser_dests,
    result_payload,
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
