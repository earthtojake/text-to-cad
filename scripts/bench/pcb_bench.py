#!/usr/bin/env python3
"""PCB tasks on the fetched corpus: a run folder for an agent, and a verdict on what it left there.

A manual benchmark, never run in CI (``AGENTS.md``). ``pcb_tasks.json`` names each task: the corpus project
it starts from (``pcb_corpus.json``, fetched by ``pcb_fetch.py``), the prompt a person would write, the
faults seeded into the project before the run (``mutations``), the checks the result is graded by, and the
reference fix that proves those checks (``reference``). Launching an agent is not this script's: a person or
a harness hands it the run folder and its ``PROMPT.md``.

    .venv/bin/python scripts/bench/pcb_bench.py tasks                      # the task file, checked; no KiCad
    .venv/bin/python scripts/bench/pcb_bench.py prepare --task ecc83-reconnect --runs 2
    .venv/bin/python scripts/bench/pcb_bench.py check tmp/pcb-bench/runs/<run>      # a JSON verdict
    .venv/bin/python scripts/bench/pcb_bench.py selftest                   # every task: fails seeded, passes fixed

``prepare`` copies the fetched project into ``<out>/<run>/`` (an opaque name), applies the task's
mutations and writes ``PROMPT.md``; what the grader needs (the task, the corpus folder, every file's hash as
prepared) goes in ``<out>/<run>.json`` beside it, never inside. ``check`` reads the run folder's files with
the library (``cad.kicad_pcb.read``, ``cad.kicad_sch.read``) and runs KiCad's DRC and ERC on them and on the
untouched corpus project, in a ``cad[kicad]`` environment of the bench's own (``tmp/pcb-bench/.runtime``),
never the person's engine or installation. See ``README.md``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from collections import Counter
from pathlib import Path
from typing import Any, Callable, Iterable

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pcb_fetch  # noqa: E402  (this folder's, beside it)

ROOT = pcb_fetch.ROOT
TASKS = Path(__file__).with_name("pcb_tasks.json")
CORPUS = pcb_fetch.OUT
RUNS = ROOT / "tmp" / "pcb-bench" / "runs"
RUNTIME = ROOT / "tmp" / "pcb-bench" / ".runtime"
KINDS = ("fix_drc", "fix_erc", "renet", "move_part", "route_net", "review", "build_edit")
TASK_KEYS = frozenset({"id", "project", "kind", "prompt", "mutations", "checks", "reference", "rebuild", "proof"})
MUTATIONS = {"delete": {"file", "uuids"}, "strip_net": {"file", "net"}, "edit": {"file", "uuid", "from", "to"},
             "move_part": {"file", "ref", "at"}, "replace_all": {"file", "from", "to"}, "restore": {"file"},
             "write": {"file", "text"}, "refill": {"file"}}
REQUIRED_OP_KEYS = {**MUTATIONS, "edit": {"file", "from", "to"}}  # an edit's uuid is optional: the whole file
# A reference fix's KiCad step: the board's pours filled again and saved, by KiCad (its IPC API, in an edit).
REFILL = "import sys\nfrom cad import kicad_pcb\nwith kicad_pcb.edit(sys.argv[1]) as board:\n    board.refill_zones()\n"
CHECKS = {
    "drc_no_worse": {"ignore"}, "drc_none": {"type", "net", "ref"}, "connectivity_same": {"rename"},
    "parts_unmoved": {"except", "tolerance"}, "part_at": {"ref", "at", "tolerance"}, "net_routed": {"net"},
    "board_net_named": {"net", "was"}, "erc_no_worse": {"ignore"}, "erc_none": {"code", "message"},
    "sch_nets_same": {"rename"}, "sch_net_named": {"net", "was"}, "files_unchanged": {"except"},
    "review_names": {"file", "faults"}, "parts_on_circle": {"refs", "centre", "radius", "tolerance"},
}
REQUIRED_CHECK_KEYS = {"drc_none": set(), "part_at": {"ref", "at"}, "net_routed": {"net"},
                       "board_net_named": {"net", "was"}, "sch_net_named": {"net", "was"},
                       "review_names": {"file", "faults"}, "parts_on_circle": {"refs", "centre", "radius"}}
PROMPT = "PROMPT.md"
# KiCad and the tools leave these beside a project they open: never a change the agent made.
LOCAL = re.compile(r"(^|/)(fp-info-cache|[^/]*\.kicad_prl|[^/]*\.lck|[^/]*-backups(/.*)?|\.history(/.*)?"
                   r"|__pycache__(/.*)?)$")


# --- the S-expression edits ---------------------------------------------------------------------

_TOKEN = re.compile(r'[()"\\]')


def lists(text: str, start: int = 0, end: int | None = None) -> list[tuple[int, int]]:
    """The spans ``[open, close]`` of the lists directly inside the list that opens at ``start`` (the whole
    file's root list by default): ``text[open] == "("`` and ``text[close] == ")"``. Strings, with their
    escapes, are skipped, so a parenthesis inside one is text."""
    end = len(text) if end is None else end
    depth, in_string, skip, opened, found = 0, False, -1, -1, []
    for match in _TOKEN.finditer(text, start, end):
        char, at = match.group(), match.start()
        if at < skip:  # the character a backslash escapes
            continue
        if in_string:
            if char == "\\":
                skip = at + 2
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "(":
            depth += 1
            if depth == 2:
                opened = at
        elif char == ")":
            if depth == 2:
                found.append((opened, at))
            depth -= 1
            if depth == 0:
                break
    return found


def head(text: str, span: tuple[int, int]) -> str:
    match = re.match(r"\(\s*([^\s()\"]+)", text[span[0]:span[1] + 1])
    return match.group(1) if match else ""


def own_id(text: str, span: tuple[int, int]) -> str | None:
    """The item's own uuid (``(uuid "...")``, or a KiCad 6 file's ``(tstamp ...)``), not a child's."""
    for child in lists(text, span[0], span[1] + 1):
        match = re.fullmatch(r'\(\s*(?:uuid|tstamp)\s+"?([0-9A-Fa-f-]+)"?\s*\)', text[child[0]:child[1] + 1])
        if match:
            return match.group(1).lower()
    return None


