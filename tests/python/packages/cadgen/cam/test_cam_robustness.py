"""Robustness (README law 10): every input to ``cadgen cam`` ends in ``ok`` with sane outputs, or ``ok: false`` with
one teaching error and no file written; never a traceback, a hang, a NaN or an infinity in a posted file, or memory
past a bound.

Deterministic: the fuzzer is a seeded mutator over one valid job per machine kind, every part is built in a temporary
directory (never ``models/``). Each case here is either a class of input or a crash this suite found and the engine
now refuses or plans: a binary or UTF-16 job file, JSON nested past the recursion limit, numbers past any machine
(a 1e308 margin, a 0.000001 mm tool), a stepdown that makes millions of levels, a STEP that cannot be read, a drawing
kilometres across, a tiny tool beside a big one (the simulator's stamping work), an output folder that is a file.
"""

from __future__ import annotations

import contextlib
import copy
import io
import json
import os
import random
import re
import resource
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from tests.python.support.cam_fixtures import mill_job, plate_step, quiet, read_glb
from tests.python.support.cam_fixtures_cutting import bracket_dxf, cut_job
from tests.python.support.cam_fixtures_multiaxis import multiaxis_job
from tests.python.support.cam_fixtures_turning import lathe_job, shaft_step

#: The posts' file extensions, for "nothing was written".
POSTED = re.compile(r"\.(nc|ngc|gcode|tap|txt|cnc|iso|glb|tmp-\d+)$", re.IGNORECASE)
#: A NaN or an infinity spelt in a G-code word or a number (never "info" or "inch").
NOT_A_NUMBER = re.compile(r"(?<![A-Za-z])(nan|inf|infinity)(?![A-Za-z])", re.IGNORECASE)
#: Words a teaching error never holds.
TRACEBACK = ("Traceback", "File \"", "Error:", "line ")

_DIR: Path | None = None
_PARTS: dict[str, Path] = {}


def setUpModule():  # noqa: N802 - unittest's name
    global _DIR
    _DIR = Path(tempfile.mkdtemp(prefix="cam-robust-"))
    _PARTS["plate"] = _same_bytes(plate_step(_DIR, "plate"))
    _PARTS["shaft"] = _same_bytes(shaft_step(_DIR, "shaft"))
    _PARTS["bracket"] = bracket_dxf(_DIR, "bracket")


def _same_bytes(path: Path) -> Path:
    """The STEP with its export time fixed, so a rerun finds its compiled scene in the store (a cold compile is
    seconds per part, and this suite reads nine)."""
    text = path.read_text(encoding="utf-8")
    path.write_text(re.sub(r"(FILE_NAME\('[^']*',)'[^']*'", r"\1'2026-01-01T00:00:00'", text, count=1),
                    encoding="utf-8")
    return path


def tearDownModule():  # noqa: N802 - unittest's name
    if _DIR is not None:
        shutil.rmtree(_DIR, ignore_errors=True)


def _square(half: float, bottom: float = -1.0) -> dict:
    return {"polygon": [[-half, -half], [half, -half], [half, half], [-half, half]], "bottom_z": bottom}


def valid_jobs() -> dict[str, tuple[str, dict]]:
    """One job that plans ``ok`` per machine kind: (part, job)."""
    face = {"op": "face", "tool": "T1"}
    return {
        "mill": ("plate", mill_job([face, {"op": "pocket", "tool": "T1", "region": _square(8, -2)},
                                    {"op": "contour", "tool": "T1", "region": _square(40, -3)}])),
        "mill4": ("plate", multiaxis_job([face], kind="mill4")),
        "mill5": ("plate", multiaxis_job([face], kind="mill5")),
        "router": ("bracket", cut_job("router")),
        "lathe": ("shaft", lathe_job([{"op": "turn_face", "tool": "T1"}, {"op": "turn_rough", "tool": "T1"}])),
        "laser": ("bracket", cut_job("laser")),
        "plasma": ("bracket", cut_job("plasma")),
        "waterjet": ("bracket", cut_job("waterjet")),
        "wire_edm": ("bracket", cut_job("wire_edm")),
    }


def _out_dir() -> Path:
    path = Path(tempfile.mkdtemp(prefix="out-", dir=_DIR))
    return path


def _finite_json(text: str) -> None:
    """Refuse NaN and Infinity in a JSON text (Python's json writes them; no other reader takes them)."""
    def bad(token):
        raise AssertionError(f"{token} in JSON")

    json.loads(text, parse_constant=bad)


