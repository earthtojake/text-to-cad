"""Shared by this suite: usd-brep's availability, and the exact comparison with build123d.

usd-brep 1.0.0 ships CPython 3.12 wheels for Linux and Windows only, which is where CI runs
this suite (the cadgen jobs install it: setup-deps ``usd-brep``). Without it the suite skips
locally (``pip install usd-brep==1.0.0`` to run it) but fails in CI, so it cannot skip there.
"""

from __future__ import annotations

import os
import sys
import unittest

from tests.python.support.paths import add_repo_path

add_repo_path("packages/usd-brep-build123d/src")

SUPPORTED = sys.version_info[:2] == (3, 12) and sys.platform in ("linux", "win32")
try:
    import usd_brep  # noqa: F401
except ImportError:
    if SUPPORTED and os.environ.get("CI") == "true":
        raise ImportError("CI runs this suite with usd-brep installed (setup-deps usd-brep: true)") from None
    AVAILABLE = False
else:
    AVAILABLE = True

requires_usd_brep = unittest.skipUnless(AVAILABLE, "needs usd-brep (pip install usd-brep==1.0.0; CPython 3.12 on Linux or Windows)")


def occt_volume(shape) -> float:
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps

    props = GProp_GProps()
    BRepGProp.VolumeProperties_s(shape, props, 1e-9)
    return props.Mass()


def symmetric_difference(b3d_shape, ub_shape) -> float:
    """Volume where the two solids differ, relative to build123d's: 0 for the same solid."""
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut
    from usd_brep_build123d.occt import to_occt

    a, b = b3d_shape.wrapped, to_occt(ub_shape)
    differ = occt_volume(BRepAlgoAPI_Cut(a, b).Shape()) + occt_volume(BRepAlgoAPI_Cut(b, a).Shape())
    return differ / occt_volume(a)


class ParityCase(unittest.TestCase):
    """Run one script with build123d and with usd_brep_build123d; the solids must match."""

    TOLERANCE = 1e-9

    @classmethod
    def setUpClass(cls):
        import build123d
        import usd_brep_build123d

        cls.b3d, cls.ub = build123d, usd_brep_build123d

    def assertSameSolid(self, script, tolerance: float | None = None):
        expected, actual = script(self.b3d), script(self.ub)
        self.assertLess(symmetric_difference(expected, actual), self.TOLERANCE if tolerance is None else tolerance)
        return expected, actual
