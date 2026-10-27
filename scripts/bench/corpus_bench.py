#!/usr/bin/env python3
"""The corpus batch: the xbf engine's builds of a set of models, cold to warm, timed.

A manual measurement, never run in CI (``AGENTS.md``); what it writes goes under an ignored
folder, ``tmp/bench/corpus-<time>/`` by default: ``rows.jsonl`` (one JSON object a line, each
appended as its step ends, so a crash loses nothing), ``table.md`` (rewritten after each model)
and the snapshots. Run it once every change it measures is in the branch, on a quiet machine,
from one place; ``compare.py`` sets its rows beside the old engine's recorded numbers.

    .venv/bin/python scripts/bench/corpus_bench.py --dry-run             # the config, checked
    .venv/bin/python scripts/bench/corpus_bench.py                       # every model in corpus.json
    .venv/bin/python scripts/bench/corpus_bench.py --model l_bracket     # one (repeat for more)

Each configured Python script runs its own explicit calls, unchanged, in a fresh client
process. A report recorder measures those calls without introducing any. The configured
``document`` selects an actual report by script and function, never by the export filename.
Builds run cold, unchanged, edited, reverted, after a restart with the engine's document
cache, and after a restart without that cache. Export, serve, mesh and snapshot are separate
steps reading the selected document's id. No exported file is used as a build cache.

Source copies and each model's engine, state, cache and launcher directories belong to this
batch alone. Telemetry and browser opening are disabled. See ``README.md`` for the config,
measurement boundaries, comparison limits and outputs.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, NamedTuple

ROOT = Path(__file__).resolve().parents[2]
CONFIG = Path(__file__).with_name("corpus.json")
BUILDS = ("cold", "noop", "edit", "revert", "restart", "restart-cold")
NOT_COPIED = frozenset({"XBF", "DXF", "__pycache__", ".DS_Store", ".git", ".venv", "venv",
                        "node_modules", "tmp", ".claude", ".codex", ".pytest_cache", ".pio"})
MODEL_KEYS = frozenset({"name", "root", "cwd", "pythonpath", "targets", "document", "xbf", "edit",
                        "needs", "note", "comparison_note"})
REQUIRED = ("name", "root", "targets", "document", "xbf", "edit")
EDIT_KEYS = frozenset({"file", "from", "to"})
NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*")
TARGET = re.compile(r"[^:]+\.py")
DOCUMENT = re.compile(r"[^:]+\.py::[A-Za-z_][A-Za-z0-9_]*")
TELEMETRY_OFF = {"DO_NOT_TRACK": "1", "CADGEN_TELEMETRY": "0"}
MARK = "corpus-bench:"  # the line the build process answers on

# Record only builds requested by the program's own calls. The normal Python control flow,
# including __main__ and a failure stopping subsequent calls, stays in charge. No engine verb
# executes or selects source for the runner. Instrumentation adds no CAD work to the wall.
DRIVER = """
import json, runpy, sys
from pathlib import Path
from cadgen.engine import api
builds = []
script = sys.argv[1]
build_script = api.build_script
def recorded(*args, **kwargs):
    found = build_script(*args, **kwargs)
    builds.append({"target": script, "models": found.models, "wall": found.wall, "fresh": found.fresh})
    return found
api.build_script = recorded
sys.argv = [script]
sys.path[0] = str(Path(script).parent)
answer = {"builds": builds}
try:
    runpy.run_path(script, run_name="__main__")
except BaseException as error:
    if not isinstance(error, SystemExit) or error.code not in (None, 0):
        answer["error"] = f"{type(error).__name__}: {error}"
        raise
finally:
    print("\\n" + MARK + json.dumps(answer), flush=True)