class Sane:
    """The law-10 assertions every plan here ends in."""

    def plan(self, part, job, *, out_dir: Path | None = None, seconds: float = 60.0, what: str = ""):
        from cadgen import cam
        from cadgen.results import CamPlanResult

        out_dir = out_dir or _out_dir()
        started = time.perf_counter()
        try:
            with quiet():
                result = cam.plan(part, job=job, out_dir=out_dir)
        except Exception as exc:  # noqa: BLE001 - the assertion names it
            raise AssertionError(f"{what}: cadgen.cam.plan raised {type(exc).__name__}: {exc}") from exc
        elapsed = time.perf_counter() - started
        self.assertIsInstance(result, CamPlanResult, what)
        self.assertLess(elapsed, seconds, f"{what}: took {elapsed:.1f} s")
        self.assertSane(result, out_dir, what)
        return result

    def assertSane(self, result, out_dir: Path, what: str = "") -> None:  # noqa: N802 - unittest's style
        internal = [f for f in result.findings if f.get("type") == "internal_error"]
        self.assertFalse(internal, f"{what}: {internal}")
        written = sorted(p.name for p in Path(out_dir).iterdir()) if Path(out_dir).is_dir() else []
        if not result.ok:
            self.assertEqual([], [n for n in written if POSTED.search(n) or n.startswith(".")],
                             f"{what}: refused but wrote files")
            errors = [f for f in result.findings if f["severity"] == "error"]
            self.assertTrue(errors, f"{what}: refused with no error finding")
            for item in errors:
                self.assertTeaching(item["summary"], what)
            return
        self.assertTrue(result.glb and Path(result.glb).is_file(), what)
        self.assertFalse([n for n in written if ".tmp-" in n], f"{what}: temporaries left: {written}")
        document, _ = read_glb(result.glb)
        _finite_json(json.dumps(document))
        _finite_json(json.dumps({"summary": result.summary, "verdict": result.verdict,
                                 "operations": list(result.operations)}))
        for post in result.posts:
            text = Path(post["file"]).read_text(encoding="utf-8")
            self.assertTrue(text.strip(), f"{what}: {post['file']} is empty")
            bad = [line for line in text.splitlines() if NOT_A_NUMBER.search(line.split("(")[0].split(";")[0])]
            self.assertFalse(bad[:3], f"{what}: {Path(post['file']).name} posts a NaN or an infinity")

    def assertTeaching(self, summary: str, what: str = "") -> None:  # noqa: N802 - unittest's style
        self.assertIsInstance(summary, str)
        self.assertTrue(summary.strip(), f"{what}: an empty error")
        self.assertNotIn("\n", summary, f"{what}: a multi-line error: {summary!r}")
        self.assertLess(len(summary), 600, f"{what}: an error too long to read: {summary[:200]}...")
        self.assertFalse([w for w in TRACEBACK[:2] if w in summary], f"{what}: a traceback as the error: {summary}")

    def refused(self, part, job, what: str = "", *, contains: str | None = None, **kwargs):
        result = self.plan(part, job, what=what, **kwargs)
        self.assertFalse(result.ok, f"{what}: planned, but should have been refused")
        if contains:
            self.assertIn(contains, result.findings[0]["summary"], what)
        return result


# --- job level ----------------------------------------------------------------------------------------------


class JobFiles(Sane, unittest.TestCase):
    """The job as a path, text or a dict: whatever it is, refused in one sentence."""

    def test_job_text_and_files_that_are_not_jobs_are_refused(self):
        plate = _PARTS["plate"]
        folder = _out_dir()
        binary = folder / "binary.json"
        binary.write_bytes(bytes(range(256)) * 4)
        utf16 = folder / "utf16.json"
        utf16.write_text(json.dumps(mill_job([{"op": "face", "tool": "T1"}])), encoding="utf-16")
        cases = {
            "malformed": '{"machine": ',
            "an array": "[1, 2]",
            "NaN": '{"machine": NaN}',
            "an int": 5,
            "a list": [1],
            "nothing": None,
            "empty text": "",
            "a missing path": str(folder / "nope.json"),
            "a directory": str(folder),
            "a binary file": str(binary),
            "a UTF-16 file": str(utf16),
            "nested past recursion": '{"machine": ' + "[" * 100_000 + "]" * 100_000 + "}",
            "an integer of 5000 digits": '{"tolerance_mm": 1' + "0" * 5000 + "}",
        }
        for what, job in cases.items():
            with self.subTest(what):
                self.refused(plate, job, what)

    def test_a_job_file_beside_the_part_plans(self):
        folder = _out_dir()
        path = folder / "job.cam.json"
        path.write_text(json.dumps(mill_job([{"op": "face", "tool": "T1"}])), encoding="utf-8")
        self.assertTrue(self.plan(_PARTS["plate"], str(path)).ok)

    def test_an_output_folder_that_is_a_file_or_cannot_be_written_is_refused(self):
        job = mill_job([{"op": "face", "tool": "T1"}])
        a_file = _out_dir() / "not-a-folder"
        a_file.write_text("x", encoding="utf-8")
        self.refused(_PARTS["plate"], job, "out_dir a file", out_dir=a_file, contains="is a file")
        locked = _out_dir()
        locked.chmod(0o500)
        try:
            if os.access(locked, os.W_OK):
                self.skipTest("this user writes into a read-only folder (root)")
            self.refused(_PARTS["plate"], job, "out_dir read-only", out_dir=locked, contains="could not be")
        finally:
            locked.chmod(0o700)


def _paths(node, prefix=()):
    yield prefix
    if isinstance(node, dict):
        for key, value in node.items():
            yield from _paths(value, (*prefix, key))
    elif isinstance(node, list):
        for i, value in enumerate(node):
            yield from _paths(value, (*prefix, i))


