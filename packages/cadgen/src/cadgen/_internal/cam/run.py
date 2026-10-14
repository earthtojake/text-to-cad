"""What the ``cadgen.cam`` verbs do, end to end: :func:`list_features` and :func:`plan_job`.

``plan_job`` is the pipeline: parse the job (and every operation's own keys, before anything heavy) -> read the part
-> build the stock -> per setup: its WCS, heights and sections, then each operation planned in order with the tool
change, spindle and coolant events around it -> simulate the stock -> run the checks -> the verdict -> post each
setup and write the GLB, to temporary names renamed into place only when everything is written.

Before anything else a plan removes what an earlier plan of the same document left in the output folder (the
result GLB, every posted file it lists, and every ``<stem>.<setup>[.<tool>].<post extension>`` file whose header
says cadgen posted it for this document), so a job that cannot run (:class:`CamJobError`, answered ``ok: false``
with one error finding), or one that fails any other way, leaves no result GLB and no posted file, never the last
run's "Ready to cut". A post that writes one file per tool (``Post.split_by_tool``: GRBL cannot re-zero a tool after
``M0``) posts a setup with several tools as ``<stem>.<setup>.<label><ext>`` per tool, in program order.
"""

from __future__ import annotations

import dataclasses
import json
import math
import os
import re
import struct
import sys
import time
from pathlib import Path

from cadgen._internal.atomic_replace import replace_atomic
from cadgen._internal.cam.checks.base import finding
from cadgen._internal.cam.job_errors import CamJobError, PlanError, PostRefusal
from cadgen.cli_logging import CliLogger
from cadgen.results import CamFeaturesResult, CamPlanResult, _assumed_value

__all__ = ["headline", "list_features", "parse_operations", "plan_job", "plan_setups"]


#: The machine keys an assumption of which only shapes the cycle time, not the posted program.
_CYCLE_TIME_KEYS = frozenset({"machine.rapid_mm_min", "machine.tool_change_s"})

#: Op meta keys that steer the run rather than describe the cut, kept out of a row's facts.
_NOT_FACTS = frozenset({"no_gouge_check", "note_level", "spindle_dir", "findings", "adapted", "unreachable",
                        "plan_error"})

def job_finding(message: str) -> dict:
    """A job that cannot run, as the one error finding its result carries."""
    return finding("job", "error", "job", message, "the job was refused before anything was planned; nothing was "
                   "written. Change the job (or the --occurrence) as the summary says and plan again")


def tool_changes(op_plans) -> dict:
    """``{"count", "order"}``: how many times the running order switches tool, across setups too (loading the first
    tool is not one), and the tools in the order they run, a tool listed again each time it comes back."""
    order: list[str] = []
    for op in op_plans:
        if op.tool is not None and "plan_error" not in op.meta and (not order or order[-1] != op.tool.id):
            order.append(op.tool.id)
    return {"count": max(0, len(order) - 1), "order": order}


def plan_error_finding(op) -> dict:
    """The error finding of an operation that could not be planned (:class:`PlanError`): its ``kind`` is the type."""
    error = op.meta["plan_error"]
    where = f"operation {op.index + 1} ({op.summary}, setup {op.setup})"
    return finding("plan", "error", error["kind"], f"{where} cannot be planned: {error['message']}",
                   "nothing of this operation is in the program and no G-code was written; every other operation was "
                   "planned. Change the job as the summary says (another tool, setup, depth or operation) and plan "
                   "again", [{"setup": op.setup, "operation": op.index}])


def _toward(reading: dict, direction: str) -> dict:
    """What a tool coming from ``direction`` (``-Z``: from under the part) can work: the holes it reaches, the floors
    facing it, the flat faces turned toward it and the round walls and cones along it (curved faces stay: their
    reach is not read). Occlusion by other faces is not judged here; a hole's ``reach`` is."""
    import numpy as np

    axis = np.zeros(3)
    axis["XYZ".index(direction[1])] = 1.0 if direction[0] == "+" else -1.0

    def keep(face: dict) -> bool:
        if face["surface"] == "plane":
            return float(np.dot(face["normal"], axis)) > 1e-6
        if face["surface"] in ("cylinder", "cone"):
            return abs(float(np.dot(face["axis"], axis))) > 1.0 - 1e-6
        return True

    return {"faces": [f for f in reading["faces"] if keep(f)],
            "holes": [h for h in reading["holes"] if direction in h.get("reach", ())],
            "floors": [f for f in reading["floors"] if f["normal"] == direction],
            "profiles": reading["profiles"] if direction == "+Z" else []}


