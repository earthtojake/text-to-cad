#!/usr/bin/env python3

"""One shape's STEP in memory (``cad.engine.export.step.shape_bytes``): the same bytes for the same shape,
whatever the process wrote before; the part where it stands, in millimetres; its faces in the order the kernel
numbers them, read back by the kernel itself; nothing printed and no file written."""

from __future__ import annotations

import io
import os
import tempfile
import unittest
from typing import Any

import build123d as bd

from cad.build123d import _dfm_brep as brep
from cad.engine.export.step import WRITTEN_STAMP, shape_bytes


def bracket() -> Any:
    """A plate with a through hole, a blind hole and a rounded corner, turned and moved from the origin."""
    plate = bd.Box(60, 40, 10) - bd.Pos(-15, 5, 0) * bd.Cylinder(4, 10) - bd.Pos(15, 5, 2) * bd.Cylinder(3, 6)
    plate = bd.fillet(plate.edges().filter_by(bd.Axis.Z).sort_by(bd.Axis.X)[-1:], 5)
    return bd.Pos(100, -50, 20) * bd.Rot(0, 90, 30) * plate


def read_back(data: bytes) -> Any:
    from OCP.IFSelect import IFSelect_RetDone
    from OCP.STEPControl import STEPControl_Reader

    reader = STEPControl_Reader()
    if reader.ReadStream("part", io.BytesIO(data)) != IFSelect_RetDone:
        raise AssertionError("the kernel does not read the bytes back")
    reader.TransferRoots()
    return bd.Shape.cast(reader.OneShape())


def surfaces(shape: Any) -> list[tuple[Any, ...]]:
    """Each face's surface as the kernel reads it, in its ordinal's order, rounded to a nanometre."""
    def rounded(values: Any) -> Any:
        return None if values is None else tuple(round(float(value), 6) + 0.0 for value in values)

    found = []
    for face in brep.Part(name="part", owner="part", shape=shape).faces():
        surface = brep.surface(face)
        found.append((surface.kind, rounded(surface.normal), rounded(surface.origin), rounded(surface.axis),
                      None if surface.radius is None else round(surface.radius, 6), round(face.area, 6)))
    return found


class ShapeBytesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.shape = bracket()
        cls.data = shape_bytes(cls.shape)

    def test_the_same_shape_is_the_same_bytes_whatever_was_written_before(self) -> None:
        shape_bytes(bd.Box(1, 2, 3))
        self.assertEqual(shape_bytes(self.shape), self.data)
        self.assertEqual(shape_bytes(self.shape.wrapped), self.data, "a kernel shape or build123d's")
        self.assertIn(f"'{WRITTEN_STAMP}'".encode(), self.data[:1024])
        self.assertIn(b"PRODUCT('1','1'", self.data)

    def test_the_bytes_do_not_depend_on_how_the_process_wrote_a_step_before_and_its_settings_are_left(self) -> None:
        """The kernel keeps its writer's parameters for the process, and build123d's own export changes two of
        them (curves on surfaces, the precision mode): one shape's bytes are the same after it, and after every
        other parameter they depend on was changed, and each is left as it was found."""
        from OCP.Interface import Interface_Static

        with tempfile.TemporaryDirectory(prefix="step-shape-bytes-") as folder:
            bd.export_step(bd.Box(1, 2, 3), os.path.join(folder, "box.step"), write_pcurves=False,
                           precision_mode=bd.PrecisionMode.GREATEST)
        self.assertEqual((Interface_Static.IVal_s("write.surfacecurve.mode"),
                          Interface_Static.IVal_s("write.precision.mode")), (0, 1), "build123d's export changed them")
        self.assertEqual(shape_bytes(self.shape), self.data)
        whole = {"write.precision.mode": -1, "write.step.assembly": 1, "write.surfacecurve.mode": 0,
                 "write.step.vertex.mode": 1, "write.step.nonmanifold": 1, "write.step.tessellated": 0}
        words = {"write.step.unit": "INCH", "write.step.schema": "AP203", "write.step.product.name": "another's"}
        was = {name: Interface_Static.IVal_s(name) for name in whole} | {
            name: Interface_Static.CVal_s(name) for name in words} | {
            "write.precision.val": Interface_Static.RVal_s("write.precision.val")}
        try:
            for name, value in whole.items():
                Interface_Static.SetIVal_s(name, value)
            for name, value in words.items():
                Interface_Static.SetCVal_s(name, value)
            Interface_Static.SetRVal_s("write.precision.val", 0.5)
            self.assertEqual(shape_bytes(self.shape), self.data)
            self.assertEqual({name: Interface_Static.IVal_s(name) for name in whole}, whole, "left as found")
            self.assertEqual({name: Interface_Static.CVal_s(name) for name in words}, words)
            self.assertEqual(Interface_Static.RVal_s("write.precision.val"), 0.5)
        finally:
            for name in whole:
                Interface_Static.SetIVal_s(name, was[name])
            for name in words:
                Interface_Static.SetCVal_s(name, was[name])
            Interface_Static.SetRVal_s("write.precision.val", was["write.precision.val"])

    def test_the_kernel_reads_back_the_faces_in_their_order_where_the_part_stands(self) -> None:
        written, read = surfaces(self.shape), surfaces(read_back(self.data))
        self.assertEqual(len(read), len(written))
        self.assertEqual(read, written)
        self.assertEqual({kind for kind, *_rest in written}, {"plane", "cylinder"})
        # Where it stands, in millimetres: the same material about the same point, far from the origin.
        back = read_back(self.data)
        self.assertAlmostEqual(back.volume, self.shape.volume, places=6)
        self.assertGreater(self.shape.center().length, 100.0)
        self.assertAlmostEqual((back.center() - self.shape.center()).length, 0.0, places=6)

    def test_nothing_is_printed_and_no_file_is_written(self) -> None:
        with tempfile.TemporaryDirectory(prefix="step-shape-bytes-") as folder:
            said = os.path.join(folder, "stdout")
            kept, here = os.dup(1), os.getcwd()
            target = os.open(said, os.O_WRONLY | os.O_CREAT)
            work = os.path.join(folder, "work")
            os.mkdir(work)
            try:
                os.dup2(target, 1)
                os.chdir(work)
                shape_bytes(self.shape)
            finally:
                os.chdir(here)
                os.dup2(kept, 1)
                os.close(kept)
                os.close(target)
            self.assertEqual(os.path.getsize(said), 0, "the kernel's writer says nothing on a worker's protocol")
            self.assertEqual(os.listdir(work), [])


if __name__ == "__main__":
    unittest.main()
