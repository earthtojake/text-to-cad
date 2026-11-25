"""``cad run kicad-cli ...``: KiCad's own command line, kicode's, with no ``--with``.

The real ``cad run``, on this file's own engine, state and cache (the runner's): the bare command makes the
environment of ``cad[kicad]`` (from uv's cache after the KiCad job's first), runs kicode's kicad-cli there,
prints the pinned KiCad's version and passes its exit code through, in private homes: the KiCad homes the
caller's environment names are left as they were.
"""

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests.python.support import engine_daemon, kicode

HOMES = ("KICAD_CONFIG_HOME", "KICAD_DOCUMENTS_HOME", "KICAD_CACHE_HOME")


class RunKicadCli(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder = Path(tempfile.mkdtemp(prefix="kicad-run-")).resolve()
        cls.addClassCleanup(shutil.rmtree, cls.folder, True)
        # The person's own KiCad homes, as their environment names them: kicad-cli must write none of them.
        cls.person = {name: cls.folder / "person" / name.lower() for name in HOMES}
        for folder in cls.person.values():
            folder.mkdir(parents=True)
        cls.env = engine_daemon.watched({**os.environ, **{name: str(path) for name, path in cls.person.items()}},
                                        cls.addClassCleanup)

    def run_(self, *args):
        return engine_daemon.run([sys.executable, "-m", "cad_server.cli", "run", *args], env=self.env, cwd=self.folder)

    def test_kicad_cli_runs_kicode_s_pinned_kicad_headless_in_private_homes(self):
        pinned = kicode.run_python(self, "import kicode; print(kicode.KICAD_VERSION)")
        self.assertEqual(0, pinned.returncode, pinned.stderr)
        done = self.run_("kicad-cli", "version")
        self.assertEqual((done.returncode, done.stdout.strip()), (0, pinned.stdout.strip()), done.stderr)
        self.assertEqual({name: sorted(path.iterdir()) for name, path in self.person.items()},
                         {name: [] for name in HOMES}, "the person's KiCad homes are untouched")

        # KiCad's own exit code, as kicode's kicad-cli gives it run directly.
        missing = str(self.folder / "missing.kicad_pcb")
        done = self.run_("kicad-cli", "pcb", "drc", missing)
        direct = subprocess.run([str(kicode.kicad_cli(self)), "pcb", "drc", missing], capture_output=True, text=True,
                                env=kicode.environment(self, self.folder / "direct"), check=False)
        self.assertNotEqual(0, direct.returncode)
        self.assertEqual(done.returncode, direct.returncode, done.stderr)


if __name__ == "__main__":
    unittest.main()