def item(text: str, uuid: str) -> tuple[int, int]:
    """The span of the one top-level item whose own id is ``uuid``; anything else is an error."""
    found = [span for span in lists(text) if own_id(text, span) == uuid.lower()]
    if len(found) != 1:
        raise ValueError(f"expected one top-level item with uuid {uuid}; found {len(found)}")
    return found[0]


def footprint(text: str, ref: str) -> tuple[int, int]:
    """The span of the footprint whose reference is ``ref`` (KiCad 8's property, KiCad 6 and 7's fp_text)."""
    pattern = re.compile(r'\(\s*(?:property\s+"Reference"|fp_text\s+reference)\s+"?' + re.escape(ref) + r'"?[\s)]')
    found = []
    for span in lists(text):
        if head(text, span) != "footprint":
            continue
        for child in lists(text, span[0], span[1] + 1):
            if pattern.match(text, child[0]):
                found.append(span)
                break
    if len(found) != 1:
        raise ValueError(f"expected one footprint {ref}; found {len(found)}")
    return found[0]


def strip_net(text: str, net: str) -> str:
    """The board without a net's copper: every top-level track, arc and via on ``net`` removed (by name in
    KiCad 10's files, by the net table's number in older ones). Its pads and pours stay."""
    numbers = set()
    for span in lists(text):
        if head(text, span) == "net":
            match = re.fullmatch(r'\(\s*net\s+(\d+)\s+"((?:[^"\\]|\\.)*)"\s*\)', text[span[0]:span[1] + 1])
            if match and match.group(2) == net:
                numbers.add(match.group(1))
    wanted = {f'(net "{net}")', *(f"(net {number})" for number in numbers)}
    doomed = []
    for span in lists(text):
        if head(text, span) not in ("segment", "arc", "via"):
            continue
        for child in lists(text, span[0], span[1] + 1):
            if re.sub(r"\s+", " ", text[child[0]:child[1] + 1]) in wanted:
                doomed.append(span)
                break
    if not doomed:
        raise ValueError(f"no track, arc or via on net {net!r}")
    for start, end in reversed(doomed):
        line_start = text.rfind("\n", 0, start) + 1
        if text[line_start:start].strip() == "" and text[end + 1:].split("\n", 1)[0].strip() == "":
            newline = text.find("\n", end)
            start, end = line_start, (newline if newline != -1 else len(text) - 1)
        text = text[:start] + text[end + 1:]
    return text


def _once(text: str, old: str, new: str, where: str) -> str:
    count = text.count(old)
    if count != 1:
        raise ValueError(f"{old!r} occurs {count} times in {where}, not once")
    return text.replace(old, new)


def mutate(text: str, op: dict[str, Any]) -> str:
    """``text`` with one text-level edit applied (``delete``, ``edit``, ``move_part``, ``replace_all``)."""
    kind = op["op"]
    if kind == "delete":
        for uuid in op["uuids"]:
            start, end = item(text, uuid)
            line_start = text.rfind("\n", 0, start) + 1
            if text[line_start:start].strip() == "" and text[end + 1:].split("\n", 1)[0].strip() == "":
                newline = text.find("\n", end)
                start, end = line_start, (newline if newline != -1 else len(text) - 1)
            text = text[:start] + text[end + 1:]
        return text
    if kind == "strip_net":
        return strip_net(text, op["net"])
    if kind == "edit":
        if op.get("uuid"):
            start, end = item(text, op["uuid"])
            return text[:start] + _once(text[start:end + 1], op["from"], op["to"], f"item {op['uuid']}") + text[end + 1:]
        return _once(text, op["from"], op["to"], op["file"])
    if kind == "move_part":
        start, end = footprint(text, op["ref"])
        for child in lists(text, start, end + 1):
            if head(text, child) == "at":
                x, y = (f"{value:g}" for value in op["at"])
                parts = text[child[0] + 1:child[1]].split()
                moved = "(" + " ".join(["at", x, y, *parts[3:]]) + ")"
                return text[:child[0]] + moved + text[child[1] + 1:]
        raise ValueError(f"footprint {op['ref']} has no (at ...)")
    if kind == "replace_all":
        if op["from"] not in text:
            raise ValueError(f"{op['from']!r} does not occur in {op['file']}")
        return text.replace(op["from"], op["to"])
    raise ValueError(f"no text edit {kind!r}")


