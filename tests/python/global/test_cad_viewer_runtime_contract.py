from __future__ import annotations

import json
import unittest

from tests.python.support.paths import REPO_ROOT


RUNTIME_DIR = REPO_ROOT / "skills" / "cad-viewer" / "scripts" / "viewer"


class CadViewerRuntimeContractTests(unittest.TestCase):
    def test_materialized_runtime_includes_agent_launcher(self) -> None:
        if RUNTIME_DIR.is_symlink():
            self.skipTest("develop uses the source Viewer symlink; production runtime is checked after bundling")

        package = json.loads((RUNTIME_DIR / "package.json").read_text(encoding="utf-8"))

        self.assertEqual(package["scripts"].get("agent:start"), "node scripts/start-agent-viewer.mjs")
        self.assertTrue((RUNTIME_DIR / "scripts" / "start-agent-viewer.mjs").is_file())
        self.assertTrue((RUNTIME_DIR / "backend" / "server.mjs").is_file())


if __name__ == "__main__":
    unittest.main()
