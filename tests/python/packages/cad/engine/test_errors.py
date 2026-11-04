"""Whose an error is to fix, by its class (``cad.engine.errors``): a ``UserError`` is the person's, any other
``CadError`` is cadgen's, and anything else is left to the caller's fallback."""

from __future__ import annotations

import unittest

from cad.engine import errors


class OwnerTest(unittest.TestCase):
    def test_the_rule_by_class(self) -> None:
        self.assertEqual(errors.owner(errors.UserError("no")), "user")
        self.assertEqual(errors.owner(errors.InternalError("lost")), "ours")
        self.assertEqual(errors.owner(errors.CadError("bare")), "ours")
        for foreign in (KeyError("k"), ValueError("v"), RuntimeError("r"), AssertionError()):
            self.assertIsNone(errors.owner(foreign), foreign)

    def test_cadgen_s_refusals_are_user_errors_and_keep_their_built_in_class(self) -> None:
        from cad.engine.animations import AnimationError
        from cad.engine.build import BuildError
        from cad.engine.document_migrations import DocumentCompatibilityError
        from cad.engine.export import ExportRefused
        from cad.engine.export.dxf import DrawingValidationError, DxfDeterminismError
        from cad.engine.formats import FormatError
        from cad.engine.formats.dxf import DxfError
        from cad.engine.formats.gltf import GltfError
        from cad.engine.formats.robot import RobotError
        from cad.engine.formats.stl import StlError
        from cad.engine.formats.threemf import ThreeMfError
        from cad.engine.mechanism import KinematicsError
        from cad.engine.refs import RefError
        from cad.engine.snapshot import SnapshotRefused
        from cad._internal.programs import ProgramMissing
        from cad.build123d._geometry import GeometryError
        from cad.engine.formats.kicad import PlotError
        from cad.engine.formats.kicad.sexpr import SexprError
        from cad.sdf._source import SdfSourceError
        from cad.urdf._source import UrdfSourceError

        refusals = {AnimationError: ValueError, DocumentCompatibilityError: ValueError, ExportRefused: ValueError,
                    DrawingValidationError: ValueError, FormatError: ValueError, DxfError: ValueError,
                    GltfError: ValueError, RobotError: ValueError, StlError: ValueError, ThreeMfError: ValueError,
                    KinematicsError: ValueError, RefError: ValueError, SnapshotRefused: ValueError,
                    GeometryError: RuntimeError, SdfSourceError: ValueError, UrdfSourceError: ValueError,
                    BuildError: Exception, ProgramMissing: RuntimeError, PlotError: ValueError,
                    SexprError: ValueError}
        for kind, builtin in refusals.items():
            self.assertTrue(issubclass(kind, errors.UserError), kind)
            self.assertTrue(issubclass(kind, builtin), (kind, builtin))  # an ``except`` of the old class still holds
        self.assertTrue(issubclass(DxfDeterminismError, errors.InternalError))
        self.assertTrue(issubclass(DxfDeterminismError, RuntimeError))


if __name__ == "__main__":
    unittest.main()