def apply(folder: Path, ops: Iterable[dict[str, Any]], pristine: Path | None = None, python: str | None = None) -> None:
    """Each op on the file it names inside ``folder``; ``restore`` takes the file from ``pristine``, and
    ``refill`` has KiCad (``python``, the ``cad[kicad]`` environment's) fill the board's pours again."""
    for op in ops:
        target = pcb_fetch.inside(folder, op["file"])
        if op["op"] == "refill":
            if python is None:
                raise ValueError("refill needs the cad[kicad] environment's Python")
            done = subprocess.run([python, "-c", REFILL, str(target)], capture_output=True, text=True)
            if done.returncode:
                raise RuntimeError(f"the refill of {op['file']} failed: {done.stderr[-600:]}")
        elif op["op"] == "restore":
            if pristine is None:
                raise ValueError("restore needs the corpus project")
            shutil.copyfile(pcb_fetch.inside(pristine, op["file"]), target)
        elif op["op"] == "write":
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(op["text"], encoding="utf-8")
        else:
            text = target.read_text(encoding="utf-8")
            target.write_text(mutate(text, op), encoding="utf-8", newline="")


# --- the task file ------------------------------------------------------------------------------


def _op_problems(op: Any, where: str, files: set[str] | None) -> list[str]:
    if not isinstance(op, dict) or op.get("op") not in MUTATIONS:
        return [f"{where}: an op is one of {', '.join(MUTATIONS)}"]
    kind = op["op"]
    found = [f"{where}: {kind} takes no `{key}`" for key in sorted(set(op) - MUTATIONS[kind] - {"op"})]
    found += [f"{where}: {kind} needs `{key}`" for key in sorted(REQUIRED_OP_KEYS[kind] - set(op))]
    if not pcb_fetch.safe_path(op.get("file")):
        found.append(f"{where}: `file` is a safe relative path in the project")
    elif files is not None and kind not in ("write",) and op["file"] not in files:
        found.append(f"{where}: no file {op['file']} in the project")
    if kind == "delete" and not (isinstance(op.get("uuids"), list) and op["uuids"]
                                 and all(isinstance(u, str) and re.fullmatch(r"[0-9a-fA-F-]{8,}", u) for u in op["uuids"])):
        found.append(f"{where}: delete's `uuids` lists the items' uuids")
    if kind == "move_part" and not (isinstance(op.get("at"), list) and len(op["at"]) == 2
                                    and all(isinstance(v, (int, float)) for v in op["at"])):
        found.append(f"{where}: move_part's `at` is [x, y] in millimetres")
    if kind in ("edit", "replace_all") and op.get("from") == op.get("to"):
        found.append(f"{where}: `from` and `to` are the same")
    return found


def _check_problems(check: Any, where: str) -> list[str]:
    if not isinstance(check, dict) or check.get("check") not in CHECKS:
        return [f"{where}: a check is one of {', '.join(CHECKS)}"]
    name = check["check"]
    found = [f"{where}: {name} takes no `{key}`" for key in sorted(set(check) - CHECKS[name] - {"check", "file"})]
    found += [f"{where}: {name} needs `{key}`" for key in sorted(REQUIRED_CHECK_KEYS.get(name, set()) - set(check))]
    if name == "review_names":
        faults = check.get("faults")
        if not (isinstance(faults, list) and faults and all(
                isinstance(f, dict) and isinstance(f.get("id"), str) and isinstance(f.get("any"), list) and f["any"]
                for f in faults)):
            found.append(f"{where}: review_names' `faults` are {{id, any: [pattern, ...]}}")
        else:
            for fault in faults:
                for pattern in fault["any"]:
                    try:
                        re.compile(pattern)
                    except re.error as error:
                        found.append(f"{where}: fault {fault['id']}'s pattern {pattern!r}: {error}")
    return found


