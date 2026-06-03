from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests.python.support.paths import add_repo_path

add_repo_path("skills/cad/scripts")

from cadpy_common import assembly_spec, catalog, generation, render
from cadpy import assembly_spec as cad_assembly_spec
from cadpy import catalog as cad_catalog
from cadpy import generation as cad_generation
from cadpy import glb_topology as cad_glb_topology
from cadpy import metadata as cad_metadata
from cadpy import render as cad_render
from cadpy import step_scene as cad_step_scene
from cadpy import step_targets as cad_step_targets
from tests.python.support.tmp_root import CAD_TEST_TMP_ROOT, temporary_directory


IGNORED_TEST_ROOT = CAD_TEST_TMP_ROOT


class IsolatedCadRoots:
    def __init__(self, testcase: unittest.TestCase, *, prefix: str) -> None:
        self._tempdir = temporary_directory(prefix=prefix)
        testcase.addCleanup(self._tempdir.cleanup)

        self.root = Path(self._tempdir.name)
        self.cad_root = self.root / "workspace"
        self.cad_root.mkdir(parents=True, exist_ok=True)

        patches = []
        for module in (
            assembly_spec,
            catalog,
            render,
            generation,
            cad_assembly_spec,
            cad_catalog,
            cad_render,
            cad_generation,
            cad_glb_topology,
            cad_metadata,
            cad_step_scene,
            cad_step_targets,
        ):
            if hasattr(module, "CAD_ROOT"):
                patches.append(mock.patch.object(module, "CAD_ROOT", self.cad_root))
            if hasattr(module, "REPO_ROOT"):
                patches.append(mock.patch.object(module, "REPO_ROOT", self.cad_root))
        for patcher in patches:
            patcher.start()
            testcase.addCleanup(patcher.stop)

    def temporary_cad_directory(self, *, prefix: str) -> tempfile.TemporaryDirectory[str]:
        return tempfile.TemporaryDirectory(prefix=prefix, dir=self.cad_root)
