"""What counts as a skill's cadgen pin: the version its SKILL.md's launch command names.

The release stamps `uvx ... --from cadgen==<release> cadgen` into every cadgen skill.
`cadgen doctor` is the check a skill teaches: it compares the running version with the pin
`read_skill_pin` finds (test_doctor.py pins what it does with a mismatch -- exit 3, naming
both versions). What this file pins is the READER, because its silence matters as much as its
answer: a development install's rewritten command, a bare mention of cadgen or another package's
pin must not read as a pin, or `cadgen doctor` would fail a skill with nothing to enforce.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from cadgen import __version__ as INSTALLED
from cadgen.cli import read_skill_pin


class SkillPin(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def _skill(self, body: str) -> Path:
        path = self.root / "SKILL.md"
        path.write_text(body, encoding="utf-8")
        return path

    def test_a_missing_file_pins_nothing(self) -> None:
        self.assertIsNone(read_skill_pin(self.root / "SKILL.md"))

    def test_text_without_a_launch_command_pins_nothing(self) -> None:
        # A development install points the command at a checkout: `.venv/bin/python -m cadgen.cli`.
        self.assertIsNone(read_skill_pin(self._skill("Run `/src/.venv/bin/python -m cadgen.cli`.\nplaywright==1.0.0\n")))

    def test_the_launch_commands_pin_is_read_back(self) -> None:
        body = f"- `cadgen` means `uvx --no-config --managed-python --python 3.13 --from cadgen=={INSTALLED} cadgen`\n"
        self.assertEqual(INSTALLED, read_skill_pin(self._skill(body)))


if __name__ == "__main__":
    unittest.main()