""".replace("MARK", repr(MARK))
PROBE = "import json, sys, cadgen; print(json.dumps({'cadgen': cadgen.__file__, 'python': sys.version.split()[0]}))"


# --- the config ---------------------------------------------------------------------------------


def _relative(value: Any, *, up: bool = False) -> bool:
    """A non-empty relative path; one that climbs (``..``) only where ``up``."""
    return (isinstance(value, str) and bool(value) and not Path(value).is_absolute()
            and (up or ".." not in Path(value).parts))


def _shape_problems(model: dict[str, Any], names: set[str]) -> list[str]:
    found = [f"unknown key `{key}`" for key in sorted(set(model) - MODEL_KEYS)]
    found += [f"no `{key}`" for key in REQUIRED if key not in model]
    name = model.get("name")
    if "name" in model:
        if not isinstance(name, str) or not NAME.fullmatch(name):
            found.append("`name` is a folder name: letters, digits, `_`, `.` and `-`")
        elif name in names:
            found.append("a second model of this name")
        else:
            names.add(name)
    for key, where in (("root", "from the repository"), ("cwd", "inside the project"), ("xbf", "inside the project")):
        if key in model and not _relative(model[key], up=key == "root"):
            found.append(f"`{key}` is a relative path {where}")
    if isinstance(model.get("xbf"), str) and not model["xbf"].endswith(".xbf"):
        found.append("`xbf` names an .xbf")
    targets = model.get("targets")
    if "targets" in model and (not isinstance(targets, list) or not targets or not all(
            isinstance(target, str) and TARGET.fullmatch(target) and _relative(target)
            for target in targets)):
        found.append("`targets` is a list of Python scripts (`script.py`)")
    document = model.get("document")
    if "document" in model and (not isinstance(document, str) or not DOCUMENT.fullmatch(document)
                                or not _relative(document.partition("::")[0])):
        found.append("`document` selects a built model by `script.py::function`, relative to cwd")
    for key in ("pythonpath", "needs"):
        if key in model and (not isinstance(model[key], list) or not all(_relative(path) for path in model[key])):
            found.append(f"`{key}` is a list of relative paths")
    for key in ("note", "comparison_note"):
        if key in model and (not isinstance(model[key], str) or not model[key].strip()):
            found.append(f"`{key}` is non-empty text")
    edit = model.get("edit")
    if "edit" in model:
        if not isinstance(edit, dict) or set(edit) != EDIT_KEYS or not all(
                isinstance(edit[key], str) and edit[key] for key in EDIT_KEYS):
            found.append("`edit` is {file, from, to}: three strings")
        elif edit["from"] == edit["to"]:
            found.append("the edit's `to` is its `from`")
        elif not _relative(edit["file"]):
            found.append("the edit's `file` is a relative path inside the project")
    return found


def _file_problems(model: dict[str, Any], root: Path) -> list[str]:
    project = root / model["root"]
    if not project.is_dir():
        return [f"no folder {model['root']}"]
    cwd = project / model.get("cwd", ".")
    if not cwd.is_dir():
        return [f"no folder {model.get('cwd')} in {model['root']}"]
    found = [f"no script {target} in {model['root']}/{model.get('cwd', '.')}" for target in model["targets"]
             if not (cwd / target).is_file()]
    found += [f"no folder {folder} (pythonpath)" for folder in model.get("pythonpath", []) if not (project / folder).is_dir()]
    found += [f"no {need}: an input the build reads that is never committed (the model's README says how to "
              "put it there)" for need in model.get("needs", []) if not (project / need).exists()]
    selected = cwd / model["document"].partition("::")[0]
    if not selected.is_file():
        found.append(f"no document script {model['document']} in {model['root']}/{model.get('cwd', '.')}")
    edit = model["edit"]
    path = project / edit["file"]
    if not path.is_file():
        found.append(f"no edit file {edit['file']}")
    else:
        count = path.read_text(encoding="utf-8").count(edit["from"])
        if count != 1:
            found.append(f"the edit's `from` occurs {count} times in {edit['file']}, not once")
    return found


def problems(config: Any, root: Path | None = None) -> list[str]:
    """What is wrong with a config, each in words; empty when nothing is. With ``root`` (the folder
    the models' roots are relative to) its files too: each model's folders, scripts and inputs
    exist, and its edit's ``from`` occurs exactly once in its file."""
    if not isinstance(config, dict) or not isinstance(config.get("models"), list) or not config["models"]:
        return ["the config is an object whose `models` is a list of models"]
    found = [f"unknown key `{key}`" for key in sorted(set(config) - {"about", "models"})]
    names: set[str] = set()
    for index, model in enumerate(config["models"]):
        if not isinstance(model, dict):
            found.append(f"models[{index}]: not an object")
            continue
        name = model.get("name")
        label = name if isinstance(name, str) and name else f"models[{index}]"
        mine = _shape_problems(model, names)
        if not mine and root is not None:
            mine = _file_problems(model, root)
        found += [f"{label}: {text}" for text in mine]
    return found


# --- a step's row -------------------------------------------------------------------------------


def _same(left: str, right: str) -> bool:
    return os.path.normcase(os.path.realpath(left)) == os.path.normcase(os.path.realpath(right))


def _files(report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Every file a model's build wrote or kept: its own, then each child model's."""
    found = dict(report.get("files") or {})
    for child in (report.get("child_models") or {}).values():
        if isinstance(child, dict):
            found.update(child.get("files") or {})
    return found


def driver_answer(stdout: str) -> dict[str, Any] | None:
    """The build process's answer: its last line marked ``MARK``."""
    for line in reversed(stdout.splitlines()):
        if line.startswith(MARK):
            try:
                return json.loads(line[len(MARK):])
            except ValueError:
                return None
    return None


def build_row(answer: Any, document: str | None = None) -> dict[str, Any]:
    """A build step's row from the build process's answer: each target's models' reports, summed.
    ``document`` is the configured xbf, whose size is ``xbf_bytes``."""
    row: dict[str, Any] = {"ok": True, "models": 0, "wall_api": 0.0, "fresh": None, "timings": {}, "hits": 0,
                           "misses": 0, "uncached": 0, "bodies_run": 0, "bodies_replayed": 0, "bodies_loaded": 0,
                           "cache": None, "cache_reason": None, "parts": 0, "files": {}, "xbf_bytes": None}
    builds = answer.get("builds") if isinstance(answer, dict) else None
    if not isinstance(builds, list):
        return {**row, "ok": False, "error": "the build process gave no answer"}
    errors: list[str] = [str(answer["error"])] if answer.get("error") else []
    taken: list[str] = []
    for build in builds:
        if "error" in build:
            errors.append(f"{build.get('target')}: {build['error']}")
            continue
        row["wall_api"] = round(row["wall_api"] + float(build.get("wall") or 0), 4)
        if build.get("fresh") is not None:
            row["fresh"] = bool(row["fresh"]) or bool(build["fresh"])
        for report in build.get("models") or []:
            row["models"] += 1
            if not report.get("ok"):
                errors.append(str(report.get("error") or f"{report.get('model')} failed"))
            for name, seconds in (report.get("timings") or {}).items():
                if isinstance(seconds, (int, float)):
                    row["timings"][name] = round(row["timings"].get(name, 0.0) + seconds, 4)
            memo = report.get("memo") if isinstance(report.get("memo"), dict) else {}
            statuses = list((report.get("bodies") or {}).values())
            for key in ("hits", "misses", "uncached", "bodies_loaded"):
                row[key] += int(memo.get(key) or 0)
            row["bodies_run"] += int(memo["bodies_run"]) if "bodies_run" in memo else statuses.count("run")
            row["bodies_replayed"] += (int(memo["bodies_skipped"]) if "bodies_skipped" in memo
                                       else statuses.count("replayed"))
            cache = report.get("cache") if isinstance(report.get("cache"), dict) else {}
            if cache.get("used"):
                taken.append(str(cache.get("from")))
            elif cache.get("reason") and row["cache_reason"] is None:
                row["cache_reason"] = str(cache["reason"])
            row["parts"] += int(report.get("parts") or 0)
            if report.get("retired"):
                row["retired"] = True
            for path, file in _files(report).items():
                kind = file.get("kind") or Path(path).suffix.lstrip(".").lower()
                held = row["files"].setdefault(kind, {"written": 0, "kept": 0, "bytes": 0, "seconds": 0.0})
                held["written" if file.get("written") else "kept"] += 1
                held["bytes"] += int(file.get("bytes") or 0)
                held["seconds"] = round(held["seconds"] + float(file.get("seconds") or 0), 4)
                if document is not None and _same(path, document):
                    row["xbf_bytes"] = int(file.get("bytes") or 0)
    if taken and len(taken) == row["models"]:
        row["cache"] = "+".join(sorted(set(taken)))
    if not row["models"] and not errors:
        errors.append("the scripts made no model calls")
    if errors:
        row["ok"] = False
        row["error"] = "\n".join(errors)[-4000:]
    return row


def worker_memory(status: Any, scripts: Iterable[str]) -> int | None:
    """The resident memory in MB of the workers that build ``scripts``, as each measured it after its
    last build (``cadgen status --json``), summed; None when the daemon names none of them."""
    if not isinstance(status, dict):
        return None
    wanted = [str(script) for script in scripts]
    sizes = [worker["rssMb"] for worker in status.get("workers") or []
             if isinstance(worker, dict) and isinstance(worker.get("rssMb"), (int, float))
             and any(_same(str(worker.get("script")), script) for script in wanted)]
    return round(sum(sizes)) if sizes else None


def last_json(stdout: str) -> Any:
    for line in reversed(stdout.splitlines()):
        if line.startswith("{"):
            try:
                return json.loads(line)
            except ValueError:
                return None
    return None


# --- the table ----------------------------------------------------------------------------------

COLUMNS = ("model", "cold wall / body", "no-op", "edit wall / body (misses; run+replayed)", "revert", "restart",
           "cold restart", "xbf MB", "mesh cold / warm", "snapshot", "worker MB", "load")


def seconds(value: Any) -> str:
    """A time as the batch notes write one: two decimals under 10, one under 100, none above."""
    if not isinstance(value, (int, float)):
        return "—"
    return f"{value:.2f}" if value < 10 else f"{value:.1f}" if value < 100 else f"{value:.0f}"


def megabytes(count: Any) -> str:
    if not isinstance(count, (int, float)):
        return "—"
    value = count / 1e6
    return f"{value:.2f}" if value < 1 else f"{value:.1f}"


def _wall(row: dict[str, Any] | None, detail: str = "") -> str:
    """A step's wall (and ``detail`` after it), ``failed``, or a dash for a step not run."""
    if row is None:
        return "—"
    return "failed" if not row.get("ok", True) else seconds(row.get("wall")) + detail


def _body(row: dict[str, Any] | None) -> str:
    return f" / {seconds(((row or {}).get('timings') or {}).get('body'))}"


def _taken(row: dict[str, Any] | None) -> str:
    """After a restart's wall: what it took whole (the engine's document cache), or that it took nothing."""
    if row is None or "cache" not in row:
        return ""
    return f" ({row['cache']})" if row["cache"] else " (not taken)"


def table(rows: Iterable[dict[str, Any]]) -> str:
    """The batch as Markdown, a line a model in the order they ran: each build's wall (and the cold's
    and the edit's body, the edit's memo misses and bodies run and replayed, and what the restart
    took whole), the document's size,
    the whole-document mesh cold and warm, the warm snapshot, the largest worker memory after a build
    and the range of the 1-minute load average. A step that failed says so; one not run is a dash."""
    steps: dict[str, dict[str, dict[str, Any]]] = {}
    for row in rows:
        if row.get("kind") == "step" and isinstance(row.get("model"), str) and isinstance(row.get("step"), str):
            steps.setdefault(row["model"], {})[row["step"]] = row
    lines = ["| " + " | ".join(COLUMNS) + " |", "|" + "---|" * len(COLUMNS)]
    for model, done in steps.items():
        edit = done.get("edit") or {}
        sizes = [row["xbf_bytes"] for row in (done.get(step) for step in (*BUILDS, "export"))
                 if row and row.get("xbf_bytes")]
        memory = [row["rss_mb"] for row in done.values() if isinstance(row.get("rss_mb"), (int, float))]
        load = [row["load"] for row in done.values() if isinstance(row.get("load"), (int, float))]
        mesh = _wall(done.get("mesh-cold"))
        if mesh not in ("—", "failed"):
            mesh += f" / {_wall(done.get('mesh-warm'))}"
        cells = [
            model,
            _wall(done.get("cold"), _body(done.get("cold"))),
            _wall(done.get("noop")),
            _wall(done.get("edit"), _body(edit) + f" ({edit.get('misses')}; {edit.get('bodies_run')}+"
                                                   f"{edit.get('bodies_replayed')})"),
            _wall(done.get("revert")),
            _wall(done.get("restart"), _taken(done.get("restart"))),
            _wall(done.get("restart-cold")),
            megabytes(sizes[0]) if sizes else "—",
            mesh,
            _wall(done.get("snapshot")),
            str(round(max(memory))) if memory else "—",
            "—" if not load else f"{min(load):.1f}" + ("" if min(load) == max(load) else f"–{max(load):.1f}"),
        ]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n"


def heading(run: dict[str, Any] | None) -> str:
    """What the table measured: when, which commit and cadgen, on what."""
    if not run:
        return "# Corpus batch\n"
    commit = (run.get("commit") or "?")[:10] + (" (uncommitted changes)" if run.get("dirty") else "")
    machine = ", ".join([str(run.get("platform") or "?"), *([f"{run['cpus']} cores"] if run.get("cpus") else []),
                         *([f"{run['memory_gb']} GB"] if run.get("memory_gb") else [])])
    return (f"# Corpus batch, {run.get('started', '?')}\n\n"
            f"{commit} on {run.get('branch') or '?'}; cadgen {run.get('cadgen', '?')}; Python {run.get('python', '?')}; "
            f"{machine}.\n\nSeconds: a build's wall is its process's, as `python model.py` waits; body is the engine's. "
            "Memo misses and bodies run+replayed are the edit's. The mesh is the whole document's on the server's "
            "pool, cold, then with its meshes dropped; the snapshot is the second, warm. Worker MB is the largest "
            "resident memory after a build; load, the 1-minute average before each step.\n")


def describe(row: dict[str, Any]) -> str:
    """One progress line for a step."""
    head = f"{row.get('model', ''):16s} {row.get('step', ''):15s}"
    if not row.get("ok", True):
        return f"{head}FAILED {str(row.get('error', ''))[:400]}"
    words = [f"{seconds(row.get('wall'))} s"]
    if "misses" in row:
        words += [f"body {seconds(row.get('timings', {}).get('body'))}", f"misses {row['misses']}",
                  f"bodies {row['bodies_run']}+{row['bodies_replayed']}"
                  + (f" loaded {row['bodies_loaded']}" if row.get("bodies_loaded") else "")]
        words += [f"{kind} {held['written']} written {held['kept']} kept {megabytes(held['bytes'])} MB"
                  for kind, held in row.get("files", {}).items()]
        if row.get("rss_mb"):
            words.append(f"worker {row['rss_mb']} MB")
    elif "triangles" in row:
        words += [f"parts {row.get('meshed')}/{row.get('parts')}", f"triangles {row.get('triangles')}",
                  f"unmeshed {row.get('unmeshed')}"]
    if isinstance(row.get("load"), (int, float)):
        words.append(f"load {row['load']:.1f}")
    return head + "  ".join(words)


# --- running ------------------------------------------------------------------------------------


def loads() -> dict[str, float]:
    if not hasattr(os, "getloadavg"):
        return {}
    one, five, _fifteen = os.getloadavg()
    return {"load": round(one, 2), "load5": round(five, 2)}


def remove(path: Path) -> None:
    """``path`` and all in it, read-only files and folders too (tom's vendor inputs are)."""
    if path.is_symlink() or path.is_file():
        path.unlink()
        return
    if not path.exists():
        return
    for folder, _folders, _names in os.walk(path):
        os.chmod(folder, os.stat(folder).st_mode | stat.S_IRWXU)

    def writable(function: Any, target: str, *_error: Any) -> None:
        os.chmod(target, stat.S_IWRITE | stat.S_IREAD)
        function(target)

    if sys.version_info >= (3, 12):
        shutil.rmtree(path, onexc=writable)
    else:
        shutil.rmtree(path, onerror=writable)


def copy_project(source: Path, work: Path) -> None:
    """Copy source and inputs, never local environments or metadata; refuse symlinks so a
    script, edit or export in the copy cannot write through one into the owner's checkout."""
    source, work = source.resolve(), work.resolve()
    if work.is_relative_to(source):
        raise ValueError("the work copy must be outside its source project")

    def excluded(folder: str, names: list[str]) -> set[str]:
        for name in names:
            if name not in NOT_COPIED and (Path(folder) / name).is_symlink():
                raise ValueError(f"copy refuses symlink {Path(folder) / name}")
        return set(names) & NOT_COPIED

    def copied(source_file: str, target_file: str) -> str:
        if sys.platform == "darwin":
            done = subprocess.run(["cp", "-c", source_file, target_file], capture_output=True)
            if done.returncode == 0:
                return target_file
        return shutil.copy2(source_file, target_file)

    shutil.copytree(source, work, ignore=excluded, copy_function=copied)


def document_id(answer: dict[str, Any], script: str, function: str) -> str:
    """Select a successfully built document from reports, including called child models.
    A missing or ambiguous result is an error, never a guessed id or a filename fallback."""
    matches = set()
    pending = [report for build in answer["builds"] for report in build.get("models", [])]
    while pending:
        report = pending.pop()
        source = report.get("source") or {}
        if (_same(source.get("script", ""), script) and source.get("name") == function
                and report.get("ok") and report.get("id")):
            matches.add(report["id"])
        pending.extend((report.get("child_models") or {}).values())
    if len(matches) != 1:
        raise ValueError(f"expected one built document for {script}::{function}; found {len(matches)}")
    return matches.pop()


def inside(work: Path, path: Path) -> Path:
    """Every writable benchmark artifact stays in its work copy, including through symlinks."""
    resolved = path.resolve()
    if not resolved.is_relative_to(work.resolve()):
        raise ValueError(f"path escapes the work copy: {path}")
    return resolved


def git(*args: str) -> str | None:
    try:
        return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def memory_gb() -> float | None:
    try:
        return round(os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 2 ** 30, 1)
    except (AttributeError, ValueError, OSError):
        return None


def probe(python: str, cadgen_src: Path) -> dict[str, Any] | str:
    """The cadgen ``python`` imports with ``cadgen_src`` on its path, and its version; the problem
    as text when it imports none, or another (the venv's editable install, say)."""
    env = {**os.environ, "PYTHONPATH": str(cadgen_src), **TELEMETRY_OFF}
    try:
        done = subprocess.run([python, "-B", "-c", PROBE], env=env, capture_output=True, text=True, timeout=300)
    except (OSError, subprocess.TimeoutExpired) as error:
        return f"{python}: {error}"
    if done.returncode:
        return f"{python} cannot import cadgen from {cadgen_src}: {done.stderr.strip()[-500:]}"
    found = json.loads(done.stdout.strip().splitlines()[-1])
    if not Path(found["cadgen"]).resolve().is_relative_to(cadgen_src.resolve()):
        return f"{python} imports cadgen from {found['cadgen']}, not from {cadgen_src}"
    return found


class Model(NamedTuple):
    """One configured model, on its work copy."""

    name: str
    work: Path
    cwd: Path
    env: dict[str, str]
    targets: list[str]
    scripts: list[str]
    document: Path
    selection: tuple[str, str]
    comparison_note: str | None
    edit: Path
    before: str
    after: str


def prepare(spec: dict[str, Any], out: Path, engine_dir: Path, cadgen_src: Path) -> Model:
    work = out / "work" / spec["name"]
    cwd = work / spec.get("cwd", ".")
    scripts = [str((cwd / target).resolve()) for target in spec["targets"]]
    selected_script, _, function = spec["document"].partition("::")
    path = os.pathsep.join([str(cadgen_src), *(str(work / folder) for folder in spec.get("pythonpath", []))])
    private = out / "runtime" / spec["name"]
    env = {**os.environ, "CADGEN_ENGINE_DIR": str(engine_dir / spec["name"]),
           "CADGEN_STATE_DIR": str(private / "state"), "CADGEN_CACHE_DIR": str(private / "cache"),
           "CADGEN_LAUNCHER_DIR": str(private / "launcher"), "CADGEN_ENGINE_PORT": "0",
           "CADGEN_ENGINE_STANDBY": "0", "PYTHONPATH": path,
           "PYTHONPYCACHEPREFIX": str(private / "cache" / "pycache"),
           "BROWSER": str(out / "no-browser.py") + " %s", **TELEMETRY_OFF}
    env.pop("PYTHONDONTWRITEBYTECODE", None)  # compile into this model's private prefix
    return Model(spec["name"], work, cwd, env, scripts, scripts, work / spec["xbf"],
                 (str((cwd / selected_script).resolve()), function), spec.get("comparison_note"),
                 work / spec["edit"]["file"], spec["edit"]["from"], spec["edit"]["to"])


class Bench:
    """One batch: its rows, appended to ``rows.jsonl`` as each step ends."""

    def __init__(self, out: Path, python: str, timeout: float, limit: float | None = None) -> None:
        self.out, self.python, self.timeout, self.limit = out, python, timeout, limit
        self.rows: list[dict[str, Any]] = []
        self.failed = False
        self.ids: dict[str, str] = {}  # the selected document id, from its actual build report

    def emit(self, row: dict[str, Any]) -> None:
        row = {**row, "at": datetime.now().isoformat(timespec="seconds")}
        self.rows.append(row)
        with open(self.out / "rows.jsonl", "a", encoding="utf-8") as handle:
            handle.write(json.dumps(row) + "\n")
        if row.get("ok") is False:
            self.failed = True
        if row.get("kind") == "step":
            print(describe(row), file=sys.stderr, flush=True)

    def run(self, model: Model, args: list[str], timeout: float | None = None) -> tuple[Any, float]:
        """``args`` run by the interpreter, in the model's folder and environment: the finished
        process (None when it ran out of time) and its wall."""
        started = time.perf_counter()
        try:
            done = subprocess.run([self.python, *args], cwd=model.cwd, env=model.env, capture_output=True, text=True,
                                  encoding="utf-8", errors="replace", timeout=timeout or self.timeout)
        except subprocess.TimeoutExpired:
            done = None
        return done, time.perf_counter() - started

    def stop(self, model: Model) -> None:
        done, _wall = self.run(model, ["-m", "cadgen.cli", "stop"], timeout=300)
        if done is None or done.returncode:
            raise RuntimeError(f"its daemon did not stop: {done.stderr[-500:] if done else 'no answer'}")

    def status(self, model: Model) -> Any:
        done, _wall = self.run(model, ["-m", "cadgen.cli", "status", "--json"], timeout=120)
        if done is None or done.returncode:
            raise RuntimeError(f"status failed: {done.stderr[-500:] if done else 'no answer'}")
        found = json.loads(done.stdout)
        if not isinstance(found, dict) or "workers" not in found:
            raise ValueError("status returned no workers list")
        return found

    def step(self, model: Model, step: str, wall: float, load: dict[str, float], **row: Any) -> dict[str, Any]:
        row = {"kind": "step", "model": model.name, "step": step, "wall": round(wall, 3), **load, **row}
        self.emit(row)
        return row

    def daemon(self, model: Model) -> list[int]:
        """The pid of the model's own engine daemon, if one holds its door open."""
        done, _wall = self.run(model, ["-c", "from cadgen.engine.daemon import address; print(address())"], 60)
        path = done.stdout.strip() if done is not None and done.returncode == 0 else ""
        if not path or not os.path.exists(path):
            return []
        found = subprocess.run(["lsof", "-t", path], capture_output=True, text=True).stdout.split()
        return [int(pid) for pid in found if pid.isdigit()]

    def quiet(self, model: Model) -> dict[str, float]:
        """``--max-load``'s guard before a step: the load at most the limit and no other cadgen
        build busy; then the load the step starts at."""
        wait_until_quiet(self.limit, self.daemon(model) if self.limit is not None else ())
        return loads()

    def build(self, model: Model, step: str) -> dict[str, Any]:
        top = {"top": top_three()} if step in ("cold", "restart-cold") and self.limit is not None else {}
        load = self.quiet(model)
        answer: dict[str, Any] = {"builds": []}
        wall = 0.0
        stderr = []
        for script in model.targets:
            done, elapsed = self.run(model, ["-c", DRIVER, script])
            wall += elapsed
            result = driver_answer(done.stdout) if done is not None else None
            if result is not None:
                answer["builds"].extend(result["builds"])
            if done is not None:
                stderr.append(done.stderr)
            if done is None or done.returncode or result is None:
                answer["error"] = (result or {}).get("error") or (
                    f"{script}: process exited {done.returncode} without a valid answer" if done else
                    f"{script}: no answer in {self.timeout:.0f} s")
                break
        row = build_row(answer, str(model.document))
        if row["ok"]:
            try:
                self.ids[model.name] = document_id(answer, *model.selection)
                row["document_id"] = self.ids[model.name]
                row["rss_mb"] = worker_memory(self.status(model), model.scripts)
            except (ValueError, RuntimeError) as error:
                row.update(ok=False, error=str(error))
        if not row["ok"]:
            row["stderr"] = "\n".join(stderr)[-3000:]
        if model.comparison_note:
            row["comparison_note"] = model.comparison_note
        return self.step(model, step, wall, load, **row, **top)

    def document(self, model: Model) -> None:
        """The document saved, served and meshed whole, its structure read, and two snapshots."""
        ident = self.ids[model.name]
        inside(model.work, model.document)
        load = self.quiet(model)
        done, wall = self.run(model, ["-m", "cadgen.cli", "export", ident, str(model.document), "--json"], timeout=1800)
        report = last_json(done.stdout) if done is not None else None
        files = report.get("files") if isinstance(report, dict) else None
        if (done is None or done.returncode or not report or report.get("ok") is not True
                or not isinstance(files, list) or len(files) != 1 or files[0].get("kind") != "xbf"
                or not _same(files[0].get("path", ""), str(model.document)) or not model.document.is_file()
                or files[0].get("bytes") != model.document.stat().st_size):
            self.step(model, "export", wall, load, ok=False,
                      error=(report or {}).get("error") or (done.stderr[-2000:] if done else "no answer")
                            or "export returned an invalid file report")
            return
        self.step(model, "export", wall, load, ok=True, document_id=ident,
                  xbf_bytes=files[0]["bytes"], xbf_seconds=files[0]["seconds"], written=files[0]["written"])
        load = self.quiet(model)
        done, wall = self.run(model, ["-m", "cadgen.cli", "serve", ident], timeout=600)
        url = (done.stdout.strip().splitlines() or [""])[-1] if done is not None else ""
        page = urllib.parse.urlsplit(url)
        if (done is None or done.returncode or page.hostname not in ("127.0.0.1", "localhost", "::1")
                or page.path.strip("/") != ident or page.scheme != "http"):
            self.step(model, "serve", wall, load, ok=False, error=(done.stderr[-2000:] if done else "no answer")
                      or "serve returned no loopback URL for the built document")
            return
        else:
            self.step(model, "serve", wall, load, ok=True)
            # The page is ``<engine>/<id>?token=...``: the document's routes are under
            # ``/api/doc/<id>``, and take the page's token as a bearer.
            api = f"{page.scheme}://{page.netloc}/api/doc/{ident}"
            token = (urllib.parse.parse_qs(page.query).get("token") or [""])[0]
            auth = {"Authorization": f"Bearer {token}"} if token else {}
            for step, query in (("mesh-cold", ""), ("mesh-warm", "?drop=1")):
                load, started = loads(), time.perf_counter()
                try:
                    # A POST carries the viewer's guard header, as the page's do.
                    with urllib.request.urlopen(urllib.request.Request(f"{api}/mesh{query}", data=b"", method="POST",
                                                                       headers={**auth, "x-cadgen-viewer": "1"}),
                                                timeout=self.timeout) as response:  # noqa: S310 - the engine, on loopback
                        answer = json.loads(response.read())
                        required = {"seconds", "parts", "meshed", "triangles", "bytes", "unmeshed", "mode", "workers", "per_part"}
                        if not isinstance(answer, dict) or not required <= answer.keys():
                            raise ValueError("mesh returned an invalid report")
                except Exception as error:  # noqa: BLE001 - a bench row, not a program
                    self.step(model, step, time.perf_counter() - started, load, ok=False,
                              error=f"{type(error).__name__}: {error}")
                    return
                self.step(model, step, time.perf_counter() - started, load, ok=True,
                          **{key: answer.get(key) for key in ("seconds", "parts", "meshed", "triangles", "bytes",
                                                              "unmeshed", "mode", "workers")},
                          slowest=(answer.get("per_part") or {}).get("slowest"))
            load, started = loads(), time.perf_counter()
            try:
                with urllib.request.urlopen(urllib.request.Request(api, headers=auth), timeout=600) as response:  # noqa: S310 - the engine, on loopback
                    data = response.read()
                structure = json.loads(data)
                if not isinstance(structure, dict) or not {"prototypes", "instances"} <= structure.keys():
                    raise ValueError("structure returned no prototypes or instances")
                self.step(model, "structure", time.perf_counter() - started, load, ok=True, bytes=len(data),
                          prototypes=len(structure.get("prototypes") or []),
                          instances=len(structure.get("instances") or []))
            except Exception as error:  # noqa: BLE001 - a bench row, not a program
                self.step(model, "structure", time.perf_counter() - started, load, ok=False,
                          error=f"{type(error).__name__}: {error}")
                return
        pictures = self.out / "snapshots"
        pictures.mkdir(exist_ok=True)
        for step in ("snapshot-first", "snapshot"):
            png = pictures / f"{model.name}{'-first' if step == 'snapshot-first' else ''}.png"
            load = self.quiet(model)
            done, wall = self.run(model, ["-m", "cadgen.cli", "snapshot", ident, str(png), "--json"],
                                  timeout=1800)
            report = last_json(done.stdout) if done is not None else None
            report = report if isinstance(report, dict) else {}
            if (done is not None and done.returncode == 0 and png.is_file() and report.get("width")
                    and report.get("height") and isinstance(report.get("timings"), dict)):
                self.step(model, step, wall, load, ok=True, timings=report.get("timings"), width=report.get("width"),
                          height=report.get("height"), png_bytes=png.stat().st_size)
            else:
                self.step(model, step, wall, load, ok=False, error=report.get("error") or
                          (done.stderr[-2000:] if done else "no answer") or "snapshot returned an invalid report")
                return

    def model(self, spec: dict[str, Any], engine_dir: Path, cadgen_src: Path, keep: bool) -> None:
        """Every step of one model, on its work copy and its own daemon; the daemon stopped after,
        and the copy removed unless kept."""
        model = prepare(spec, self.out, engine_dir, cadgen_src)
        original = None
        phase = "setup"
        stopped = False
        try:
            copy_project(ROOT / spec["root"], model.work)
            inside(model.work, model.edit)
            inside(model.work, model.document)
            original = model.edit.read_bytes()
            for step in BUILDS:
                phase = step
                if step == "edit":
                    model.edit.write_bytes(original.decode("utf-8").replace(model.before, model.after, 1).encode("utf-8"))
                elif step == "revert":
                    model.edit.write_bytes(original)
                elif step in ("restart", "restart-cold"):
                    self.stop(model)
                    if step == "restart-cold":
                        remove(Path(model.env["CADGEN_CACHE_DIR"]) / "documents")
                if not self.build(model, step)["ok"]:
                    return
            phase = "document"
            self.document(model)
        except Exception as error:  # noqa: BLE001 - record the failed measurement, never continue it
            self.step(model, phase, 0, loads(), ok=False, error=f"{type(error).__name__}: {error}")
        finally:
            if model.cwd.is_dir():
                try:
                    self.stop(model)
                    stopped = True
                except Exception as error:  # noqa: BLE001 - retain its files when the process may still use them
                    self.step(model, "stop", 0, loads(), ok=False, error=str(error))
            if original is not None:
                if keep or not stopped:
                    model.edit.write_bytes(original)
                else:
                    remove(model.work)


def _processes() -> dict[int, tuple[int, float, str]]:
    """Every process: its parent, CPU seconds so far and command line (``ps``)."""
    try:
        out = subprocess.run(["ps", "-A", "-o", "pid=,ppid=,time=,command="], capture_output=True, text=True).stdout
    except OSError:
        return {}
    found: dict[int, tuple[int, float, str]] = {}
    for line in out.splitlines():
        fields = line.split(None, 3)
        if len(fields) == 4:
            days, _sep, clock = fields[2].rpartition("-")
            seconds = 0.0
            for part in clock.split(":"):
                seconds = seconds * 60 + float(part)
            found[int(fields[0])] = (int(fields[1]), seconds + (float(days) * 86400 if days else 0.0), fields[3])
    return found


def busy_builds(own: Iterable[int], seconds: float = 2.0, share: float = 0.05) -> list[str]:
    """The cadgen processes outside ``own`` (a daemon's pid and its descendants are left out) using
    more than ``share`` of a core over ``seconds``: another build on the machine."""
    first = _processes()
    time.sleep(seconds)
    second = _processes()
    mine = {pid for pid in own if pid in second} | {os.getpid()}
    grew = True
    while grew:
        grew = False
        for pid, (parent, _cpu, _command) in second.items():
            if parent in mine and pid not in mine:
                mine.add(pid)
                grew = True
    return [f"{pid} {command[:120]}" for pid, (_parent, cpu, command) in second.items()
            if pid not in mine and "cadgen" in command and pid in first
            and (cpu - first[pid][1]) / seconds > share]


def top_three() -> list[str]:
    """The three processes using the most CPU now (macOS ``top``, its second sample)."""
    try:
        out = subprocess.run(["top", "-l", "2", "-o", "cpu", "-n", "3", "-stats", "pid,command,cpu"],
                             capture_output=True, text=True, timeout=30).stdout
    except (OSError, subprocess.TimeoutExpired):
        return []
    lines = [line.split() for line in out.splitlines()]
    rows = [line for line in lines if len(line) >= 3 and line[0].isdigit()]
    return [" ".join(row) for row in rows[-3:]]


def wait_until_quiet(limit: float | None, own: Iterable[int] = ()) -> None:
    """Wait while the 1-minute load average is over ``limit`` or another cadgen build is busy."""
    if limit is None or not hasattr(os, "getloadavg"):
        return
    own = list(own)
    while True:
        load = os.getloadavg()[0]
        others = busy_builds(own) if load <= limit else []
        if load <= limit and not others:
            return
        why = f"load {load:.1f} is over {limit:g}" if load > limit else f"another build is busy: {others[0]}"
        print(f"{why}: waiting", file=sys.stderr, flush=True)
        time.sleep(15)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--config", type=Path, default=CONFIG, help="the models (default: corpus.json beside this)")
    parser.add_argument("--model", action="append", default=[], help="this model alone (repeat for more)")
    parser.add_argument("--dry-run", action="store_true", help="check the config and the interpreter, run nothing")
    parser.add_argument("--out", type=Path, help="the batch's folder (default: tmp/bench/corpus-<time>)")
    parser.add_argument("--engine-dir", type=Path, default=Path(tempfile.gettempdir()) / "cadgen-bench",
                        help="parent for a fresh batch folder containing each model's private engine door")
    parser.add_argument("--python", default=sys.executable, help="the interpreter that builds (default: this one)")
    parser.add_argument("--cadgen-src", type=Path, default=ROOT / "packages/cadgen/src",
                        help="the cadgen it imports (default: this checkout's)")
    parser.add_argument("--max-load", type=float, help="before each step, wait until the 1-minute load is at most this and no other cadgen build "
                        "uses more than 5%% of a core")
    parser.add_argument("--timeout", type=float, default=3600, help="seconds a build may take (default 3600)")
    parser.add_argument("--keep", action="store_true", help="keep each model's work copy")
    args = parser.parse_args(argv)
    args.engine_dir, args.cadgen_src = args.engine_dir.resolve(), args.cadgen_src.resolve()

    try:
        config = json.loads(args.config.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        print(f"corpus_bench: {args.config}: {error}", file=sys.stderr)
        return 2
    chosen: list[dict[str, Any]] = []
    found = problems(config)
    if not found:
        known = [model["name"] for model in config["models"]]
        unknown = [name for name in args.model if name not in known]
        if unknown:
            print(f"corpus_bench: no model {', '.join(unknown)} in {args.config}; it has {', '.join(known)}",
                  file=sys.stderr)
            return 2
        chosen = [model for model in config["models"] if not args.model or model["name"] in args.model]
        found = problems({"models": chosen}, ROOT)
    found_cadgen = probe(args.python, args.cadgen_src)
    if isinstance(found_cadgen, str):
        found.append(found_cadgen)
    if args.dry_run:
        for model in chosen:
            edit = model["edit"]
            print(f"{model['name']:16s} {model['root']}/{model.get('cwd', '.')}: {' '.join(model['targets'])}; "
                  f"edit {edit['file']}: {edit['from']!r} -> {edit['to']!r}")
        print(f"steps: {', '.join(BUILDS)}, export, serve, mesh-cold, mesh-warm, structure, snapshot-first, snapshot")
        if isinstance(found_cadgen, dict):
            print(f"cadgen {found_cadgen['cadgen']} (Python {found_cadgen['python']}, {args.python})")
        print(f"daemons in a fresh batch folder under {args.engine_dir}; private state/cache/launcher under --out/runtime")
        for text in found:
            print(f"problem: {text}")
        print("ok" if not found else f"{len(found)} problem{'s' if len(found) != 1 else ''}")
        return 1 if found else 0
    if found:
        for text in found:
            print(f"corpus_bench: {text}", file=sys.stderr)
        return 2

    out = (args.out or ROOT / "tmp" / "bench" / f"corpus-{datetime.now():%Y%m%d-%H%M%S}").resolve()
    if out.exists():
        print(f"corpus_bench: output folder already exists: {out}; choose a fresh folder", file=sys.stderr)
        return 2
    out.mkdir(parents=True)
    args.engine_dir.mkdir(parents=True, exist_ok=True)
    args.engine_dir = Path(tempfile.mkdtemp(prefix="corpus-", dir=args.engine_dir))
    browser = out / "no-browser.py"
    browser.write_text(f"#!{args.python}\nimport sys\nfrom pathlib import Path\n"
                       f"with Path({str(out / 'browser-requests.log')!r}).open('a') as log:\n"
                       "    log.write(repr(sys.argv[1:]) + '\\n')\n", encoding="utf-8")
    browser.chmod(0o700)
    bench = Bench(out, args.python, args.timeout, args.max_load)
    run = {"kind": "run", "started": datetime.now().isoformat(timespec="seconds"), "commit": git("rev-parse", "HEAD"),
           "branch": git("rev-parse", "--abbrev-ref", "HEAD"), "dirty": bool(git("status", "--porcelain")),
           "cadgen": found_cadgen["cadgen"], "python": found_cadgen["python"], "interpreter": args.python,
           "platform": platform.platform(), "cpus": os.cpu_count(), "memory_gb": memory_gb(),
           "engine_dir": str(args.engine_dir), "config": str(args.config), "models": [model["name"] for model in chosen],
           "environment": {key: value for key, value in os.environ.items() if key.startswith("CADGEN_")}}
    bench.emit(run)
    print(f"corpus_bench: {len(chosen)} model{'s' if len(chosen) != 1 else ''} into {out}", file=sys.stderr, flush=True)
    for spec in chosen:
        bench.model(spec, args.engine_dir, args.cadgen_src, args.keep)
        (out / "table.md").write_text(heading(run) + "\n" + table(bench.rows), encoding="utf-8")
    work = out / "work"
    if work.is_dir() and not any(work.iterdir()):
        work.rmdir()
    print(heading(run) + "\n" + table(bench.rows))
    print(f"corpus_bench: rows in {out / 'rows.jsonl'}, the table in {out / 'table.md'}", file=sys.stderr)
    return 1 if bench.failed else 0


if __name__ == "__main__":
    sys.exit(main())