def _at(node, path):
    for key in path:
        node = node[key]
    return node


def _set(job, path, value):
    out = copy.deepcopy(job)
    _at(out, path[:-1])[path[-1]] = value
    return out


def _delete(job, path):
    out = copy.deepcopy(job)
    del _at(out, path[:-1])[path[-1]]
    return out


class JobKeys(Sane, unittest.TestCase):
    """Every key of a valid job, swapped for every wrong type and every absurd number: a plan or a refusal."""

    BAD = ("12", -1, 0, float("nan"), float("inf"), 1e308, -1e308, 1e-9, [], {}, None, True, [[[]]], {"a": {}},
           10 ** 400)

    def test_every_key_with_every_wrong_value(self):
        from cadgen._internal.cam.job import parse_job
        from cadgen._internal.cam.job_errors import CamJobError

        plate = _PARTS["plate"]
        base = valid_jobs()["mill"][1]
        planned = 0
        for path in [p for p in _paths(base) if p]:
            for value in self.BAD:
                job = _set(base, path, value)
                what = f"{'.'.join(map(str, path))} = {value!r:.30}"
                try:
                    parse_job(job)
                except CamJobError as exc:
                    self.assertTeaching(str(exc), what)
                    continue
                except Exception as exc:  # noqa: BLE001 - the assertion names it
                    self.fail(f"{what}: parse_job raised {type(exc).__name__}: {exc}")
                # It parsed: the whole plan must still end sane (an op's own keys are checked there).
                planned += 1
                with self.subTest(what):
                    self.plan(plate, job, what=what, seconds=30)
        self.assertGreater(planned, 0)

    def test_numbers_past_any_machine_are_refused_at_parse(self):
        from cadgen._internal.cam.job import parse_job as parse_keys
        from cadgen._internal.cam.job_errors import CamJobError
        from cadgen._internal.cam.run import parse_operations

        def parse_job(job):  # the job's keys, then every operation's own (a region's polygon)
            return parse_operations(parse_keys(job))

        base = valid_jobs()["mill"][1]
        cases = {
            ("stock", "margin_mm"): [1e308, 1e6, float("nan")],
            ("tools", 0, "diameter_mm"): [1e-9, 0.001, 6e9],
            ("tools", 0, "number"): [10 ** 20],
            ("tools", 0, "id"): ["T" + "9" * 5000],
            ("tools", 0, "flutes"): [10 ** 9],
            ("material",): [{"surface_m_min": 1e308, "chipload_mm": 1e308}, {"surface_m_min": 100, "chipload_mm": 50},
                            {"surface_m_min": 100, "chipload_mm": 0.01, "stepdown_fraction": 1e-9}],
            ("machine", "max_rpm"): [1e-9, 1e308],
            ("machine", "max_feed_mm_min"): [1e-9],
            ("setups", 0, "clearance_mm"): [1e9],
            ("setups", 0, "origin"): [{"xyz": [1e308, 0, 0]}],
            ("setups", 0, "operations", 0, "stepdown_mm"): [1e-9],
            ("setups", 0, "operations", 0, "stepover_mm"): [1e-9],
            ("setups", 0, "operations", 0, "speed"): [1e-9],
            ("setups", 0, "operations", 1, "region", "polygon", 1, 0): [1e9],
        }
        for path, values in cases.items():
            for value in values:
                with self.subTest(path=path, value=value):
                    with self.assertRaises(CamJobError) as caught:
                        parse_job(_set(base, path, value))
                    self.assertTeaching(str(caught.exception))
        for size in ({"kind": "box", "size_mm": [1e6, 1e6, 10]}, {"kind": "box", "margin_mm": [1e5, 1e5, 1]}):
            with self.subTest(stock=size), self.assertRaises(CamJobError):
                parse_job({**base, "stock": size})

    def test_every_enum_with_a_bad_value_is_refused(self):
        jobs = valid_jobs()
        mill, lathe, laser = jobs["mill"][1], jobs["lathe"][1], jobs["laser"][1]
        cases = [
            (mill, ("machine", "kind"), "spaceship"), (mill, ("machine", "post"), "nope"),
            (mill, ("machine", "post"), 7), (mill, ("material",), "unobtainium"),
            (mill, ("stock", "kind"), "blob"), (mill, ("tools", 0, "type"), "laser"),
            (mill, ("tools", 0, "material"), "diamond"), (mill, ("setups", 0, "orientation"), "+W"),
            (mill, ("setups", 0, "origin"), "moon"), (mill, ("setups", 0, "wcs"), "G99"),
            (mill, ("coolant",), "lava"), (mill, ("setups", 0, "operations", 0, "coolant"), "lava"),
            (mill, ("setups", 0, "operations", 0, "op"), "teleport"),
            (mill, ("setups", 0, "operations", 0, "pattern"), "spiral-ish"),
            (mill, ("setups", 0, "operations", 1, "entry"), "jump"),
            (mill, ("setups", 0, "operations", 2, "side"), "middle"),
            (lathe, ("tools", 0, "insert"), "Z"), (lathe, ("tools", 0, "side"), "up"),
            (lathe, ("stock", "axis"), "w"), (laser, ("machine", "laser_source"), "plasma"),
            (jobs["mill5"][1], ("machine", "kinematics"), "hexapod"),
        ]
        for job, path, value in cases:
            part = {id(mill): "plate", id(lathe): "shaft", id(laser): "bracket"}.get(id(job), "plate")
            with self.subTest(path=path, value=value):
                self.refused(_PARTS[part], _set(job, path, value), f"{path} = {value!r}")

    def test_unknown_keys_at_every_level_are_refused(self):
        base = valid_jobs()["mill"][1]
        for path in [p for p in _paths(base) if isinstance(_at(base, p), dict)]:
            job = copy.deepcopy(base)
            _at(job, path)["zz_unknown"] = 1
            with self.subTest(path=path):
                self.refused(_PARTS["plate"], job, f"unknown key at {path}")
        for at, value in ((("setups", 0, "origin"), {"xyz": [0, 0, 0], "zz": 1}),
                          (("setups", 0, "fixture"), {"min_mm": [0, 0, 0], "max_mm": [1, 1, 1], "zz": 1}),
                          (("material",), {"surface_m_min": 100, "chipload_mm": 0.01, "zz": 1})):
            with self.subTest(at=at):
                self.refused(_PARTS["plate"], _set(base, at, value), f"unknown key in {at}", contains="unknown key")

    def test_missing_required_keys_are_refused(self):
        base = valid_jobs()["mill"][1]
        for path in (("machine",), ("material",), ("stock",), ("tools",), ("setups",), ("machine", "kind"),
                     ("stock", "kind"), ("tools", 0, "id"), ("tools", 0, "type"), ("tools", 0, "diameter_mm"),
                     ("setups", 0, "operations"), ("setups", 0, "operations", 0, "op"),
                     ("setups", 0, "operations", 0, "tool"), ("setups", 0, "operations", 1, "region", "bottom_z")):
            with self.subTest(path=path):
                self.refused(_PARTS["plate"], _delete(base, path), f"without {path}")

    def test_duplicates_missing_tools_and_bad_faces_are_refused(self):
        base = valid_jobs()["mill"][1]
        tool = base["tools"][0]
        setup = base["setups"][0]
        pocket = {"op": "pocket", "tool": "T1"}
        cases = {
            "duplicate tool ids": {**base, "tools": [tool, {**tool, "diameter_mm": 3}]},
            "duplicate T numbers": {**base, "tools": [tool, {**tool, "id": "rougher", "number": 1}]},
            "duplicate setup ids": {**base, "setups": [setup, setup]},
            "an op naming a missing tool": _set(base, ("setups", 0, "operations", 0, "tool"), "T9"),
            "a face that does not exist": _set(base, ("setups", 0, "operations"), [{**pocket, "faces": ["#o1.f999"]}]),
            "face 0": _set(base, ("setups", 0, "operations"), [{**pocket, "faces": ["#o1.f0"]}]),
            "a face ref of 30 digits": _set(base, ("setups", 0, "operations"),
                                            [{**pocket, "faces": ["#o1.f" + "9" * 30]}]),
            "a face in wrong syntax": _set(base, ("setups", 0, "operations"), [{**pocket, "faces": ["f12"]}]),
            "an edge, not a face": _set(base, ("setups", 0, "operations"), [{**pocket, "faces": ["#o1.e1"]}]),
            "a face of another occurrence": _set(base, ("setups", 0, "operations"), [{**pocket, "faces": ["#o2.f1"]}]),
            "faces not a list of text": _set(base, ("setups", 0, "operations"), [{**pocket, "faces": [1]}]),
            "a wall named as a pocket floor": _set(base, ("setups", 0, "operations"), [{**pocket, "faces": ["#o1.f1"]}]),
        }
        for what, job in cases.items():
            with self.subTest(what):
                self.refused(_PARTS["plate"], job, what)

    def test_region_polygons_that_cross_themselves_or_have_no_area_are_refused(self):
        base = valid_jobs()["mill"][1]
        for what, polygon in {"a bow tie": [[0, 0], [10, 10], [10, 0], [0, 10]],
                              "collinear": [[0, 0], [1, 1], [2, 2]], "one point": [[0, 0], [0, 0], [0, 0]],
                              "two points": [[0, 0], [1, 1]], "not points": "square",
                              "points of three numbers": [[0, 0, 0], [1, 0, 0], [1, 1, 0]]}.items():
            with self.subTest(what):
                self.refused(_PARTS["plate"], _set(base, ("setups", 0, "operations", 1, "region", "polygon"),
                                                   polygon), what)

    def test_a_pocket_kilometres_deep_or_a_hair_per_level_is_refused_not_planned(self):
        # Before: a pocket 9 m deep planned its 4,500 levels for over a minute; a 1e-9 stepdown filled the memory
        # computing its levels.
        base = valid_jobs()["mill"][1]
        deep = _set(base, ("setups", 0, "operations", 1, "region", "bottom_z"), -9000.0)
        deep = _set(deep, ("setups", 0, "operations", 1, "stepdown_mm"), 2.0)
        self.refused(_PARTS["plate"], deep, "9 m deep pocket", contains="too big to plan", seconds=20)
        fine = _set(base, ("setups", 0, "operations", 0, "stepdown_mm"), 0.001)
        fine = _set(fine, ("stock", "margin_mm"), [2, 2, 20])
        self.refused(_PARTS["plate"], fine, "a 0.001 mm stepdown through 20 mm", contains="levels", seconds=20)

    def test_an_operation_past_the_move_budget_is_refused_with_its_name(self):
        from cadgen._internal.cam import ir

        job = mill_job([{"op": "face", "tool": "T1", "stepover_mm": 0.05}])
        with mock.patch.object(ir, "MAX_MOVES", 500):
            result = self.refused(_PARTS["plate"], job, "past the move budget", contains="too big to plan")
        self.assertIn("setups[0].operations[0]", result.findings[0]["summary"])

    def test_a_bug_in_an_operation_is_a_refusal_that_says_so(self):
        from cadgen._internal.cam.operations.face import FaceOp

        def broken(self, ctx, params):
            raise ZeroDivisionError("a planner bug")

        out = _out_dir()
        with mock.patch.object(FaceOp, "plan", broken), quiet():
            from cadgen import cam

            result = cam.plan(_PARTS["plate"], job=mill_job([{"op": "face", "tool": "T1"}]), out_dir=out)
        self.assertFalse(result.ok)
        self.assertEqual("internal_error", result.findings[0]["type"])
        self.assertIn("ZeroDivisionError", result.findings[0]["summary"])
        self.assertEqual([], list(out.iterdir()))


