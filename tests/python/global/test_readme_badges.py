"""Keep the install page's Python requirement in sync with the package Python floor."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]


class ReadmeRequirementsTests(unittest.TestCase):
    def test_documented_python_floor_matches_the_library_s_requirements(self) -> None:
        pyproject = (REPO_ROOT / "packages" / "cad" / "pyproject.toml").read_text(encoding="utf-8")
        page = (REPO_ROOT / "docs" / "install.md").read_text(encoding="utf-8")
        python = re.search(r'requires-python = ">=(\d+\.\d+)"', pyproject)[1]
        self.assertIn(f"The runtime supports Python {python}+", page)


if __name__ == "__main__":
    unittest.main()