def list_features(target: Path, *, occurrence: str | None = None, direction: str | None = None) -> CamFeaturesResult:
    from cadgen._internal.cam.features import read_features
    from cadgen._internal.cam.job import ORIENTATIONS
    from cadgen._internal.cam.job_errors import choice
    from cadgen._internal.cam.part import read_part

    try:
        if direction is not None:
            choice(direction, ORIENTATIONS, "direction")
        part = read_part(Path(target), occurrence=occurrence)
        reading = read_features(part)
        if direction is not None:
            reading = _toward(reading, direction)
    except CamJobError as exc:
        return CamFeaturesResult(ok=False, document=Path(target), findings=(job_finding(str(exc)),))
    except OSError as exc:
        return CamFeaturesResult(ok=False, document=Path(target), findings=(job_finding(
            f"{Path(target).name} could not be read: {exc.strerror or exc}"),))
    except Exception as exc:  # noqa: BLE001 - a bug in cadgen is a refusal that says so, never a traceback
        return CamFeaturesResult(ok=False, document=Path(target), findings=(finding(
            "job", "error", "internal_error",
            f"cadgen cam failed reading this part ({type(exc).__name__}: {str(exc)[:200]})",
            "this is a bug in cadgen, not in the part: report it with the part"),))
    low, high = part.bbox
    bbox = {"min": [round(float(v), 4) + 0.0 for v in low], "max": [round(float(v), 4) + 0.0 for v in high],
            "size": [round(float(b - a), 4) + 0.0 for a, b in zip(low, high)]}
    return CamFeaturesResult(ok=True, document=Path(target), occurrence=part.occurrence, bbox_mm=bbox,
                             faces=tuple(reading["faces"]), holes=tuple(reading["holes"]),
                             floors=tuple(reading["floors"]), profiles=tuple(reading["profiles"]))


# --- plan ------------------------------------------------------------------------------------------------

def _duration_words(seconds: float) -> str:
    """``42 s``, ``4 min``, ``1 h 05 min``: rounded first, so 59.6 s is ``1 min`` and 3570 s ``1 h 00 min`` (never
    ``60 s`` or ``1 h 60 min``)."""
    whole = max(1, round(seconds))
    if whole < 60:
        return f"{whole} s"
    minutes = max(1, round(seconds / 60))
    if minutes < 60:
        return f"{minutes} min"
    hours, rest = divmod(minutes, 60)
    return f"{hours} h {rest:02d} min"


def headline(errors: int, seconds: float, tools: int) -> str:
    """``Ready to cut · 42 min · 3 tools`` or ``2 to fix · 42 min · 3 tools``."""
    head = "Ready to cut" if errors == 0 else f"{errors} to fix"
    return f"{head} · {_duration_words(seconds)} · {tools} tool{'s' if tools != 1 else ''}"


def _glb_path(document: Path, out_dir: Path | None) -> Path:
    """The result GLB's path: the document's stem beside it, or in ``out_dir``. Needs nothing from the job."""
    folder = Path(out_dir) if out_dir is not None else document.parent
    return folder / f"{document.stem}.cam.glb"


def _naming(document: Path) -> re.Pattern:
    """A posted file's name for this document: ``<stem>.<setup>.<ext>``, or ``<stem>.<setup>.<tool>.<ext>``."""
    return re.compile(rf"^{re.escape(document.stem)}\.([A-Za-z0-9_-]{{1,40}})(?:\.([A-Za-z0-9_-]{{1,40}}))?"
                      r"(\.[A-Za-z0-9]+)$")


def _glb_cam(path: Path) -> dict | None:
    """The plan a cadgen GLB carries (``scenes[0].extras.cam``), read from its JSON chunk alone; None for anything
    else (not there, not a GLB, not cadgen's)."""
    try:
        with open(path, "rb") as handle:
            head = handle.read(20)
            if len(head) < 20:
                return None
            magic, _, _, length, kind = struct.unpack("<4sIIII", head)
            if magic != b"glTF" or kind != 0x4E4F534A or length > 64 * 1024 * 1024:
                return None
            document = json.loads(handle.read(length))
    except (OSError, ValueError, RecursionError, struct.error):
        return None
    scenes = document.get("scenes") if isinstance(document, dict) else None
    extras = scenes[0].get("extras") if isinstance(scenes, list) and scenes and isinstance(scenes[0], dict) else None
    cam = extras.get("cam") if isinstance(extras, dict) else None
    return cam if isinstance(cam, dict) and cam.get("generator") == "cadgen cam" else None


def _posted_for(path: Path, document: Path, setup_id: str) -> bool:
    """Whether a posted file's header says cadgen wrote it for ``document``'s setup ``setup_id``."""
    try:
        with open(path, "rb") as handle:
            head = handle.read(2048).decode("utf-8", errors="replace").lower()
    except OSError:
        return False
    return "cadgen" in head and f"{document.name.lower()} - setup {setup_id.lower()}" in head


def previous_outputs(document: Path, out_dir: Path | None, extensions) -> list[Path]:
    """What an earlier plan of ``document`` may have left in the output folder: its result GLB, every posted file
    that GLB lists, and every file named like a posted one (``<stem>.<setup>[.<tool>]<ext>``, ``ext`` a post's) whose
    header says cadgen posted it for this document. Nothing outside the folder, nothing named otherwise."""
    glb_path = _glb_path(document, out_dir)
    folder = glb_path.parent
    naming = _naming(document)
    extensions = set(extensions)
    found: dict[str, Path] = {}
    if glb_path.is_file():
        found[glb_path.name] = glb_path
    cam = _glb_cam(glb_path) if glb_path.is_file() else None
    def items(value) -> list:
        return value if isinstance(value, list) else []

    listed = []
    if cam is not None:
        listed += [entry.get("file") for entry in items(cam.get("posts")) if isinstance(entry, dict)]
        for setup in items(cam.get("setups")):
            if isinstance(setup, dict):
                listed += [setup.get("post"), *items(setup.get("posts"))]
    for name in listed:
        if not isinstance(name, str) or not name or "/" in name or "\\" in name:
            continue
        match = naming.match(name)
        if match and match.group(3) in extensions and (folder / name).is_file():
            found[name] = folder / name
    if folder.is_dir():
        for child in folder.iterdir():
            match = naming.match(child.name)
            if (match and match.group(3) in extensions and child.name not in found and child.is_file()
                    and _posted_for(child, document, match.group(1))):
                found[child.name] = child
    return sorted(found.values())


