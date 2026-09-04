"""The ``out=`` path in a decorator is repository-facing and its separator rule is absolute.

A model's outputs are what its decorators declare; there is no per-run output
override, so the only path rule left is the one for ``out=`` in a checked-in
``@step``/``@dxf`` decorator. That file is read on every platform, so POSIX
separators are the portable form and a backslash is refused everywhere -- on
Windows too, where it is the native separator.
"""

from __future__ import annotations

import ast
import unittest
from pathlib import Path

from tests.python.support.paths import add_repo_path

add_repo_path("packages/cadgen/src")


class DecoratorPathRuleStaysAbsoluteTest(unittest.TestCase):
    """The repository-facing rule is NOT platform-conditional, on any platform."""

    def test_a_decorator_out_path_with_a_backslash_is_rejected_everywhere(self):
        from cadgen.metadata import _decorator_string_kwarg

        kwargs = {"out": ast.Constant(value=r"models\widget.step")}
        with self.assertRaisesRegex(ValueError, "POSIX"):
            _decorator_string_kwarg(kwargs, "out", script_path=Path("widget.py"))


if __name__ == "__main__":
    unittest.main()
