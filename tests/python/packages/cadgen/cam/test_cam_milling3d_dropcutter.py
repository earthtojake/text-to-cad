"""The drop-cutter against analytic answers: a ball on a plane and on a sphere, a flat on an edge, a bull on a plane, a
vee in a groove; every cutter against a brute-force sample of a bumpy mesh; stock to leave and the gouge check's
inset; marching squares and push."""

from __future__ import annotations

import math
import unittest

import numpy as np

from cadgen._internal.cam.dropcutter import Cutter, DropMesh, contours, cutter_for, drop, push


def grid_mesh(f, x0, x1, y0, y1, n):
    xs, ys = np.linspace(x0, x1, n), np.linspace(y0, y1, n)
    gx, gy = np.meshgrid(xs, ys, indexing="ij")
    v = np.column_stack([gx.ravel(), gy.ravel(), f(gx.ravel(), gy.ravel())])
    idx = np.arange(n * n).reshape(n, n)
    a, b, c, d = idx[:-1, :-1].ravel(), idx[1:, :-1].ravel(), idx[1:, 1:].ravel(), idx[:-1, 1:].ravel()
    return v, np.vstack([np.column_stack([a, b, c]), np.column_stack([a, c, d])])


def sphere_cap(radius, rings=160, segments=320):
    theta = np.linspace(0, math.pi / 2, rings)
    phi = np.linspace(0, 2 * math.pi, segments, endpoint=False)
    t, p = np.meshgrid(theta, phi, indexing="ij")
    v = np.column_stack([(radius * np.sin(t) * np.cos(p)).ravel(), (radius * np.sin(t) * np.sin(p)).ravel(),
                         (radius * np.cos(t)).ravel()])
    idx = np.arange(rings * segments).reshape(rings, segments)
    nxt = np.roll(idx, -1, axis=1)
    tris = np.vstack([np.column_stack([idx[:-1].ravel(), idx[1:].ravel(), nxt[1:].ravel()]),
                      np.column_stack([idx[:-1].ravel(), nxt[1:].ravel(), nxt[:-1].ravel()])])
    return v, tris


def brute(q, vertices, triangles, cutter, k=24):
    """A lower bound: the cutter over a dense sample of each triangle (and its corners)."""
    tri = vertices[triangles]
    u = np.random.default_rng(0).random((k * k, 2))
    flip = u.sum(1) > 1
    u[flip] = 1 - u[flip]
    pts = (tri[:, None, 0] + u[None, :, 0, None] * (tri[:, None, 1] - tri[:, None, 0])
           + u[None, :, 1, None] * (tri[:, None, 2] - tri[:, None, 0])).reshape(-1, 3)
    pts = np.vstack([pts, vertices])
    return np.array([np.max(pts[:, 2] - cutter.h(np.hypot(pts[:, 0] - x, pts[:, 1] - y))) for x, y in q]) + cutter.shift


R = 3.0
PLANE = (0.3, 0.1)