def _remove_stale(paths) -> None:
    for path in paths:
        try:
            Path(path).unlink()
        except FileNotFoundError:
            pass


def _check_drawing_stock(document: Path, stock) -> None:
    """A DXF has no thickness of its own: it is cut from a sheet that names one, never from a guessed 1 mm."""
    from cadgen._internal.cam.part import DXF_SUFFIXES

    if document.suffix.lower() not in DXF_SUFFIXES:
        return
    if stock.kind != "sheet":
        raise CamJobError(f"{document.name} is a drawing: it is cut from a sheet, not a {stock.kind}; set stock to "
                          "{\"kind\": \"sheet\", \"thickness_mm\": 3} with the sheet's real thickness")
    if stock.thickness_mm is None:
        raise CamJobError(f"{document.name} is a drawing with no thickness of its own: give the sheet's, like "
                          "stock {\"kind\": \"sheet\", \"thickness_mm\": 3} (cutting speeds and the simulated "
                          "sheet depend on it)")


def _refused(document: Path, message: str, timings: dict) -> CamPlanResult:
    return CamPlanResult(ok=False, document=document, findings=(job_finding(message),), timings=timings)


def _relative(target: Path, start: Path) -> str:
    try:
        return Path(os.path.relpath(Path(target).resolve(), Path(start).resolve())).as_posix()
    except ValueError:  # another drive on Windows
        return Path(target).resolve().as_posix()


def plan_job(target: Path, *, job, occurrence: str | None = None, post: str | None = None,
             out_dir: Path | None = None, verbose: bool = False) -> CamPlanResult:
    from cadgen._internal.cam import posts as post_registry
    from cadgen._internal.cam.job import parse_job

    logger = CliLogger("cam", verbose=verbose)
    document = Path(target)
    timings: dict[str, float] = {}
    started = time.perf_counter()
    glb_path = _glb_path(document, out_dir)
    try:
        if out_dir is not None and Path(out_dir).exists() and not Path(out_dir).is_dir():
            raise CamJobError(f"out_dir {out_dir} is a file; pass the folder the outputs go in")
        # Whatever happens next (a refusal, a crash, a plan), the last run's outputs are not left standing beside it.
        _remove_stale(previous_outputs(document, out_dir,
                                       {entry.extension for entry in post_registry.REGISTRY.values()}))
        parsed = parse_job(job, post=post, part_dir=document.parent)
        _check_drawing_stock(document, parsed.stock)
        entry = post_registry.entry_for(parsed.machine.post, parsed.machine.kind)
        operations = parse_operations(parsed)
        post = post_registry.get_post(parsed.machine.post, parsed.machine.kind)
        timings["parse_s"] = round(time.perf_counter() - started, 4)
        return _plan(document, parsed, operations, post, glb_path, entry.extension, logger, timings, started,
                     occurrence=occurrence)
    except CamJobError as exc:
        timings["total_s"] = round(time.perf_counter() - started, 4)
        logger.debug(f"refused: {exc}")
        return _refused(document, str(exc), timings)
    except OSError as exc:
        # A folder that cannot be written, a full disk, a file that cannot be read: said, with nothing written (the
        # write removes its temporaries and whatever it had placed).
        timings["total_s"] = round(time.perf_counter() - started, 4)
        where = f" ({exc.filename})" if getattr(exc, "filename", None) else ""
        return _refused(document, f"a file could not be read or written{where}: {exc.strerror or exc}; nothing was "
                                  "written", timings)
    except Exception as exc:  # noqa: BLE001 - the last resort: a bug in cadgen is a refusal that says so, never a traceback
        timings["total_s"] = round(time.perf_counter() - started, 4)
        logger.debug(f"internal error: {type(exc).__name__}: {exc}")
        return CamPlanResult(ok=False, document=document, timings=timings, findings=(finding(
            "job", "error", "internal_error",
            f"cadgen cam failed while planning this job ({type(exc).__name__}: {str(exc)[:200]}); nothing was written",
            "this is a bug in cadgen, not in the job: report it with the job and the part. Changing the job (another "
            "tool, operation or stock) may route round it"),))
    finally:
        # The stock replays an operation kept for the next one (StockNow) belong to this plan, not the process.
        replays = getattr(sys.modules.get("cadgen._internal.cam.milling3d"), "_REPLAYS", None)
        if replays is not None:
            replays.clear()


