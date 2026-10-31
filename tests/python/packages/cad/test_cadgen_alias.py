"""``cadgen``, the library's earlier import name, is the library itself (``src/cadgen/__init__.py``).

Every top-level name of ``cadgen`` is ``cad``'s own, and every module ``cadgen.<x>`` is the module object
``cad.<x>``: imported once, under its own name, and handed out as it is -- never a second copy whose
classes and memo would be strangers to the first. Nothing is said when it is used. There is no
``text_to_cad`` import name: the distribution ``text-to-cad`` is named so, and installs ``cad``.

Run in a fresh interpreter each: this one has imported ``cad`` already, and the alias must hold whichever
name a process imports first.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
import unittest

from tests.python.support.paths import SOURCE_PATH


def run(code: str) -> dict:
    done = subprocess.run([sys.executable, "-W", "error", "-c", textwrap.dedent(code)], capture_output=True, text=True,
                          env={**os.environ, "PYTHONPATH": SOURCE_PATH}, timeout=120)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout.strip().splitlines()[-1])


class AliasTest(unittest.TestCase):
    def test_every_module_of_cadgen_is_the_library_s_own_module(self) -> None:
        found = run("""
            import json, sys
            import cadgen.ap242
            import cad, cad.ap242
            from cadgen.gltf import animation
            from cadgen.engine.model import Model
            import cad.gltf, cad.engine.model
            print(json.dumps({
                "ap242": cadgen.ap242 is cad.ap242,
                "gltf": sys.modules["cadgen.gltf"] is cad.gltf and animation is cad.gltf.animation,
                "model": sys.modules["cadgen.engine.model"] is cad.engine.model and Model is cad.engine.model.Model,
                "named": [cad.ap242.__name__, Model.__module__],
                "copies": sorted({module.__file__ for name, module in sys.modules.items()
                                  if name.startswith("cadgen.") and getattr(module, "__file__", None)}
                                 - {module.__file__ for name, module in sys.modules.items()
                                    if name.startswith("cad.") and getattr(module, "__file__", None)}),
            }))
        """)
        self.assertEqual(found, {"ap242": True, "gltf": True, "model": True, "named": ["cad.ap242", "cad.engine.model"],
                                 "copies": []})

    def test_every_top_level_name_is_the_library_s(self) -> None:
        found = run("""
            import json
            import cadgen
            import cad
            print(json.dumps({
                "same": all(getattr(cadgen, name) is getattr(cad, name) for name in cad.__all__),
                "dir": dir(cadgen) == dir(cad),
                "version": cadgen.__version__ == cad.__version__,
            }))
        """)
        self.assertEqual(found, {"same": True, "dir": True, "version": True})

    def test_a_model_written_against_cadgen_builds_names_as_cad(self) -> None:
        found = run("""
            import json
            from cadgen import model, step
            import cad
            print(json.dumps({"model": model is cad.model, "step": step is cad.step}))
        """)
        self.assertEqual(found, {"model": True, "step": True})

    def test_a_module_neither_name_has_is_not_found_under_the_name_asked(self) -> None:
        found = run("""
            import importlib, importlib.util, json
            try:
                import cadgen.no_such_module_here
            except ModuleNotFoundError as error:
                missing = error.name
            print(json.dumps({"missing": missing, "text_to_cad": importlib.util.find_spec("text_to_cad") is None}))
        """)
        self.assertEqual(found, {"missing": "cadgen.no_such_module_here", "text_to_cad": True})


if __name__ == "__main__":
    unittest.main()
