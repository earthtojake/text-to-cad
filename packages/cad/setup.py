"""cad builds from pyproject.toml; this adds two files to the wheel's root.

``cad.pth`` is what cad does as an interpreter starts, in the environment it is installed into: ``import
build123d`` is made lazy (``cad/_internal/lazy_kernel.py``). The interpreter runs a ``.pth``
file's import line at start only from a site-packages directory, so the file must sit at the wheel's
root, which an installer unpacks into site-packages. setuptools' ``data-files`` cannot put it there -- a wheel's
data scheme installs under the environment's prefix -- so ``build_py`` copies it beside the
packages, as setuptools ships its own ``distutils-precedence.pth``. ``MANIFEST.in`` carries it
into the sdist, which the wheel is built from. An editable install (a checkout's
development environment) gets it too: its wheel holds what is installed at ``install_lib``, the
wheel's root, and nothing of ``build_lib``, so ``build_py`` copies it there as well.

``cad.start`` is the same, for Python 3.15 and later, which run a ``.start`` file's entry points as they start and
ignore the import lines of the ``.pth`` file of the same name (PEP 829; from 3.18 they ignore every ``.pth`` file's
import lines). It goes where ``cad.pth`` goes.
"""

from __future__ import annotations

import os

from setuptools import setup
from setuptools.command.build_py import build_py

PTH = "cad.pth"
START = "cad.start"


class build_py_with_pth(build_py):  # noqa: N801 - setuptools' command naming
    def run(self) -> None:
        super().run()
        for name in (PTH, START):
            source = os.path.join(os.path.dirname(os.path.abspath(__file__)), name)
            self.copy_file(source, os.path.join(self.build_lib, name), preserve_mode=False)
            if getattr(self, "editable_mode", False):
                root = self.get_finalized_command("install").install_lib
                self.copy_file(source, os.path.join(root, name), preserve_mode=False)

    def get_outputs(self, include_bytecode: bool = True) -> list[str]:
        return [*super().get_outputs(include_bytecode), *(os.path.join(self.build_lib, name) for name in (PTH, START))]


setup(cmdclass={"build_py": build_py_with_pth})