def _plan(document, parsed, operations, post, glb_path, extension, logger, timings, started, *,
          occurrence: str | None = None) -> CamPlanResult:
    from cadgen._internal.cam import fit
    from cadgen._internal.cam.checks import run_checks
    from cadgen._internal.cam.checks.base import CheckContext
    from cadgen._internal.cam.outputs import line_segments, sample_axes, write_glb
    from cadgen._internal.cam.part import read_part
    from cadgen._internal.cam.stock import SimReport, build_stock, create_stock_sim

    def lap(name: str, since: float) -> float:
        now = time.perf_counter()
        timings[name] = round(now - since, 4)
        return now

    machine = parsed.machine
    tools = {tool.id: tool for tool in parsed.tools}
    tolerance = parsed.tolerance_mm
    budget = fit.Budget()
    adapted: list[dict] = []
    warnings: list[str] = []
    mark = time.perf_counter()
    with logger.timed("read part"):
        part = read_part(document, occurrence=occurrence, sheet_thickness_mm=parsed.stock.thickness_mm)
        stock = build_stock(parsed.stock, part, base_dir=parsed.base_dir)
    mark = lap("part_s", mark)
    warnings += list(part.notes)
    # What the plan takes that nobody stated (the machine's generic values, a used tool's catalogue lengths) is the
    # job's ``assumed``: the result, the GLB and the Viewer each list it.
    logger.debug(f"part {part.occurrence or document.name}: {len(part.triangles)} triangles; stock {stock.kind}")

    setup_plans, op_plans, notes = plan_setups(parsed, operations, part, stock, logger)
    warnings += notes
    # An operation that coarsened its own sampling says so in its meta (``adapted``: fit-ladder steps).
    adapted += [{**step, "operation": op.index} for op in op_plans for step in op.meta.get("adapted", ())]
    mark = lap("plan_s", mark)

    # Times: program time runs on across setups.
    clock = 0.0
    by_index = {op.index: op for op in op_plans}
    for plan in setup_plans:
        plan.t0 = clock
        plan.time_s = plan.toolpath.time_s(machine)
        op_times = plan.toolpath.op_times(machine)
        for op_range in plan.toolpath.ops:
            op = by_index[op_range.index]
            t0, t1 = op_times[op_range.index]
            op.t0, op.t1, op.time_s = clock + t0, clock + t1, t1 - t0
            op.start, op.end = op_range.start, op_range.end
        clock += plan.time_s
    duration = clock

    # Simulate.
    # The grid is sized by the tools that cut, not by one the job lists and never uses.
    cell, steps = fit.stock_cell(stock, [op.tool for op in op_plans if op.tool is not None], budget)
    adapted += steps
    sim, steps = create_stock_sim(machine.kind, stock, part, cell_mm=cell, tolerance_mm=tolerance)
    adapted += steps
    length = float(sum(plan.toolpath.lengths().sum() for plan in setup_plans))
    step, steps = fit.sim_step(length, cell, budget)
    adapted += steps
    if hasattr(sim, "step"):
        sim.step = step
    reports = {}
    removed_before = sim.volume()
    with logger.timed("simulate"):
        for plan in setup_plans:
            # A sample spacing wider than a tool's radius (a tiny tool on a long program) stamps dots, not a cut: the
            # stock left would be judged wrong, so the setup goes unsimulated, and says so, rather than misjudged.
            fine = [op.tool for op in op_plans if op.setup == plan.setup.id and op.tool is not None
                    and op.tool.family == "mill" and op.tool.radius < step]
            if fine and hasattr(sim, "step"):
                tool = min(fine, key=lambda t: t.radius)
                report = SimReport(setup=plan.setup.id, skipped=(
                    f"the simulation samples every {step:.3g} mm along the program's {length / 1000:.1f} m of path, "
                    f"wider than {tool.id}'s {tool.radius:g} mm radius, so it cannot follow that tool's cut"))
            else:
                report = sim.cut(plan.toolpath, tools, plan.wcs)
            reports[plan.setup.id] = report
            if report.skipped and not any(a.get("setup") == plan.setup.id for a in adapted):
                adapted.append({"step": "stock_sim", "setup": plan.setup.id, "words": report.skipped})
    mark = lap("simulate_s", mark)

    ctx = CheckContext(job=parsed, part=part, stock=stock, sim=sim, sim_reports=reports, setups=setup_plans,
                       ops=op_plans, tolerance_mm=tolerance, logger=logger)
    with logger.timed("checks"):
        findings, ran, skipped = run_checks(ctx)
    # An operation's own findings (ctx.meta["findings"], e.g. a drill the wrong size for its holes) join the checks'.
    planner = [item for op in op_plans for item in op.meta.get("findings", ())]
    planner += [plan_error_finding(op) for op in op_plans if "plan_error" in op.meta]
    if planner:
        from cadgen._internal.cam.checks.base import by_severity

        findings = by_severity(list(findings) + planner)
    for op in op_plans:
        if op.meta.get("plunges"):
            warnings.append(f"{op.summary}: plunged straight in {op.meta['plunges']} time(s); the tool must cut at "
                            "its centre (most end mills do; check yours)")
        if op.meta.get("note") and op.meta.get("note_level") == "info":
            findings = list(findings)
            # What the op did on purpose (a chamfer cut into the modelled edge): an info finding, not a warning.
            findings.append(finding("plan", "info", "note", f"{op.summary}: {op.meta['note']}", op.meta["note"],
                                    [{"setup": op.setup, "operation": op.index}]))
        elif op.meta.get("note"):
            warnings.append(f"{op.summary}: {op.meta['note']}")
    mark = lap("checks_s", mark)

    used_tools = sorted({op.tool.id for op in op_plans if op.tool is not None})
    changes = tool_changes(op_plans)
    lite = [{"operation": op.index, "op": op.operation.name, "limits": list(op.operation.limits)}
            for op in op_plans if op.operation.status == "lite"]

    # Post every setup, then the GLB: all to temporary names first. ``rendered``: (setup id, tool label or None,
    # final path, text) per posted file, in program order. A plan with an error posts no G-code at all, so nothing a
    # machine could run stands beside the part; the GLB is still written, for the Viewer to show the problems (and
    # the last run's posted files went before planning). A post that cannot write what the job needs
    # (:class:`PostRefusal`) is one more error, on its operation, and nothing is posted.
    folder = glb_path.parent
    rendered = []
    split = bool(getattr(post, "split_by_tool", False))
    if not any(f["severity"] == "error" for f in findings):
        try:
            for k, plan in enumerate(setup_plans):
                rendered += _render_setup(post, plan, k, setup_plans, op_plans, tools, machine, document, parsed,
                                          tolerance, lite, by_index, split, folder, extension)
        except PostRefusal as exc:
            from cadgen._internal.cam.checks.base import by_severity

            rendered = []
            findings = by_severity(list(findings) + [post_refusal_finding(exc, post, op_plans)])
    errors = sum(1 for f in findings if f["severity"] == "error")
    warn_count = sum(1 for f in findings if f["severity"] == "warning")
    verdict = {"status": "ready" if errors == 0 else "fix", "headline": headline(errors, duration, len(used_tools)),
               "errors": errors, "warnings": warn_count, "duration_s": round(duration, 2), "tools": len(used_tools)}
    if lite:
        verdict["lite"] = lite
    if errors:
        unposted = f"G-code not written: fix {errors} error{'s' if errors != 1 else ''} first"
        verdict["gcode"] = unposted
        warnings.insert(0, unposted)
    names = [path.name for _, _, path, _ in rendered]
    if len(set(names)) != len(names):
        raise ValueError(f"post {post.name} posted two files at one name: {', '.join(names)}")
    mark = lap("post_s", mark)

    glb_dir = glb_path.parent
    operations_out = []
    setups_out = []
    for plan in setup_plans:
        ops = []
        for op in [o for o in op_plans if o.setup == plan.setup.id]:
            row = {
                "index": op.index, "setup": op.setup, "op": op.operation.name, "plain": op.operation.plain,
                "family": op.operation.family, "status": op.operation.status,
                "tool": op.tool.id if op.tool else None, "tool_plain": op.tool.plain if op.tool else "",
                "tool_diameter_mm": op.tool.diameter_mm if op.tool else None,
                "rpm": op.feeds.rpm if op.feeds else None, "feed_mm_min": op.feeds.feed_mm_min if op.feeds else None,
                "plunge_mm_min": op.feeds.plunge_mm_min if op.feeds else None,
                "time_s": round(op.time_s, 2), "t0": round(op.t0, 3), "t1": round(op.t1, 3),
                "summary": op.summary + f", {_duration_words(op.time_s)}", "limits": list(op.operation.limits),
                "moves": op.end - op.start,
            }
            if op.spec.faces:
                row["faces"] = list(op.spec.faces)
            if op.spec.name:
                row["name"] = op.spec.name
            if op.feeds is not None and op.feeds.clamped:
                row["clamped"] = list(op.feeds.clamped)
            # Every plain fact an op recorded (levels, passes, depth, thread size, ...), for the agent and the row.
            facts = {k: v for k, v in op.meta.items() if k not in _NOT_FACTS and not k.startswith("_")
                     and (isinstance(v, (str, bool, int)) or (isinstance(v, float) and math.isfinite(v)))}
            if isinstance(op.meta.get("cut"), dict):
                facts["cut"] = op.meta["cut"]
            if facts:
                row["facts"] = facts
            ops.append(row)
        operations_out.extend(ops)
        setups_out.append({
            "id": plan.setup.id, "plain": plan.setup.plain, "index": plan.setup.index,
            "orientation": _orientation_out(plan.setup.orientation), "wcs": plan.setup.wcs,
            "fixtures": [{"name": box.name or f"fixture {k + 1}", "min_mm": [round(float(v), 4) for v in box.min_mm],
                          "max_mm": [round(float(v), 4) for v in box.max_mm]}
                         for k, box in enumerate(plan.setup.fixtures)],
            "origin_part_mm": plan.wcs.origin_part_mm, "matrix": plan.wcs.matrix(), "heights": plan.heights.as_dict(),
            "time_s": round(plan.time_s, 2), "t0": round(plan.t0, 3), "t1": round(plan.t0 + plan.time_s, 3),
            "post": next((_relative(path, glb_dir) for setup_id, _, path, _ in rendered if setup_id == plan.setup.id),
                         None),
            "posts": [_relative(path, glb_dir) for setup_id, _, path, _ in rendered if setup_id == plan.setup.id],
            "operations": ops,
        })
    posts_out = [{"setup": setup_id, "file": str(path), "post": post.name, "tool": label}
                 for setup_id, label, path, _ in rendered]
    removed = removed_before - sim.volume()
    cam = {
        "schema": 1, "generator": "cadgen cam", "document": _relative(document, glb_dir),
        "occurrence": part.occurrence, "units": "mm", "verdict": verdict, "machine": machine.as_dict(),
        "material": parsed.material.name, "material_plain": parsed.material.plain, "stock": stock.as_dict(),
        "tools": [tools[t].as_dict() for t in sorted(tools, key=lambda t: tools[t].number)],
        "setups": setups_out, "findings": findings, "adapted": adapted,
        "posts": [{"setup": p["setup"], "file": _relative(Path(p["file"]), glb_dir), "post": p["post"],
                   "tool": p["tool"]} for p in posts_out],
        "duration_s": round(duration, 3), "removed_mm3": round(removed, 2),
        "checks": {"ran": ran, "skipped": skipped}, "tool_changes": changes, "warnings": list(warnings),
        "assumed": [dict(entry) for entry in parsed.assumed],
        "safety": "Generated by cadgen; not proven on a machine. Air-cut or single-block it first, and check the work "
                  "offset and every tool length.",
    }
    # Lines for the GLB, in part coordinates on the program clock.
    def segments_at(chord: float) -> int:
        return sum(len(plan.toolpath.sample(chord).points) for plan in setup_plans)

    chord, stride, steps = fit.display_chord(segments_at, tolerance, budget)
    adapted += steps
    cam["adapted"] = adapted
    lines = []
    for plan in setup_plans:
        samples = plan.toolpath.sample(chord, machine=machine)
        thickness = plan.heights.stock_top - plan.heights.stock_bottom if machine.kind == "wire_edm" else None
        axes = sample_axes(plan.toolpath, plan.wcs, samples.move, thickness_mm=thickness)
        samples = dataclasses.replace(samples, points=plan.wcs.from_wcs(samples.points))
        lines += line_segments(samples, setup=plan.setup.id, t_offset=plan.t0, stride=stride, axes=axes)

    # Every file to a temporary name first, then each renamed into place; a failure anywhere removes the temporaries
    # and whatever of the new set was already in place (the old set went before planning), so nothing half-written
    # or stale stands at the names.
    temporaries = []
    placed = []
    try:
        suffix = f".tmp-{os.getpid()}"
        glb_tmp = glb_path.with_name(f".{glb_path.name}{suffix}")
        temporaries.append((glb_tmp, glb_path))
        write_glb(glb_tmp, part_mesh=(part.vertices, part.triangles), stock_mesh=sim.mesh(), lines=lines, cam=cam,
                  name=f"{document.stem} cam")
        for _, _, final, text in rendered:
            tmp = final.with_name(f".{final.name}{suffix}")
            temporaries.append((tmp, final))
            tmp.write_text(text, encoding="utf-8", newline="\n")
        for tmp, final in temporaries:
            replace_atomic(tmp, final)
            placed.append(final)
    except BaseException:
        _remove_stale([tmp for tmp, _ in temporaries] + placed)
        raise
    lap("write_s", mark)
    timings["total_s"] = round(time.perf_counter() - started, 4)
    logger.debug(f"planned in {timings['total_s']:.2f} s")
    summary = {"duration_s": round(duration, 2), "tools": used_tools, "tool_changes": changes,
               "setups": len(setup_plans),
               "operations": len(op_plans), "machine": machine.kind, "post": post.name,
               "material": parsed.material.name, "stock_cell_mm": round(cell, 4), "removed_mm3": round(removed, 2),
               "checks_ran": ran, "checks_skipped": skipped}
    return CamPlanResult(ok=True, document=document, glb=glb_path, posts=tuple(posts_out), verdict=verdict,
                         assumed=tuple(dict(entry) for entry in parsed.assumed),
                         summary=summary, operations=tuple(operations_out), findings=tuple(findings),
                         adapted=tuple(adapted), warnings=tuple(warnings), timings=timings)