def task_problems(tasks: Any, manifest: dict[str, Any]) -> list[str]:
    """Everything wrong with a task file against the corpus manifest, each as a line."""
    if not isinstance(tasks, dict) or not isinstance(tasks.get("tasks"), list):
        return ["the task file is {about, tasks: [...]}"]
    projects = {project["name"]: project for project in manifest.get("projects", [])}
    found: list[str] = []
    ids: set[str] = set()
    for task in tasks["tasks"]:
        if not isinstance(task, dict):
            found.append("a task is an object")
            continue
        tid = str(task.get("id"))
        if not pcb_fetch.NAME.fullmatch(tid):
            found.append(f"{tid!r}: `id` is lowercase letters, digits, `_`, `.` and `-`")
        elif tid in ids:
            found.append(f"{tid}: a second task of this id")
        ids.add(tid)
        found += [f"{tid}: unknown key `{key}`" for key in sorted(set(task) - TASK_KEYS)]
        found += [f"{tid}: no `{key}`" for key in ("project", "kind", "prompt", "checks", "reference", "proof")
                  if key not in task]
        if task.get("kind") not in KINDS:
            found.append(f"{tid}: `kind` is one of {', '.join(KINDS)}")
        project = projects.get(task.get("project"))
        if project is None:
            found.append(f"{tid}: no project {task.get('project')!r} in the corpus")
        files = ({entry["path"] for entry in project["files"]} if project and project["kind"] == "upstream" else None)
        prompt = task.get("prompt")
        if not isinstance(prompt, str) or len(prompt.strip()) < 20:
            found.append(f"{tid}: `prompt` is what a person would ask")
        elif re.search(r"bench|evaluat|grader|graded|\btest(ing)? (you|the agent)", prompt, re.IGNORECASE):
            found.append(f"{tid}: the prompt speaks of a benchmark; write it as a person's request")
        for index, op in enumerate(task.get("mutations") or []):
            found += _op_problems(op, f"{tid} mutation {index + 1}", files)
        reference = task.get("reference")
        if not isinstance(reference, list) or not reference:
            found.append(f"{tid}: `reference` is the fix that proves the checks, as ops")
        else:
            for index, op in enumerate(reference):
                found += _op_problems(op, f"{tid} reference {index + 1}", None)
        checks = task.get("checks")
        if not isinstance(checks, list) or not checks:
            found.append(f"{tid}: `checks` grade the result")
        else:
            for index, check in enumerate(checks):
                found += _check_problems(check, f"{tid} check {index + 1}")
        if task.get("rebuild") and (project is None or project["kind"] != "build"):
            found.append(f"{tid}: only a build project is rebuilt")
        if task.get("kind") == "build_edit" and not task.get("rebuild"):
            found.append(f"{tid}: a build_edit task is graded on a rebuild (`rebuild`: true)")
        if not isinstance(task.get("proof"), str) or not task.get("proof"):
            found.append(f"{tid}: `proof` says how the checks were shown to fail seeded and pass fixed")
    return found


# --- the facts a check reads ---------------------------------------------------------------------


def drc_counts(findings: list[dict[str, Any]], ignore: Iterable[str] = ()) -> Counter:
    """What fails a board, counted by kind: each error-severity violation's type, and ``unconnected``."""
    skip = set(ignore)
    counted: Counter = Counter()
    for finding in findings:
        if finding.get("type") in skip:
            continue
        if finding.get("check") == "unconnected":
            counted["unconnected"] += 1
        elif finding.get("severity") == "error":
            counted[finding.get("type", "")] += 1
    return counted


def erc_counts(findings: list[dict[str, Any]], ignore: Iterable[str] = ()) -> Counter:
    """ERC errors and warnings, counted by severity and code (``error/pin_not_connected``)."""
    skip = set(ignore)
    return Counter(f"{f.get('severity')}/{f.get('code')}" for f in findings
                   if f.get("severity") in ("error", "warning") and f.get("code") not in skip)


def worse(after: Counter, before: Counter) -> dict[str, list[int]]:
    """Each kind that counts more after than before: ``{kind: [before, after]}``."""
    return {kind: [before.get(kind, 0), count] for kind, count in sorted(after.items()) if count > before.get(kind, 0)}


def matching(findings: list[dict[str, Any]], type_: str | None, net: str | None, ref: str | None) -> list[dict[str, Any]]:
    """The failing DRC findings (errors and unconnected items) of that type, with an item on that net or
    that part."""
    found = []
    for finding in findings:
        if finding.get("severity") != "error" and finding.get("check") != "unconnected":
            continue
        if type_ and finding.get("type") != type_:
            continue
        items = finding.get("items") or []
        if net and not any(item.get("net") == net for item in items):
            continue
        if ref and not any(item.get("part") == ref or str(item.get("ref", "")).lstrip("#").split(".")[0] == ref
                           for item in items):
            continue
        found.append(finding)
    return found


def renamed(name: str | None, rename: dict[str, str]) -> str | None:
    return rename.get(name, name) if name is not None else None


def partition(nets: dict[str, Iterable[str]]) -> set[frozenset[str]]:
    """Nets as sets of pins, names aside (a net of no pin is no connection)."""
    return {frozenset(pins) for pins in nets.values() if pins}