class FixVerdict(Sane, unittest.TestCase):
    """A plan with an error writes its GLB (the Viewer shows the problems) and no G-code at all."""

    def test_a_plan_to_fix_posts_nothing_and_removes_the_last_runs_gcode(self):
        out = _out_dir()
        ready = self.plan(_PARTS["plate"], mill_job([{"op": "face", "tool": "T1"}]), out_dir=out)
        self.assertEqual("ready", ready.verdict["status"])
        self.assertEqual(["plate.cam.glb", "plate.top.nc"], sorted(p.name for p in out.iterdir()))
        cramped = mill_job([{"op": "face", "tool": "T1"}], machine={"kind": "mill", "post": "grbl",
                                                                    "travel_mm": [10, 10, 10]})
        result = self.plan(_PARTS["plate"], cramped, out_dir=out)
        self.assertTrue(result.ok)
        self.assertEqual("fix", result.verdict["status"])
        self.assertEqual((), result.posts)
        errors = result.verdict["errors"]
        words = f"G-code not written: fix {errors} error{'s' if errors != 1 else ''} first"
        self.assertEqual(words, result.verdict["gcode"])
        self.assertEqual(words, result.warnings[0])
        self.assertEqual(["plate.cam.glb"], sorted(p.name for p in out.iterdir()))
        document, _ = read_glb(result.glb)
        cam = document["scenes"][0]["extras"]["cam"]
        self.assertEqual([], cam["posts"])
        self.assertEqual([None], [setup["post"] for setup in cam["setups"]])