def _orientation_out(orientation):
    """A setup's orientation as the job wrote it: an axis word, a tilt, or a face's selector."""
    from cadgen._internal.cam.wcs import FaceOrientation

    return orientation.ref if isinstance(orientation, FaceOrientation) else orientation


def _render_setup(post, plan, k, setup_plans, op_plans, tools, machine, document, parsed, tolerance, lite, by_index,
                  split, folder, extension) -> list:
    """One setup's posted files: ``[(setup id, tool label or None, final path, text)]``."""
    from cadgen import __version__
    from cadgen._internal.cam.posts.base import Program

    notes = tuple(f"lite {entry['op']}: {limit}" for entry in lite for limit in entry["limits"]
                  if by_index[entry["operation"]].setup == plan.setup.id)
    # What the program rests on that nobody stated (the dialect, the spindle limit, the tapping) is said where the
    # operator reads it, not only in the plan's report; what only shapes the cycle time is not.
    stated_not = [f"{entry['key'][len('machine.'):]} {_assumed_value(entry['value'])}" for entry in parsed.assumed
                  if entry["key"].startswith("machine.") and entry["key"] not in _CYCLE_TIME_KEYS]
    if stated_not:
        notes = (f"Assumed, not stated: {', '.join(stated_not)}. Check them against the machine before running.",
                 ) + tuple(f"Spindle {entry['value']}: {entry['why']}." for entry in parsed.assumed
                           if entry["key"] == "machine.spindle") + notes
    program = Program(setup=plan.setup, wcs=plan.wcs, toolpath=plan.toolpath, tools=tools, machine=machine,
                      version=__version__, part=document.name, job_name=parsed.name,
                      material=parsed.material.plain, tolerance_mm=tolerance, clearance_z=plan.heights.clearance,
                      retract_z=plan.heights.retract, setup_index=k, setup_count=len(setup_plans), notes=notes)
    setup_tools = {op.tool.id for op in op_plans if op.setup == plan.setup.id and op.tool is not None}
    if split and len(setup_tools) > 1:
        # One file per tool (GRBL cannot re-zero a tool after M0): <stem>.<setup>.<label><ext>, in program order.
        out = []
        for label, text in post.render_tool_files(program):
            if not isinstance(label, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,40}", label):
                raise ValueError(f"post {post.name} labelled a tool file {label!r}; a label is letters, digits, - or _")
            out.append((plan.setup.id, label, folder / f"{document.stem}.{plan.setup.id}.{label}{extension}", text))
        return out
    return [(plan.setup.id, None, folder / f"{document.stem}.{plan.setup.id}{extension}", post.render(program))]