def review_found(text: str, faults: list[dict[str, Any]]) -> dict[str, bool]:
    """Which seeded faults a review names: a fault is named when any of its patterns occurs (any case)."""
    return {fault["id"]: any(re.search(pattern, text, re.IGNORECASE) for pattern in fault["any"]) for fault in faults}


def evaluate(check: dict[str, Any], facts: "Facts") -> tuple[bool, Any]:
    """One check against the facts of a result and of its untouched corpus project: (passed, detail)."""
    name = check["check"]
    if name == "drc_no_worse":
        ignore = check.get("ignore", ())
        grown = worse(drc_counts(facts.drc(), ignore), drc_counts(facts.drc(pristine=True), ignore))
        return not grown, grown or "no failing kind counts more than the original board's"
    if name == "drc_none":
        left = matching(facts.drc(), check.get("type"), check.get("net"), check.get("ref"))
        return not left, [f.get("description") for f in left[:5]] or "none left"
    if name == "erc_no_worse":
        ignore = check.get("ignore", ())
        grown = worse(erc_counts(facts.erc(), ignore), erc_counts(facts.erc(pristine=True), ignore))
        return not grown, grown or "no error or warning kind counts more than the original schematic's"
    if name == "erc_none":
        left = [f for f in facts.erc() if f.get("severity") in ("error", "warning")
                and (not check.get("code") or f.get("code") == check["code"])
                and (not check.get("message") or re.search(check["message"], f.get("message", "")))]
        return not left, [f.get("message") for f in left[:5]] or "none left"
    if name == "connectivity_same":
        rename = check.get("rename", {})
        before = {pad: renamed(net, rename) for pad, net in facts.pads(pristine=True).items()}
        after = facts.pads()
        changed = sorted(f"{pad[0]}.{pad[1]}: {before.get(pad)} -> {after.get(pad)}"
                         for pad in set(before) | set(after) if before.get(pad) != after.get(pad))
        return not changed, changed[:10] or f"{len(after)} pads on their original nets"
    if name == "parts_unmoved":
        tolerance = check.get("tolerance", 0.01)
        before, after = facts.parts(pristine=True), facts.parts()
        moved = sorted(ref for ref, (x, y, rotation, side) in before.items()
                       if ref not in check.get("except", []) and (
                           ref not in after or abs(after[ref][0] - x) > tolerance or abs(after[ref][1] - y) > tolerance
                           or abs((after[ref][2] - rotation + 180) % 360 - 180) > 0.01 or after[ref][3] != side))
        return not moved, moved[:10] or f"{len(before)} parts where they were"
    if name == "part_at":
        tolerance = check.get("tolerance", 0.05)
        place = facts.parts().get(check["ref"])
        if place is None:
            return False, f"no part {check['ref']}"
        ok = abs(place[0] - check["at"][0]) <= tolerance and abs(place[1] - check["at"][1]) <= tolerance
        return ok, f"{check['ref']} at ({place[0]:g}, {place[1]:g})"
    if name == "parts_on_circle":
        tolerance = check.get("tolerance", 0.05)
        parts = facts.parts()
        cx, cy = check["centre"]
        off = {}
        for ref in check["refs"]:
            if ref not in parts:
                off[ref] = "missing"
                continue
            radius = ((parts[ref][0] - cx) ** 2 + (parts[ref][1] - cy) ** 2) ** 0.5
            if abs(radius - check["radius"]) > tolerance:
                off[ref] = round(radius, 3)
        return not off, dict(list(off.items())[:10]) or f"{len(check['refs'])} parts on r = {check['radius']:g}"
    if name == "net_routed":
        left = matching(facts.drc(), "unconnected_items", check["net"], None)
        copper = facts.copper_on(check["net"])
        return not left and copper > 0, f"{copper} tracks and vias on {check['net']}, {len(left)} unconnected"
    if name == "board_net_named":
        before = {pad for pad, net in facts.pads(pristine=True).items() if net == check["was"]}
        after_pads = facts.pads()
        now = {pad for pad, net in after_pads.items() if net == check["net"]}
        stale = {pad for pad, net in after_pads.items() if net == check["was"]}
        return bool(before) and now == before and not stale, (
            f"{len(now)} pads on {check['net']} (the {len(before)} of {check['was']}), {len(stale)} still on {check['was']}")
    if name == "sch_nets_same":
        rename = check.get("rename", {})
        before, after = facts.sch_nets(pristine=True), facts.sch_nets()
        same = partition(before) == partition(after)
        names = all(name in after for name in rename.values())
        return same and names, "the schematic's connections are the original's" if same else (
            f"{len(partition(before) ^ partition(after))} nets differ")
    if name == "sch_net_named":
        before = set(facts.sch_nets(pristine=True).get(check["was"], ()))
        after = facts.sch_nets()
        now = set(after.get(check["net"], ()))
        return bool(before) and now == before and check["was"] not in after, (
            f"{check['net']}: {len(now)} pins (the {len(before)} of {check['was']}); {check['was']} "
            + ("gone" if check["was"] not in after else "still there"))
    if name == "files_unchanged":
        changed = [path for path in facts.changed_files() if path not in check.get("except", [])]
        return not changed, changed[:10] or "every project file as prepared"
    if name == "review_names":
        text = facts.text(check["file"])
        if text is None:
            return False, f"no {check['file']}"
        named = review_found(text, check["faults"])
        return all(named.values()), named
    raise ValueError(f"no check {name!r}")


