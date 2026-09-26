"""What counts as a skill's cadgen pin.

`scripts/release/pin-cadgen-requirements.sh` writes `cadgen==<release>` into every
skill's requirements.txt at publish, but nothing makes pip re-resolve that on a machine
where some other cadgen is already installed. `cadgen doctor` is the check a skill
teaches: it compares the installed version with the pin `read_requirements_pin` finds
(test_doctor.py pins what it does with a mismatch -- exit 3, naming both versions).

What this file pins is the READER, because its silence matters as much as its answer:
a bare `cadgen` line, a pinned neighbour or a comment must not read as a pin, or
`cadgen doctor` would fail a checkout that has nothing to enforce.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from cadgen import __version__ as INSTALLED
from cadgen.cli import read_requirements_pin


class RequirementsPin(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def _requirements(self, body: str) -> Path:
        path = self.root / "requirements.txt"
        path.write_text(body, encoding="utf-8")
        return path

    # --- nothing to enforce ---------------------------------------------------------
    def test_a_missing_file_pins_nothing(self) -> None:
        # Not every skill ships a manifest; absent means nothing claims a version.
        self.assertIsNone(read_requirements_pin(self.root / "requirements.txt"))

    def test_a_bare_cadgen_line_pins_nothing(self) -> None:
        self.assertIsNone(read_requirements_pin(self._requirements("cadgen\n")))

    def test_other_distributions_are_ignored(self) -> None:
        # A pinned NEIGHBOUR is not a cadgen pin. Guards against a loose prefix match.
        self.assertIsNone(
            read_requirements_pin(self._requirements("playwright==1.0.0\ncadgen-extras==0.0.1\n"))
        )

    def test_a_comment_is_not_a_pin(self) -> None:
        self.assertIsNone(read_requirements_pin(self._requirements("# cadgen==0.0.0\ncadgen\n")))

    # --- the pin ---------------------------------------------------------------------
    def test_the_exact_pin_is_read_back(self) -> None:
        self.assertEqual(INSTALLED, read_requirements_pin(self._requirements(f"cadgen=={INSTALLED}\n")))

    def test_an_extras_pin_is_a_pin(self) -> None:
        self.assertEqual("0.0.0", read_requirements_pin(self._requirements("cadgen[snapshot]==0.0.0\n")))


if __name__ == "__main__":
    unittest.main()