class Analytic(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plane = grid_mesh(lambda x, y: PLANE[0] * x + PLANE[1] * y, -20, 20, -20, 20, 5)
        cls.q = np.random.default_rng(1).uniform(-8, 8, (200, 2))
        n = np.array([-PLANE[0], -PLANE[1], 1.0])
        cls.n = n / np.linalg.norm(n)

    def plane_z(self, xy):
        return PLANE[0] * xy[:, 0] + PLANE[1] * xy[:, 1]

    def test_ball_on_a_plane(self):
        exact = self.plane_z(self.q) + R / self.n[2] - R
        np.testing.assert_allclose(drop(self.q, Cutter("ball", R, corner=R), self.plane), exact, atol=1e-9)

    def test_bull_and_flat_on_a_plane(self):
        rc, nxy = 1.0, math.hypot(*self.n[:2])
        u = self.n[:2] / nxy
        contact = self.q - (R - rc + rc * nxy) * u
        exact = self.plane_z(contact) - (rc - rc * self.n[2])
        np.testing.assert_allclose(drop(self.q, Cutter("bull", R, corner=rc), self.plane), exact, atol=1e-9)
        np.testing.assert_allclose(drop(self.q, Cutter("flat", R), self.plane), self.plane_z(self.q - R * u),
                                   atol=1e-9)

    def test_stock_to_leave_on_a_plane_is_a_normal_offset(self):
        leave = 0.4
        exact = self.plane_z(self.q) + (R + leave) / self.n[2] - (R + leave) + leave
        np.testing.assert_allclose(drop(self.q, Cutter("ball", R, corner=R), self.plane, leave=leave), exact,
                                   atol=1e-9)
        # The inset cutter of the gouge check: a ball reaching only what the real one cuts more than 0.1 into.
        inset = self.plane_z(self.q) + (R - 0.1) / self.n[2] - (R - 0.1) - 0.1
        np.testing.assert_allclose(drop(self.q, Cutter("ball", R, corner=R), self.plane, leave=-0.1), inset,
                                   atol=1e-9)

    def test_ball_on_a_sphere(self):
        s = 20.0
        vertices, triangles = sphere_cap(s)
        q = np.random.default_rng(2).uniform(-12, 12, (300, 2))
        exact = np.sqrt((s + R) ** 2 - (q ** 2).sum(1)) - R
        z = drop(q, Cutter("ball", R, corner=R), (vertices, triangles))
        # The tessellation's chords sit inside the sphere by at most s(1 - cos(half a facet's angle)).
        sag = s * (1 - math.cos(math.pi / 320))
        self.assertLessEqual(float(np.max(z - exact)), 1e-9)
        self.assertLessEqual(float(np.max(exact - z)), sag + 1e-9)

    def test_flat_and_ball_on_a_sloped_edge(self):
        # A vertical fin whose top edge runs from (-10, 0, 0) to (10, 0, 10).
        fin = (np.array([[-10, 0, 0], [10, 0, 10], [0, 0, -20.0]]), np.array([[0, 1, 2]]))
        rng = np.random.default_rng(3)
        q = np.column_stack([rng.uniform(-5, 5, 100), rng.uniform(-2.9, 2.9, 100)])
        reach = np.sqrt(R * R - q[:, 1] ** 2)
        np.testing.assert_allclose(drop(q, Cutter("flat", R), fin), 5 + 0.5 * (q[:, 0] + reach), atol=1e-9)
        m = 0.5
        s = m * reach / math.sqrt(1 + m * m)
        exact = 5 + 0.5 * (q[:, 0] + s) - (R - np.sqrt(reach ** 2 - s ** 2))
        np.testing.assert_allclose(drop(q, Cutter("ball", R, corner=R), fin), exact, atol=1e-9)

    def test_vee_in_a_groove(self):
        groove = grid_mesh(lambda x, y: np.abs(x) * math.tan(math.radians(60)), -10, 10, -10, 10, 3)
        wide = Cutter("cone", 3.0, half_angle=math.radians(45))
        # Wider than the groove: it rests on the walls at its rim.
        self.assertAlmostEqual(3 * (math.tan(math.radians(60)) - 1), float(drop([[0, 0.3]], wide, groove)[0]), 9)
        sharp = Cutter("cone", 3.0, half_angle=math.radians(15))
        self.assertAlmostEqual(0.0, float(drop([[0, 0.3]], sharp, groove)[0]), 9)

    def test_every_cutter_meets_a_brute_force_sample(self):
        mesh = grid_mesh(lambda x, y: 2 * np.sin(x * 0.7) * np.cos(y * 0.5) + 0.3 * np.abs(x - 1), -10, 10, -10, 10, 14)
        q = np.random.default_rng(5).uniform(-6, 6, (40, 2))
        for cutter in (Cutter("flat", 2.5), Cutter("ball", 2.5, corner=2.5), Cutter("bull", 2.5, corner=0.8),
                       Cutter("cone", 2.5, tip=0.3, half_angle=math.radians(30)),
                       Cutter("ball", 2.5, corner=2.5).offset(0.4), Cutter("flat", 2.5).offset(0.4)):
            with self.subTest(cutter=cutter):
                z, b = drop(q, cutter, mesh), brute(q, *mesh, cutter)
                self.assertGreaterEqual(float((z - b).min()), -1e-9)     # never lower than a real contact
                self.assertLess(float((z - b).max()), 0.03)               # and the sample nearly reaches it

    def test_off_the_mesh_is_minus_infinity_or_the_floor(self):
        z = drop([[100.0, 100.0]], Cutter("ball", R, corner=R), self.plane)
        self.assertEqual(-math.inf, float(z[0]))
        self.assertEqual(-5.0, float(drop([[100.0, 100.0]], Cutter("ball", R, corner=R), self.plane, floor=-5)[0]))

    def test_tools_map_to_cutters(self):
        from cadgen._internal.cam.tools import parse_tool

        cases = [({"type": "flat", "diameter_mm": 6}, "flat"), ({"type": "ball", "diameter_mm": 6}, "ball"),
                 ({"type": "bull", "diameter_mm": 6, "corner_radius_mm": 1}, "bull"),
                 ({"type": "vee", "diameter_mm": 6, "angle_deg": 90}, "cone"),
                 ({"type": "drill", "diameter_mm": 5}, "cone")]
        for raw, kind in cases:
            tool = parse_tool({"id": "T1", **raw}, 0)
            cutter = cutter_for(tool)
            self.assertEqual(kind, cutter.kind)
            d = np.linspace(0, tool.radius, 7)
            np.testing.assert_allclose(cutter.h(d), tool.height_at(d), atol=1e-9)

    def test_big_triangles_are_met_once(self):
        mesh = DropMesh(*self.plane)
        levels = mesh.buckets(R).levels
        self.assertGreaterEqual(len(levels), 1)
        listed = sum(len(entry["facet"][1]) for _, entry in levels)
        self.assertLessEqual(listed, 16 * len(mesh.f_top))


class Contours(unittest.TestCase):
    def test_marching_squares_finds_a_circle_and_push_lands_on_the_contact(self):
        spacing = 0.25
        xs = np.arange(-10, 10 + 1e-9, spacing)
        gx, gy = np.meshgrid(xs, xs, indexing="ij")
        grid = 5.0 - np.hypot(gx, gy)
        lines = contours(grid, 2.0, xs[0], xs[0], spacing)
        self.assertEqual(1, len(lines))
        radius = np.hypot(lines[0][:, 0], lines[0][:, 1])
        self.assertLess(float(np.abs(radius - 3.0).max()), 0.01)
        self.assertTrue(np.allclose(lines[0][0], lines[0][-1]))
        several = contours(grid, [1.0, 4.0], xs[0], xs[0], spacing)
        self.assertEqual(2, len(several))
        # push: a ball over the slope z = -0.5 x, from x = -5 (too high there) along +x at tip height 1: it lands
        # where drop is 1, on the free side.
        ramp = grid_mesh(lambda x, y: -0.5 * x, -20, 20, -20, 20, 3)
        ball = Cutter("ball", 1.0, corner=1.0)
        start = np.array([[-5.0, 0.0]])
        self.assertGreater(float(drop(start, ball, ramp)[0]), 1.0)
        moved, ok = push(start, np.array([[1.0, 0.0]]), 1.0, ball, ramp, distance=10, tolerance=1e-4)
        self.assertTrue(ok[0])
        z = float(drop(moved, ball, ramp)[0])
        self.assertLessEqual(z, 1.0)
        self.assertGreater(z, 1.0 - 1e-3)


if __name__ == "__main__":
    unittest.main()