class Facts:
    """What the checks read, each read once: the result's and the untouched project's DRC, ERC, pads,
    parts and schematic nets. ``board`` and ``schematic`` are relative to both folders."""

    def __init__(self, result: Path, pristine: Path, board: str, schematic: str, prepared: dict[str, str],
                 kicad: Callable[[str, str, Path], dict[str, Any]]) -> None:
        self.result, self.pristine, self.board, self.schematic = result, pristine, board, schematic
        self.prepared, self.kicad, self._seen = prepared, kicad, {}

    def _once(self, key: tuple, make: Callable[[], Any]) -> Any:
        if key not in self._seen:
            self._seen[key] = make()
        return self._seen[key]

    def _folder(self, pristine: bool) -> Path:
        return self.pristine if pristine else self.result

    def drc(self, pristine: bool = False) -> list[dict[str, Any]]:
        path = self._folder(pristine) / self.board
        return self._once(("drc", pristine), lambda: self.kicad("kicad_pcb", "drc", path)["measurements"].get("drc", []))

    def erc(self, pristine: bool = False) -> list[dict[str, Any]]:
        path = self._folder(pristine) / self.schematic
        return self._once(("erc", pristine), lambda: self.kicad("kicad_sch", "erc", path)["findings"])

    def _board(self, pristine: bool):
        from cad import kicad_pcb

        return self._once(("board", pristine), lambda: kicad_pcb.read(self._folder(pristine) / self.board))

    def pads(self, pristine: bool = False) -> dict[tuple[str, str], str | None]:
        board = self._board(pristine)
        pads: dict[tuple[str, str], str | None] = {}
        for part in board.parts:
            for pad in part.pads:
                if pad.number:
                    pads[(part.ref, pad.number)] = pad.net
        return pads

    def parts(self, pristine: bool = False) -> dict[str, tuple[float, float, float, str]]:
        return {part.ref: (part.at[0], part.at[1], part.rotation, part.side) for part in self._board(pristine).parts}

    def copper_on(self, net: str) -> int:
        board = self._board(False)
        return sum(1 for track in board.tracks if track.net == net) + sum(1 for via in board.vias if via.net == net)

    def sch_nets(self, pristine: bool = False) -> dict[str, tuple[str, ...]]:
        from cad import kicad_sch

        def read() -> dict[str, tuple[str, ...]]:
            view = kicad_sch.read(self._folder(pristine) / self.schematic)
            return {net.name: tuple(sorted(f"{pin.ref}.{pin.number}" for pin in net.pins if not pin.ref.startswith("#")))
                    for net in view.nets}

        return self._once(("sch", pristine), read)

    def changed_files(self) -> list[str]:
        now = snapshot(self.result)
        return sorted(path for path in set(now) | set(self.prepared) if now.get(path) != self.prepared.get(path)
                      and path != PROMPT)

    def text(self, relative: str) -> str | None:
        path = self.result / relative
        return path.read_text(encoding="utf-8", errors="replace") if path.is_file() else None


def snapshot(folder: Path) -> dict[str, str]:
    """Every file under ``folder`` but KiCad's local leftovers, by its sha256."""
    found = {}
    for path in sorted(folder.rglob("*")):
        relative = path.relative_to(folder).as_posix()
        if path.is_file() and not LOCAL.search(relative):
            found[relative] = pcb_fetch.sha256(path)
    return found


# --- the runs ------------------------------------------------------------------------------------


def load() -> tuple[dict[str, Any], dict[str, Any]]:
    manifest = json.loads(pcb_fetch.MANIFEST.read_text(encoding="utf-8"))
    tasks = json.loads(TASKS.read_text(encoding="utf-8"))
    found = pcb_fetch.problems(manifest) + task_problems(tasks, manifest)
    if found:
        raise SystemExit("\n".join(f"pcb_bench: {line}" for line in found))
    return manifest, tasks


def run_name(task: str, run: str) -> str:
    """A run folder's name: opaque, so a path says nothing of the task."""
    return "w" + hashlib.sha256(f"{task}\0{run}".encode()).hexdigest()[:10]


def corpus_project(corpus: Path, project: dict[str, Any]) -> Path:
    folder = corpus / project["name"]
    if not (folder / project["board"]).is_file():
        raise SystemExit(f"pcb_bench: {project['name']} is not fetched: run pcb_fetch.py --project {project['name']}")
    if project["kind"] == "upstream":
        for entry in project["files"]:
            if not pcb_fetch.verified(pcb_fetch.inside(folder, entry["path"]), entry):
                raise SystemExit(f"pcb_bench: {folder / entry['path']} is not as fetched: fetch {project['name']} again")
    return folder