# --- the seeded mutator ---------------------------------------------------------------------------------------


GARBAGE = ("", "x", None, True, False, [], {}, [1, 2], {"a": 1}, -1, 0, 1e308, float("nan"), float("inf"), 1e-9, 7,
           "12", [[[]]], {"op": "face"})
FACTORS = (0, -1, 1e9, 1e-9, 0.01, 0.1, 0.5, 3, 10, 100)


def mutate(job: dict, rng: random.Random, others: list[dict]) -> str:
    """One random change to ``job`` in place; returns what it did."""
    paths = [p for p in _paths(job) if p]
    path = rng.choice(paths)
    parent, key = _at(job, path[:-1]), path[-1]
    kind = rng.choice(("delete", "garbage", "scale", "scale", "scale", "swap_ops", "unknown", "duplicate"))
    if kind == "delete":
        del parent[key]
    elif kind == "garbage":
        parent[key] = copy.deepcopy(rng.choice(GARBAGE))
    elif kind == "scale":
        numbers = [p for p in paths if isinstance(_at(job, p), (int, float)) and not isinstance(_at(job, p), bool)]
        if not numbers:
            parent[key] = copy.deepcopy(rng.choice(GARBAGE))
            return f"garbage {path}"
        path = rng.choice(numbers)
        factor = rng.choice(FACTORS)
        _at(job, path[:-1])[path[-1]] = _at(job, path) * factor
        return f"scale {path} x{factor:g}"
    elif kind == "swap_ops":
        other = rng.choice(others)
        job["setups"] = copy.deepcopy(other["setups"]) if rng.random() < 0.3 else job.get("setups")
        if isinstance(job.get("setups"), list) and job["setups"] and isinstance(job["setups"][0], dict):
            job["setups"][0]["operations"] = copy.deepcopy(other["setups"][0]["operations"])
        if rng.random() < 0.5:
            job["tools"] = copy.deepcopy(other["tools"])
        return "swap_ops"
    elif kind == "unknown":
        if isinstance(parent[key], dict):
            parent[key]["zz_unknown"] = 1
        else:
            parent[key] = {"wrapped": parent[key]}
    else:
        value = parent[key]
        if isinstance(value, list) and value:
            value.append(copy.deepcopy(value[0]))
        else:
            parent[key] = [value, value]
    return f"{kind} {path}"


