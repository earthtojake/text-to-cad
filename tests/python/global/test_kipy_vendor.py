"""The vendored kicad-python tree (``cadgen/kipy``) is whole and self-describing.

``scripts/vendor/kipy.py`` writes it from two pinned commits and checks it with
``--check``, which downloads; this is the part of that contract that needs no
network: the provenance record and licence are there, every self-import was
rewritten to ``cadgen.kipy`` (a leftover ``import kipy`` would import a different,
unrelated package on a machine that has one), the generated modules carry their
stubs, and the client imports without KiCad -- a board script's ``from cadgen
import pcb`` must never need one on the machine that merely imports it.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import unittest

from tests.python.support.paths import repo_path

KIPY = repo_path("packages/cadgen/src/cadgen/kipy")
SELF_IMPORT = re.compile(r"^\s*(?:from|import)\s+kipy\b", re.MULTILINE)
SHA = re.compile(r"^[0-9a-f]{40}$")


class VendoredTree(unittest.TestCase):
    def test_the_record_names_both_commits_and_the_toolchain(self) -> None:
        record = json.loads((KIPY / "VENDOR.json").read_text(encoding="utf-8"))
        for name in ("kicad_python", "kicad"):
            self.assertRegex(record["pins"][name], SHA)
            self.assertRegex(record["dates"][name], r"^\d{4}-\d{2}-\d{2}$")
        self.assertRegex(record["pins"]["kicad_api_version"], r"^\d+\.\d+\.\d+")
        self.assertEqual(set(record["toolchain"]), {"protoc-wheel-0", "mypy-protobuf", "protoletariat", "protobuf"})
        self.assertRegex(record["generated"], r"^\d{4}-\d{2}-\d{2}$")
        self.assertIn("KiCad Developers", (KIPY / "LICENSE").read_text(encoding="utf-8"))
        self.assertTrue((KIPY / "py.typed").is_file())

    def test_every_self_import_was_rewritten(self) -> None:
        offenders = []
        for suffix in ("*.py", "*.pyi"):
            for path in sorted(KIPY.rglob(suffix)):
                if SELF_IMPORT.search(path.read_text(encoding="utf-8")):
                    offenders.append(path.relative_to(KIPY).as_posix())
        self.assertEqual([], offenders, "an import of `kipy` survived the rewrite to `cadgen.kipy`")

    def test_every_generated_module_has_its_stub(self) -> None:
        modules = sorted(KIPY.rglob("*_pb2.py"))
        self.assertGreater(len(modules), 20, "the protobuf modules are missing: run scripts/vendor/kipy.py")
        missing = [path.name for path in modules if not path.with_suffix(".pyi").is_file()]
        self.assertEqual([], missing)

    def test_the_client_imports_without_kicad(self) -> None:
        record = json.loads((KIPY / "VENDOR.json").read_text(encoding="utf-8"))
        code = (
            "import cadgen.kipy, cadgen.kipy.board, cadgen.kipy.board_types, cadgen.kipy.geometry, "
            "cadgen.kipy.server, cadgen.pcb; from cadgen.kipy.kicad_api_version import KICAD_API_VERSION; "
            "print(KICAD_API_VERSION)"
        )
        env = {key: value for key, value in os.environ.items() if key != "CADGEN_KICAD_CLI"}
        env["PATH"] = os.pathsep.join(entry for entry in env.get("PATH", "").split(os.pathsep) if "kicad" not in entry.lower())
        env["PYTHONPATH"] = os.pathsep.join([str(repo_path("packages/cadgen/src")), env.get("PYTHONPATH", "")]).rstrip(os.pathsep)
        completed = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env)
        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertEqual(record["pins"]["kicad_api_version"], completed.stdout.strip())


if __name__ == "__main__":
    unittest.main()