def copy_project(source: Path, target: Path) -> None:
    def ignored(folder: str, names: list[str]) -> set[str]:
        for name in names:
            if (Path(folder) / name).is_symlink():
                raise ValueError(f"refuses symlink {Path(folder) / name}")
        return {name for name in names if name in (".runtime", ".built-from")}

    shutil.copytree(source, target, ignore=ignored)


def prepare(task: dict[str, Any], project: dict[str, Any], corpus: Path, out: Path, run: str) -> Path:
    pristine = corpus_project(corpus, project)
    name = run_name(task["id"], run)
    folder = out / name
    if folder.exists() or (out / f"{name}.json").exists():
        raise SystemExit(f"pcb_bench: {folder} exists; a run folder is made once")
    copy_project(pristine, folder)
    apply(folder, task.get("mutations") or [], pristine)
    (folder / PROMPT).write_text(task["prompt"].strip() + "\n", encoding="utf-8")
    sidecar = {"task": task["id"], "run": run, "project": project["name"], "corpus": str(pristine),
               "prepared": snapshot(folder), "at": time.strftime("%Y-%m-%dT%H:%M:%S")}
    (out / f"{name}.json").write_text(json.dumps(sidecar, indent=1) + "\n", encoding="utf-8")
    return folder


def kicad_python(runtime: Path = RUNTIME) -> str:
    """The Python of the bench's own ``cad[kicad]`` environment, made once in ``runtime`` as
    ``scripts/test/test-kicad.sh`` makes the suite's: never the person's engine or installation."""
    for key, folder in (("CAD_STATE_DIR", "state"), ("CAD_CACHE_DIR", "cache"), ("CAD_ENGINE_DIR", "engine"),
                        ("CAD_LAUNCHER_DIR", "launcher")):
        os.environ[key] = str(runtime / folder)
    os.environ.update(pcb_fetch.TELEMETRY_OFF)
    from cad_server._internal import integration_env

    return integration_env.environment("kicad", lambda line: print(line, file=sys.stderr))


def kicad_runner(runtime: Path = RUNTIME) -> Callable[[str, str, Path], dict[str, Any]]:
    """``cad.<type>.<operation>(path)`` run in that environment, its result as data."""
    from cad_server._internal import integration_env

    python = kicad_python(runtime)

    def call(document_type: str, operation: str, path: Path) -> dict[str, Any]:
        return integration_env.call(python, document_type, operation, [str(path)], {})

    return call


def rebuilt(folder: Path, sidecar: dict[str, Any], project: dict[str, Any], scratch: Path) -> Path:
    """The run's sources built again in a fresh copy: every file of the run folder but what the corpus's
    build wrote, so the checks read the board its scripts make, never one edited by hand."""
    corpus = Path(sidecar["corpus"])
    made = set(snapshot(corpus)) - set(pcb_fetch.tracked(project["sample"]))
    target = scratch / "rebuild"
    for relative in snapshot(folder):
        if relative in made or relative == PROMPT:
            continue
        destination = pcb_fetch.inside(target, relative)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(folder / relative, destination)
    env = pcb_fetch.private_env(RUNTIME, sys.executable)
    done = subprocess.run([sys.executable, "-c", pcb_fetch.REGISTER, pcb_fetch.BENCH_INSTALLATION], env=env,
                          capture_output=True, text=True)
    if done.returncode:
        raise RuntimeError(f"could not register the bench's installation: {done.stderr[-400:]}")
    build = pcb_fetch.inside(target, project["build"])
    done = subprocess.run([sys.executable, build.name], cwd=build.parent, env=env, capture_output=True, text=True)
    if done.returncode:
        raise RuntimeError(f"the rebuild failed: {(done.stderr or done.stdout)[-800:]}")
    return target


def grade(folder: Path, kicad: Callable[[str, str, Path], dict[str, Any]] | None = None) -> dict[str, Any]:
    """The verdict on a finished run folder: every check, passed or not, with what it found."""
    manifest, tasks = load()
    folder = folder.resolve()
    sidecar = json.loads((folder.parent / f"{folder.name}.json").read_text(encoding="utf-8"))
    task = next(t for t in tasks["tasks"] if t["id"] == sidecar["task"])
    project = next(p for p in manifest["projects"] if p["name"] == task["project"])
    started = time.monotonic()
    kicad = kicad or kicad_runner()
    with tempfile.TemporaryDirectory(prefix="pcb-bench-") as scratch:
        result = folder
        if task.get("rebuild"):
            try:
                result = rebuilt(folder, sidecar, project, Path(scratch))
            except RuntimeError as error:
                return {"task": task["id"], "run": sidecar["run"], "pass": False,
                        "checks": [{"check": "rebuild", "pass": False, "detail": str(error)}],
                        "seconds": round(time.monotonic() - started, 1)}
        facts = Facts(result, Path(sidecar["corpus"]), project["board"], project["schematic"], sidecar["prepared"], kicad)
        rows = []
        for check in task["checks"]:
            try:
                passed, detail = evaluate(check, facts)
            except Exception as error:  # noqa: BLE001 - a check that cannot read the result fails, saying why
                passed, detail = False, f"{type(error).__name__}: {error}"
            rows.append({"check": check["check"], "pass": bool(passed), "detail": detail})
    return {"task": task["id"], "run": sidecar["run"], "pass": all(row["pass"] for row in rows), "checks": rows,
            "seconds": round(time.monotonic() - started, 1)}