def post_refusal_finding(exc: PostRefusal, post, op_plans) -> dict:
    """The ``no_post_support`` error of a post that cannot write what the job needs, on its operation."""
    op = next((op for op in op_plans if op.index == exc.operation), None)
    items = [{"setup": op.setup, "operation": op.index}] if op is not None else []
    where = f"operation {op.index + 1} ({op.summary}, setup {op.setup}): " if op is not None else ""
    return finding("post", "error", "no_post_support", f"{where}{exc}",
                   f"the {post.name} post cannot write this, so no G-code was written; the plan and its toolpaths "
                   "stand. Change the post (machine.post) to one whose controller can, or the operation",
                   items)


def parse_operations(parsed) -> dict:
    """Every operation's class and parsed params, by ``(setup id, index)``; refuses before anything heavy runs."""
    from cadgen._internal.cam.operations import get_operation
    from cadgen._internal.cam.operations.base import ParseContext

    operations = {}
    for setup in parsed.setups:
        for spec in setup.operations:
            operation = get_operation(spec.op, spec.where)
            operations[(setup.id, spec.index)] = (operation, operation.parse(spec, ParseContext(parsed, setup)))
    return operations


def plan_setups(parsed, operations, part, stock, logger=None):
    """Plan every setup: ``(setup plans, op plans, warnings)``. Each setup plan carries its WCS toolpath with the
    setup, tool, spindle and coolant events and one op range per operation; op plans carry their feeds, meta and
    summary (times are filled in by the caller)."""
    from cadgen._internal.cam.checks.base import OpPlan, SetupPlan
    from cadgen._internal.cam.geom2d import Sections
    from cadgen._internal.cam.ir import MAX_MOVES, Event, OpRange, Toolpath, ToolpathBuilder, concat
    from cadgen._internal.cam.job_errors import PlanTooBig
    from cadgen._internal.cam.linking import Heights
    from cadgen._internal.cam.multiaxis import hold_rotary
    from cadgen._internal.cam.operations.base import PlanContext
    from cadgen._internal.cam.wcs import build_wcs, with_face_orientations
    from cadgen._internal.cam.workholding import holding_boxes

    logger = logger or CliLogger("cam")
    # A setup turned onto a face reads that face's normal from the part (every setup, so an operation that names
    # another setup's tool axis reads it too).
    parsed = with_face_orientations(parsed, part)
    machine = parsed.machine
    tools = {tool.id: tool for tool in parsed.tools}
    tolerance = parsed.tolerance_mm
    warnings: list[str] = []
    setup_plans: list[SetupPlan] = []
    op_plans: list[OpPlan] = []
    history: list = []          # (wcs, toolpath) per operation planned so far, for PlanContext.history
    index = 0
    for setup in parsed.setups:
        wcs = build_wcs(setup, stock_points=stock.vertices, part_points=part.vertices, machine=machine)
        # A vise or a plate is built around the stock in this setup's frame: its boxes join the job's own.
        held, assumed = holding_boxes(setup, wcs, stock.vertices)
        if held:
            setup = dataclasses.replace(setup, fixtures=setup.fixtures + held)
        part_w = wcs.to_wcs(part.vertices)
        stock_w = wcs.to_wcs(stock.vertices)
        top = float(stock_w[:, 2].max())
        heights = Heights(clearance=top + setup.clearance_mm, retract=top + setup.retract_mm, stock_top=top,
                          part_top=float(part_w[:, 2].max()), stock_bottom=float(stock_w[:, 2].min()),
                          part_bottom=float(part_w[:, 2].min()))
        sections = Sections(part_w, part.triangles)
        plan = SetupPlan(setup=setup, wcs=wcs, heights=heights, sections=sections, fixture_assumed=assumed)
        position = (0.0, 0.0, heights.clearance)
        pieces = []
        current = {"tool": None, "rpm": None, "coolant": "off"}
        for spec in setup.operations:
            operation, params = operations[(setup.id, spec.index)]

            tool = tools.get(spec.tool) if spec.tool else None
            # An operation may set its own clearance and retract over the stock top (spec.clearance_mm,
            # spec.retract_mm); it still ends at or above the setup's clearance, below.
            op_heights = heights
            if spec.clearance_mm is not None or spec.retract_mm is not None:
                clearance = spec.clearance_mm if spec.clearance_mm is not None else setup.clearance_mm
                retract = spec.retract_mm if spec.retract_mm is not None else setup.retract_mm
                op_heights = dataclasses.replace(heights, clearance=top + clearance, retract=top + retract)
            ctx = PlanContext(job=parsed, setup=setup, wcs=wcs, heights=op_heights, part=part, stock=stock,
                              sections=sections, spec=spec, index=index, tool=tool, start=position,
                              tolerance_mm=tolerance, log=logger.debug, history=list(history))
            with logger.timed(f"plan {setup.id} {spec.index + 1}. {spec.op}"):
                try:
                    path = operation.plan(ctx, params)
                except PlanTooBig as exc:
                    raise CamJobError(f"{spec.where} ({operation.plain}{f' with {tool.id}' if tool else ''}) is too "
                                      f"big to plan: {exc}") from None
                except PlanError as exc:
                    # This operation cannot be planned on this part (a tool too big for its pocket, a hole not
                    # reached from here): an error finding on it, no moves, and every other operation still planned,
                    # so one run lists every refusal. Nothing is posted while it stands.
                    ctx.meta = {"plan_error": {"kind": exc.kind, "message": str(exc)}}
                    ctx.chosen_feeds = []
                    path = ToolpathBuilder(position, op=index).build()
            if len(path.moves) > MAX_MOVES:
                raise CamJobError(f"{spec.where} ({operation.plain}{f' with {tool.id}' if tool else ''}) is too big "
                                  f"to plan: it needs {len(path.moves):,} moves, more than {MAX_MOVES:,}; use a bigger "
                                  "tool, a larger stepover or stepdown, or a smaller region")
            path = path.with_op(index)
            events = []
            feeds = ctx.chosen_feeds[0] if ctx.chosen_feeds else None
            failed = "plan_error" in ctx.meta
            if tool is not None and tool.id != current["tool"] and not failed:
                events.append(("tool", {"tool": tool.id, "number": tool.number, "plain": tool.plain}))
                current["tool"], current["rpm"] = tool.id, None
            # An op may run the spindle the other way (a left-hand tap): ctx.meta["spindle_dir"] = "ccw".
            direction = ctx.meta.get("spindle_dir", "cw")
            if feeds is not None and machine.kind not in ("laser", "plasma", "waterjet", "wire_edm") \
                    and (feeds.rpm != current["rpm"] or direction != current.get("dir", "cw")):
                spindle = {"rpm": feeds.rpm, "dir": direction}
                if getattr(feeds, "feed_mm_rev", None):
                    # A lathe op (feeds.for_turn): feed per revolution, and constant surface speed under a clamp.
                    spindle["feed_per_rev"] = True
                    if feeds.css_m_min:
                        spindle.update(css_m_min=feeds.css_m_min, max_rpm=feeds.max_rpm)
                events.append(("spindle", spindle))
                current["rpm"], current["dir"] = feeds.rpm, direction
            coolant = spec.coolant or parsed.coolant
            if coolant != current["coolant"] and not failed:
                events.append(("coolant", {"mode": coolant}))
                current["coolant"] = coolant
            # Every operation ends at the clearance height, so the next one starts safe.
            tail = ToolpathBuilder(path.positions()[-1], op=index)
            if tail.pos[2] < heights.clearance - 1e-9:
                tail.rapid(z=heights.clearance)
            tail_path = tail.build()
            # Every move carries the setup's rotary position (3+2), or holds a continuous op's last one.
            joined = hold_rotary(path, tail_path, wcs)
            wrapped = Toolpath(joined.moves, [Event(0, kind, data) for kind, data in events] + list(joined.events),
                               [OpRange(index, setup.id, spec.op, operation.plain, spec.tool, 0, len(joined.moves),
                                        dict(ctx.meta))], start=position, rotary=joined.rotary, lathe=joined.lathe)
            pieces.append(wrapped)
            history.append((wcs, wrapped))
            position = tuple(float(v) for v in wrapped.positions()[-1])
            summary = (f"{operation.plain}{f' with {tool.id}' if tool else ''}" if failed
                       else operation.summary(ctx, params))
            op_plans.append(OpPlan(index=index, setup=setup.id, spec=spec, operation=operation, tool=tool, feeds=feeds,
                                   params=params, meta=dict(ctx.meta), summary=summary))
            index += 1
        joined = concat(pieces, start=(0.0, 0.0, heights.clearance))
        end_events = [Event(len(joined.moves), "coolant", {"mode": "off"})] if current["coolant"] != "off" else []
        plan.toolpath = Toolpath(joined.moves, [Event(0, "setup", {"id": setup.id, "wcs": setup.wcs,
                                                                     "plain": setup.plain,
                                                                     "rotary": dict(wcs.rotary_deg)})]
                                 + list(joined.events) + end_events, joined.ops, start=joined.start,
                                 rotary=joined.rotary, lathe=joined.lathe)
        if sections.open_pieces:
            warnings.append(f"setup {setup.id}: {sections.open_pieces} part section(s) did not close; the part's "
                            "tessellation may have a crack there")
        setup_plans.append(plan)
    return setup_plans, op_plans, warnings
