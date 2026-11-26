"""``scripts/generated/regenerate.py``: one command makes every file generated from the code again, and ``--check``
names the stale ones and writes nothing. Every tracked ``*.generated.*`` file is one it makes; what each holds is
held to its source by that file's own test (``test_cli_reference.py``, ``test_library_reference.py``,
``test_registry.py``, ``test_look.py``)."""

from __future__ import annotations

import contextlib
import importlib.util
import io
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = REPO_ROOT / "scripts" / "generated" / "regenerate.py"


def _script():
    spec = importlib.util.spec_from_file_location("regenerate", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Regenerate(unittest.TestCase):
    def test_every_generated_file_is_one_the_command_makes(self) -> None:
        tracked = subprocess.run(["git", "ls-files", "*.generated.*"], cwd=REPO_ROOT, capture_output=True,
                                 text=True, check=True).stdout.split()
        self.assertEqual(sorted(tracked), sorted(path for path, _module, _function in _script().GENERATED))

    def test_check_names_a_stale_file_and_writes_nothing_and_a_run_makes_it_its_sources_again(self) -> None:
        regenerate = _script()
        registry = regenerate.GENERATED[2][0]
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for relative, _module, _function in regenerate.GENERATED:
                (root / relative).parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(REPO_ROOT / relative, root / relative)
            (root / registry).write_text("{}\n", encoding="utf-8")
            said = io.StringIO()
            with mock.patch.object(regenerate, "REPO_ROOT", root), contextlib.redirect_stdout(said):
                checked = regenerate.main(["--check"])
                unchanged = (root / registry).read_text(encoding="utf-8")
                made = regenerate.main([])
                again = regenerate.main(["--check"])
            self.assertEqual((checked, unchanged, made, again), (1, "{}\n", 0, 0), said.getvalue())
            self.assertIn(f"stale: {registry}\n", said.getvalue())
            self.assertIn(f"regenerated {registry}\n", said.getvalue())
            self.assertEqual((root / registry).read_bytes(), regenerate.made("cad.registry", "as_docs_json"))


if __name__ == "__main__":
    unittest.main()