class SeededMutator(Sane, unittest.TestCase):
    """150 mutations of valid jobs, across every machine kind: each a plan or a refusal, nothing escaping."""

    SEED = 20261013
    COUNT = 150

    def test_mutated_jobs_end_in_a_plan_or_a_refusal(self):
        rng = random.Random(self.SEED)
        jobs = valid_jobs()
        kinds = list(jobs)
        others = [job for _, job in jobs.values()]
        outcomes = {"ok": 0, "refused": 0}
        out = _out_dir()
        for i in range(self.COUNT):
            kind = kinds[i % len(kinds)]
            part, base = jobs[kind]
            job = copy.deepcopy(base)
            done = [mutate(job, rng, others) for _ in range(rng.choice((1, 1, 2, 3)))]
            for child in out.iterdir():
                child.unlink()
            what = f"#{i} {kind}: {'; '.join(done)}"
            with self.subTest(what):
                result = self.plan(_PARTS[part], job, out_dir=out, what=what, seconds=45)
                outcomes["ok" if result.ok else "refused"] += 1
        # The mutator reaches past the parser: some mutated jobs still plan.
        self.assertGreater(outcomes["ok"], 10, outcomes)
        self.assertGreater(outcomes["refused"], 10, outcomes)

    def test_each_valid_job_plans(self):
        for kind, (part, job) in valid_jobs().items():
            with self.subTest(kind):
                self.assertTrue(self.plan(_PARTS[part], job, what=kind).ok, kind)


# --- geometry -------------------------------------------------------------------------------------------------


def _step(name: str, shape) -> Path:
    from build123d import export_step

    path = _DIR / f"{name}.step"
    if not path.exists():
        export_step(shape, str(path))
        _same_bytes(path)
    return path


def _dxf(name: str, fill) -> Path:
    import ezdxf

    document = ezdxf.new("R2010")
    document.header["$INSUNITS"] = 4
    fill(document.modelspace())
    path = _DIR / f"{name}.dxf"
    document.saveas(path)
    return path


def _box(x, y, z):
    from build123d import Align, Box

    return Box(x, y, z, align=(Align.CENTER, Align.CENTER, Align.MIN))


