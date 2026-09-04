"""``cadgen doctor`` — the one user-facing pin/version check the skills teach.

The per-verb shims that used to enforce the pin on every invocation are gone;
doctor re-homes that value as an explicit command, so its contract is pinned here:
report the install, resolve a requirements.txt from a file/dir/cwd, exit 0 on
match-or-nothing-to-check, exit 3 (the historical shim code) on a mismatch.
"""

from __future__ import annotations

import io
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory

from tests.python.support.paths import add_repo_path

add_repo_path("packages/cadgen/src")

import cadgen  # noqa: E402
from cadgen.cli import doctor  # noqa: E402


def _run(argv: list[str]) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = doctor.main(argv)
    return code, out.getvalue(), err.getvalue()


class DoctorTests(unittest.TestCase):


    def test_matching_pin_passes_and_names_the_file(self) -> None:
        with TemporaryDirectory() as tmp:
            req = Path(tmp) / "requirements.txt"
            req.write_text(f"cadgen=={cadgen.__version__}\n", encoding="utf-8")
            code, out, _ = _run([str(req)])
        self.assertEqual(code, 0)
        self.assertIn("OK", out)
        self.assertIn(str(req), out)

    def test_mismatch_exits_3_with_the_install_instruction(self) -> None:
        with TemporaryDirectory() as tmp:
            (Path(tmp) / "requirements.txt").write_text("cadgen==0.0.0.dev0\n", encoding="utf-8")
            code, _, err = _run([tmp])
        self.assertEqual(code, 3)
        self.assertIn("MISMATCH", err)
        self.assertIn("pip install -r requirements.txt", err)


if __name__ == "__main__":
    unittest.main()