def reference(folder: Path) -> None:
    """The task's reference fix, applied to a run folder (the selftest's proof that its checks can pass)."""
    _manifest, tasks = load()
    folder = folder.resolve()
    sidecar = json.loads((folder.parent / f"{folder.name}.json").read_text(encoding="utf-8"))
    task = next(t for t in tasks["tasks"] if t["id"] == sidecar["task"])
    needs = any(op["op"] == "refill" for op in task["reference"])
    apply(folder, task["reference"], Path(sidecar["corpus"]), kicad_python() if needs else None)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("tasks", help="check the task file against the manifest and list the tasks")
    making = sub.add_parser("prepare", help="a run folder per task and run id")
    making.add_argument("--task", action="append", default=[], help="a task id (repeat; default every task)")
    making.add_argument("--runs", type=int, default=1, help="run folders per task (run ids 1..N)")
    making.add_argument("--run", action="append", default=[], help="a run id (repeat), instead of --runs")
    making.add_argument("--out", type=Path, default=RUNS)
    making.add_argument("--corpus", type=Path, default=CORPUS)
    checking = sub.add_parser("check", help="grade finished run folders: a JSON verdict each")
    checking.add_argument("folders", type=Path, nargs="+")
    fixing = sub.add_parser("reference", help="apply each run's reference fix (proving its checks)")
    fixing.add_argument("folders", type=Path, nargs="+")
    proving = sub.add_parser("selftest", help="every task: seeded fails, reference fix passes")
    proving.add_argument("--task", action="append", default=[])
    proving.add_argument("--corpus", type=Path, default=CORPUS)
    proving.add_argument("--out", type=Path, default=ROOT / "tmp" / "pcb-bench" / "selftest")
    args = parser.parse_args(argv)

    if args.command == "tasks":
        _manifest, tasks = load()
        for task in tasks["tasks"]:
            print(f"{task['id']:34} {task['project']:30} {task['kind']}")
        return 0
    if args.command == "prepare":
        manifest, tasks = load()
        chosen = [t for t in tasks["tasks"] if not args.task or t["id"] in args.task]
        runs = args.run or [str(n) for n in range(1, args.runs + 1)]
        args.out.mkdir(parents=True, exist_ok=True)
        for task in chosen:
            project = next(p for p in manifest["projects"] if p["name"] == task["project"])
            for run in runs:
                print(f"{task['id']}\t{run}\t{prepare(task, project, args.corpus.resolve(), args.out.resolve(), run)}")
        return 0
    if args.command == "check":
        kicad = kicad_runner()
        failed = False
        for folder in args.folders:
            verdict = grade(folder, kicad)
            failed |= not verdict["pass"]
            print(json.dumps(verdict, default=str))
        return 1 if failed else 0
    if args.command == "reference":
        for folder in args.folders:
            reference(folder)
        return 0
    if args.command == "selftest":
        manifest, tasks = load()
        kicad = kicad_runner()
        chosen = [t for t in tasks["tasks"] if not args.task or t["id"] in args.task]
        stamp = time.strftime("%Y%m%d-%H%M%S")
        out = (args.out / stamp).resolve()
        out.mkdir(parents=True)
        bad = 0
        for task in chosen:
            project = next(p for p in manifest["projects"] if p["name"] == task["project"])
            seeded = prepare(task, project, args.corpus.resolve(), out, "seeded")
            fixed = prepare(task, project, args.corpus.resolve(), out, "fixed")
            reference(fixed)
            before, after = grade(seeded, kicad), grade(fixed, kicad)
            ok = not before["pass"] and after["pass"]
            bad += not ok
            failing = [row["check"] for row in before["checks"] if not row["pass"]]
            print(json.dumps({"task": task["id"], "ok": ok, "seeded_fails": failing,
                              "fixed": [row for row in after["checks"] if not row["pass"]] or "all pass",
                              "seconds": [before["seconds"], after["seconds"]]}, default=str), flush=True)
        print(f"selftest: {len(chosen) - bad} of {len(chosen)} tasks proven ({out})", file=sys.stderr)
        return 1 if bad else 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