class Geometry(Sane, unittest.TestCase):
    """Parts at the edges: tiny, huge, round, open, several, none; drawings empty, annotation only, open."""

    def features(self, path, **kwargs):
        from cadgen import cam
        from cadgen.results import CamFeaturesResult

        with quiet():
            result = cam.features(path, **kwargs)
        self.assertIsInstance(result, CamFeaturesResult)
        if not result.ok:
            self.assertTeaching(result.findings[0]["summary"], str(path))
        return result

    def test_a_half_millimetre_cube(self):
        tiny = _step("tiny", _box(0.5, 0.5, 0.5))
        self.assertTrue(self.features(tiny).ok)
        self.plan(tiny, mill_job([{"op": "face", "tool": "T1"}]), what="tiny face")
        self.plan(tiny, mill_job([{"op": "contour", "tool": "T1", "region": _square(3)}]), what="tiny contour")

    def test_a_two_metre_plate_adapts_and_does_not_hang(self):
        huge = _step("huge", _box(2000, 1000, 10))
        self.assertEqual([2000.0, 1000.0, 10.0], self.features(huge).bbox_mm["size"])
        job = mill_job([{"op": "face", "tool": "T1"}], machine={"kind": "router", "post": "grbl"})
        result = self.plan(huge, job, what="2 m plate", seconds=60)
        self.assertTrue(result.ok)

    def test_a_sphere_has_no_flat_face_to_name(self):
        from build123d import Sphere

        sphere = _step("sphere", Sphere(10))
        reading = self.features(sphere)
        self.assertTrue(reading.ok)
        self.assertEqual((), tuple(f for f in reading.floors if f.get("normal") == "+Z"))
        self.assertTrue(self.plan(sphere, mill_job([{"op": "face", "tool": "T1"}]), what="sphere face").ok)
        self.refused(sphere, mill_job([{"op": "pocket", "tool": "T1", "faces": [reading.faces[0]["ref"]]}]),
                     "a pocket on a sphere", contains="sphere")

    def test_an_open_shell_touching_a_box_along_an_edge(self):
        from build123d import Compound, Pos, Shell

        # A box with no lid (an open shell, no solid) and, beside it, a box touching it only along an edge.
        box = _box(20, 20, 10)
        lid = [f for f in box.faces() if f.center().Z < 9.9]
        both = _step("open", Compound([Shell(lid), Pos(20, 20, 0) * _box(20, 20, 10)]))
        self.features(both)
        self.plan(both, mill_job([{"op": "face", "tool": "T1"}]), what=both.name)

    def test_an_assembly_needs_an_occurrence_and_a_shape_with_no_surface_is_refused(self):
        from build123d import Compound, Cylinder, Edge, Pos

        parts = [_box(10, 10, 10), Pos(30, 0, 0) * _box(10, 10, 10), Pos(60, 0, 0) * Cylinder(5, 10)]
        for k, part in enumerate(parts):
            part.label = f"p{k}"
        assembly = _step("assembly", Compound(children=parts, label="asm"))
        self.assertFalse(self.features(assembly).ok)
        self.assertTrue(self.features(assembly, occurrence="#o1.2").ok)
        for occurrence in ("#o9", "garbage!", "#o1.2.f1", ""):
            with self.subTest(occurrence=occurrence):
                self.features(assembly, occurrence=occurrence or None)
        self.refused(assembly, mill_job([{"op": "face", "tool": "T1"}]), "an assembly", contains="--occurrence")
        edge = _step("edge", Edge.make_line((0, 0, 0), (10, 0, 0)))
        self.assertFalse(self.features(edge).ok)
        self.refused(edge, mill_job([{"op": "face", "tool": "T1"}]), "no solids")

    def test_files_that_are_not_parts_are_refused(self):
        empty = _DIR / "empty.step"
        empty.write_text("", encoding="utf-8")
        folder = _out_dir()
        text = folder / "part.txt"
        text.write_text("hello", encoding="utf-8")
        junk = _DIR / "junk.dxf"
        junk.write_bytes(bytes(range(256)) * 4)
        job = mill_job([{"op": "face", "tool": "T1"}])
        for path in (empty, folder / "missing.step", folder, text, junk, _DIR / "missing.dxf"):
            with self.subTest(path.name):
                self.assertFalse(self.features(path).ok)
                self.refused(path, job, path.name)

    def test_drawings_empty_annotation_only_open_or_kilometres_across(self):
        laser = cut_job("laser")
        empty = _dxf("empty", lambda m: None)
        text = _dxf("text", lambda m: m.add_text("HELLO"))
        open_only = _dxf("open", lambda m: m.add_lwpolyline([(0, 0), (10, 0), (10, 10)]))
        point = _dxf("point", lambda m: m.add_point((0, 0)))
        flat = _dxf("degenerate", lambda m: m.add_lwpolyline([(0, 0)] * 4, close=True))
        huge = _dxf("huge", lambda m: m.add_circle((0, 0), 1e7))
        for path in (empty, text, open_only, point, flat, huge):
            with self.subTest(path.name):
                self.refused(path, laser, path.name)
        self.assertIn("m across", self.refused(huge, laser).findings[0]["summary"])

    def test_an_open_curve_beside_a_profile_is_said_not_dropped(self):
        def mixed(space):
            space.add_lwpolyline([(0, 0), (50, 0), (50, 30), (0, 30)], close=True)
            space.add_lwpolyline([(60, 0), (70, 0), (70, 10)])

        result = self.plan(_dxf("mixed", mixed), cut_job("laser"), what="profile + open curve")
        self.assertTrue(result.ok)
        self.assertTrue([w for w in result.warnings if "open curve" in w], result.warnings)

    def test_tools_stepdowns_stock_and_origin_at_their_edges(self):
        plate = _PARTS["plate"]
        face = {"op": "face", "tool": "T1"}
        big = [{"id": "T1", "type": "flat", "diameter_mm": 200, "flute_length_mm": 30, "stickout_mm": 40}]
        self.plan(plate, mill_job([face, {"op": "pocket", "tool": "T1", "region": _square(5, -2)}], tools=big),
                  what="a tool bigger than every feature")
        self.plan(plate, mill_job([face, {"op": "contour", "tool": "T1", "region": _square(35), "stepdown_mm": 500}]),
                  what="stepdown past the part's height")
        self.plan(plate, mill_job([{**face, "stepover": 1.0}]), what="stepover 1.0")
        self.refused(plate, mill_job([face], stock={"kind": "box", "size_mm": [10, 10, 2]}), "stock smaller than part")
        outside = mill_job([face], setups=[{"id": "top", "origin": {"xyz": [500, 500, 500]}, "operations": [face]}])
        self.plan(plate, outside, what="origin outside the stock")
        below = mill_job([face], setups=[{"id": "top", "origin": {"xyz": [0, 0, -500]}, "operations": [face]}])
        self.plan(plate, below, what="origin below the stock")

    def test_a_big_tool_beside_a_tiny_one_simulates_in_seconds(self):
        # Before: the 25 mm cutter was stamped every 0.05 mm (the grid the 0.2 mm tool needs): 95 s on this plate.
        tools = [{"id": "T1", "type": "flat", "diameter_mm": 25, "flute_length_mm": 30, "stickout_mm": 40},
                 {"id": "T2", "type": "flat", "diameter_mm": 0.2}]
        job = mill_job([{"op": "face", "tool": "T1"},
                        {"op": "pocket", "tool": "T2", "region": _square(2, -0.5)}], tools=tools)
        self.assertTrue(self.plan(_PARTS["plate"], job, what="25 mm + 0.2 mm", seconds=40).ok)

    def test_an_unused_tiny_tool_does_not_size_the_stock_grid(self):
        tools = [{"id": "T1", "type": "flat", "diameter_mm": 6}, {"id": "T2", "type": "ball", "diameter_mm": 0.04}]
        result = self.plan(_PARTS["plate"], mill_job([{"op": "face", "tool": "T1"}], tools=tools), what="unused T2")
        self.assertGreaterEqual(result.summary["stock_cell_mm"], 0.75)


