"""Static pins on the cad-viewer skill: it is instructions over `cadgen viewer`.

The skill used to carry the Viewer runtime itself (a built client + a Python
server under `scripts/viewer`). It ships nothing now: `requirements.txt` names
cadgen, and the documented command is cadgen's own `viewer` verb. These tests
keep the documented launch line and the base port honest, so the doc cannot
drift away from the launcher it describes, and keep the skill runtime-free.
"""

from __future__ import annotations

import unittest

from tests.python.support.paths import repo_path

VIEWER_SKILL = repo_path("skills", "cad-viewer")


class SkillIsInstructionsOnly(unittest.TestCase):
    def test_the_skill_ships_no_runtime(self):
        # No scripts/ at all: the Viewer is `cadgen viewer`, and a copy of the
        # server or client here would be a second thing to keep current.
        self.assertFalse((VIEWER_SKILL / "scripts").exists(), "skills/cad-viewer must not carry a runtime")

    def test_skill_md_documents_the_start_command_and_default_port(self):
        # The launcher has no directory flag: the cwd IS the served directory,
        # so the documented command cd's into the workspace first.
        skill_md = (VIEWER_SKILL / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("cd /absolute/project/models && cadgen viewer --host 127.0.0.1 --json", skill_md)
        self.assertIn("cadgen viewer list", skill_md)
        self.assertIn("cadgen viewer stop --port <n>", skill_md)
        self.assertNotIn("--root", skill_md, "the retired directory flag must not be documented")
        self.assertIn("3245", skill_md)

    def test_skill_md_no_longer_names_a_bundled_entrypoint(self):
        # Every earlier spelling of the launch -- `npm run start`, `main.mjs`,
        # `scripts/viewer/server/main.py` -- named a file inside the skill. None
        # exists; this keeps them out of the doc.
        skill_md = (VIEWER_SKILL / "SKILL.md").read_text(encoding="utf-8")
        for retired in ("npm --prefix scripts/viewer run start", "main.mjs", "scripts/viewer/server/main.py"):
            self.assertNotIn(retired, skill_md, retired)

    def test_requirements_name_cadgen_pinned_to_version_and_nothing_else(self):
        # Pinned to VERSION like every skill (the release PR stamps it). No
        # extras: the Viewer never renders headlessly.
        version = repo_path("VERSION").read_text(encoding="utf-8").strip()
        requirements = (VIEWER_SKILL / "requirements.txt").read_text(encoding="utf-8")
        lines = [line for line in requirements.splitlines() if line.strip() and not line.startswith("#")]
        self.assertEqual(lines, [f"cadgen=={version}"])


if __name__ == "__main__":
    unittest.main()
