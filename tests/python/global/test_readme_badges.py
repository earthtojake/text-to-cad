"""The README's version badges state what cadgen's pyproject.toml requires.

The badges are static text, so a raised floor or ceiling in pyproject.toml would
leave them claiming the old versions without this check.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]


class ReadmeBadgeTests(unittest.TestCase):
    def test_version_badges_match_cadgen_requirements(self) -> None:
        pyproject = (REPO_ROOT / "packages" / "cadgen" / "pyproject.toml").read_text(encoding="utf-8")
        readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
        python = re.search(r'requires-python = ">=(\d+\.\d+)"', pyproject)[1]
        build123d = re.search(r'"build123d>=(\d+\.\d+)[^"]*"', pyproject)[1]
        occt = re.search(r'"cadquery-ocp-novtk>=(\d+\.\d+)[^"]*"', pyproject)[1]
        self.assertIn(f"badge/Python-{python}+-", readme)
        self.assertIn(f"badge/build123d-{build123d}-", readme)
        self.assertIn(f"badge/Open%20CASCADE-{occt}-", readme)


if __name__ == "__main__":
    unittest.main()