# --- the CLI --------------------------------------------------------------------------------------------------


class Cli(unittest.TestCase):
    """Bad arguments exit non-zero, with one JSON line under --json, and never a traceback."""

    def run_cli(self, *argv) -> tuple[int, str, str]:
        from cadgen import cli

        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                code = cli.main(list(argv))
            except SystemExit as exc:      # argparse: a usage error
                code = exc.code if isinstance(exc.code, int) else 1
        return code, out.getvalue(), err.getvalue()

    def test_bad_arguments(self):
        plate = str(_PARTS["plate"])
        folder = _out_dir()
        job = json.dumps(mill_job([{"op": "face", "tool": "T1"}]))
        a_file = folder / "a-file"
        a_file.write_text("x", encoding="utf-8")
        verbs = {
            "no job": ("cam", "plan", plate),
            "malformed job": ("cam", "plan", plate, "--job", '{"machine": '),
            "a missing job file": ("cam", "plan", plate, "--job", str(folder / "nope.json")),
            "a folder as the job": ("cam", "plan", plate, "--job", str(folder)),
            "a missing part": ("cam", "plan", str(folder / "nope.step"), "--job", job),
            "a folder as the part": ("cam", "plan", str(folder), "--job", job),
            "a text file as the part": ("cam", "plan", str(a_file), "--job", job),
            "an output folder that is a file": ("cam", "plan", plate, "--job", job, "--out-dir", str(a_file)),
            "features of a missing part": ("cam", "features", str(folder / "nope.step")),
            "features of a folder": ("cam", "features", str(folder)),
            "an unknown occurrence": ("cam", "features", plate, "--occurrence", "#o9"),
            "a junk occurrence": ("cam", "features", plate, "--occurrence", "!!"),
        }
        for what, argv in verbs.items():
            with self.subTest(what):
                code, out, err = self.run_cli(*argv, "--json")
                self.assertNotEqual(0, code, what)
                self.assertNotIn("Traceback", out + err, what)
                lines = [line for line in out.splitlines() if line.strip()]
                self.assertEqual(1, len(lines), f"{what}: {out!r}")
                answer = json.loads(lines[0])
                self.assertFalse(answer["ok"], what)
                code, out, err = self.run_cli(*argv)
                self.assertNotEqual(0, code, what)
                self.assertNotIn("Traceback", out + err, what)
        for what, argv in {"no target": ("cam", "plan"), "an unknown flag": ("cam", "plan", plate, "--bogus"),
                           "features with no target": ("cam", "features")}.items():
            with self.subTest(what):
                code, out, err = self.run_cli(*argv, "--json")
                self.assertNotEqual(0, code, what)
                self.assertNotIn("Traceback", out + err, what)
                self.assertEqual("", out.strip(), what)

    def test_a_tiny_tool_over_a_big_area_stays_within_memory(self):
        # Before: a 0.1 mm tool on this plate peaked at 2.1 GB and misjudged the stock (dots, not a cut); now the
        # simulator says it cannot follow the tool, and the run stays well under that.
        job = json.dumps(mill_job([{"op": "face", "tool": "T1"}], tools=[{"id": "T1", "type": "flat",
                                                                          "diameter_mm": 0.1}]))
        script = ("import sys; from cadgen import cli; raise SystemExit(cli.main(sys.argv[1:]))")
        env = {**os.environ, "PYTHONPATH": os.pathsep.join([str(Path(__file__).resolve().parents[5] / "packages/cadgen/src"),
                                                           os.environ.get("PYTHONPATH", "")])}
        before = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
        done = subprocess.run([sys.executable, "-c", script, "cam", "plan", str(_PARTS["plate"]), "--job", job,
                               "--out-dir", str(_out_dir()), "--json"], capture_output=True, text=True, timeout=180,
                              env=env)
        peak = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
        self.assertNotIn("Traceback", done.stderr)
        answer = json.loads(done.stdout.strip().splitlines()[-1])
        self.assertTrue(answer["ok"], answer.get("findings"))
        self.assertIn("setup_not_simulated", [f["type"] for f in answer["findings"]])
        self.assertNotIn("material_left", [f["type"] for f in answer["findings"]])
        scale = 1 if sys.platform == "darwin" else 1024          # ru_maxrss: bytes on macOS, KiB on Linux
        if peak > before:
            self.assertLess(peak * scale, 1.5e9, f"peak {peak * scale / 1e9:.2f} GB")


if __name__ == "__main__":
    unittest.main()
