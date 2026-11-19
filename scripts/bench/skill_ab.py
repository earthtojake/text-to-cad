#!/usr/bin/env python3
"""Prepare an A/B test of the skills: the same tasks, done once with the skills of a Git ref and once with the
working tree's, each by a fresh agent that reads only its own copy.

    scripts/bench/skill_ab.py --base main                    # every task in scripts/bench/skill_ab/tasks
    scripts/bench/skill_ab.py --base main --task cad-part --task pcb-edit
    scripts/bench/skill_ab.py --base v0.11.13 --out tmp/skill-ab

A change to a skill is a change to what agents do, and reading the diff does not say what. This lays out, under
``tmp/skill-ab`` (ignored), one folder per task and variant: a copy of one set of skills, a working folder with
the task's fixtures, an ``env.sh`` that gives the run a cad server of its own (and starts it), and a ``BRIEF.md``
to hand to an agent. It runs no agent and grades nothing: start one agent per folder on the model you are testing for
(weaker than the one that wrote the change), then read each task's ``Expect`` against what the agent made, with
your own ``cad`` commands and never the agent's word. ``runs.tsv`` says which folder had which skills; keep it
from the agents.

A task is a Markdown file: ``skill: <name>`` on its first line, optional ``fixtures:`` (``FILE -> DEST`` copies
a file of ``skill_ab/fixtures``, or a sample's by its path from ``models/``; ``FILE.py => DEST.step`` builds
that model and exports it) and ``id:``
(``SCRIPT::FUNCTION``, whose document id replaces ``{ID}`` in the request), then ``## Request`` (what the
person asks, copied into the brief) and ``## Expect`` (the objective answer, never shown to the agent).

The standard library and the checkout's own ``cad``. Its output is never committed.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
HOME = Path(__file__).resolve().parent / "skill_ab"
#: The checkout's own cad: what this script builds fixtures with and what a run's env.sh puts first on PATH.
BIN = REPO / ".venv" / "bin"
BRIEF = """# Brief

You are completing a task for a person, using an installed skill (a folder of instructions for a tool). Work as
you would for a real person who is waiting on the result.

## Rules of this run

- The skill to use is `{run}/skills/{skill}/SKILL.md`. Read it before anything else, then the reference files it
  points you to as you need them. Where it sends you to another skill, that one is beside it.
- That skill folder is your only documentation: read no other directory on this machine for documentation,
  source, examples or tests, and no installed package's source. `cad <command> --help` is allowed.
- Work in `{run}/work` and keep every file you make there.
- Start every shell command with `. {run}/env.sh;` so that `cad` talks to this run's own server. cad is
  installed: skip any install or update step.
- There is no browser and nobody to ask. Where the skill says to show the person something, state the link or
  path you would give them. Make reasonable assumptions and say what they were.

## The person's request

{request}

## When you are done

Stop this run's server (`. {run}/env.sh; cad server stop`). Then reply, in under 350 words, with three sections:
**Reply** (what you would tell the person: what you made or found, the files, the checks you ran and what they
showed, your assumptions); **Commands** (the `cad` commands you ran, in order, marking any that failed and why);
**Skill notes** (anything in the skill that was unclear, missing or wrong, or that you had to find by trial, and
the skill files you opened).
"""


def parse(path: Path) -> dict:
    """A task file as ``{"skill", "fixtures", "id", "request", "expect"}``."""
    head, _, rest = path.read_text(encoding="utf-8").partition("## Request")
    request, _, expect = rest.partition("## Expect")
    fields = dict(line.split(":", 1) for line in head.splitlines() if ":" in line)
    if "skill" not in fields or not request.strip() or not expect.strip():
        raise SystemExit(f"{path}: a task needs `skill:`, `## Request` and `## Expect`")
    return {"skill": fields["skill"].strip(), "id": fields.get("id", "").strip(), "request": request.strip(),
            "expect": expect.strip(), "fixtures": [item.strip() for item in fields.get("fixtures", "").split(",")
                                                    if item.strip()]}


def environment(run: Path) -> dict[str, str]:
    """A run's own server: its engine, state and cache folders, no update and no telemetry, and one worker with
    no standby, since a bench has a server a run and they share one machine's memory."""
    return {"CAD_ENGINE_DIR": str(run / ".cad/engine"), "CAD_STATE_DIR": str(run / ".cad/state"),
            "CAD_CACHE_DIR": str(run / ".cad/cache"), "CAD_UPDATE_CHECK": "0", "CAD_TELEMETRY": "0",
            "CAD_ENGINE_WORKERS": "1", "CAD_ENGINE_STANDBY": "0"}


def exported(model: Path, scratch: Path) -> Path:
    """The STEP of the one model ``model`` builds, made once by a scratch server and kept for every run."""
    out = scratch / (model.stem + ".step")
    if out.exists():
        return out
    env = {**os.environ, **environment(scratch), "PATH": f"{BIN}{os.pathsep}{os.environ.get('PATH', '')}"}
    cad = str(BIN / "cad")
    subprocess.run([cad, "server", "start"], env=env, check=True, capture_output=True)
    try:
        built = subprocess.run([cad, "run", str(model)], env=env, check=True, capture_output=True, text=True)
        ids = [line.split("id:", 1)[1].strip() for line in built.stdout.splitlines() if line.strip().startswith("id:")]
        subprocess.run([cad, "model", "export", ids[0], str(out)], env=env, check=True, capture_output=True)
    finally:
        subprocess.run([cad, "server", "stop"], env=env, check=False, capture_output=True)
    return out


def skills_of(ref: str | None, into: Path) -> None:
    """The skills of ``ref`` (the working tree's for None) copied into ``into``."""
    if ref is None:
        shutil.copytree(REPO / "skills", into)
        return
    with tempfile.TemporaryDirectory() as scratch:
        archive = Path(scratch) / "skills.tar"
        subprocess.run(["git", "-C", str(REPO), "archive", "-o", str(archive), ref, "skills"], check=True)
        with tarfile.open(archive) as tar:
            tar.extractall(scratch, filter="data")
        shutil.copytree(Path(scratch) / "skills", into)


def prepare(run: Path, task: dict, ref: str | None, scratch: Path) -> None:
    work = run / "work"
    work.mkdir(parents=True)
    skills_of(ref, run / "skills")
    for fixture in task["fixtures"]:
        built = "=>" in fixture
        source, destination = (part.strip() for part in fixture.split("=>" if built else "->"))
        # A fixture is a file of this bench's own, or one of the repository's samples (``models/...``).
        source = REPO / source if source.startswith("models/") else HOME / "fixtures" / source
        (work / destination).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(exported(source, scratch) if built else source, work / destination)
    variables = environment(run)
    # The checkout's own cad comes first on PATH: an agent's shell has no cad of its own, or another release's.
    # The run's server is its own, so nothing has started it: sourcing this does, as a person's computer has one
    # running already (`cad server start` starts one where none runs, and joins the one that does).
    (run / "env.sh").write_text(f'export PATH="{BIN}:$PATH"\n'
                                + "".join(f"export {name}={value}\n" for name, value in variables.items())
                                + "cad server start >/dev/null 2>&1 || true\n",
                                encoding="utf-8")
    request = task["request"]
    if task["id"]:
        sys.path.insert(0, str(REPO / "packages/cad/src"))
        from cad.engine import ids

        script, function = task["id"].split("::")
        request = request.replace("{ID}", ids.model_id(work / script, function))
        # A request that names a document's id speaks of one the person has built: build it on the run's own
        # server, which keeps it, so the id resolves as it would on their computer.
        env = {**os.environ, **variables, "PATH": f"{BIN}{os.pathsep}{os.environ.get('PATH', '')}"}
        cad = str(BIN / "cad")
        subprocess.run([cad, "server", "start"], env=env, check=True, capture_output=True)
        try:
            subprocess.run([cad, "run", script], env=env, cwd=work, check=True, capture_output=True)
        finally:
            subprocess.run([cad, "server", "stop"], env=env, check=False, capture_output=True)
    (run / "BRIEF.md").write_text(BRIEF.format(run=run, skill=task["skill"], request=request), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--base", default="main", help="the Git ref whose skills are the baseline (default: main)")
    parser.add_argument("--task", action="append", help="a task's name; repeat it (default: every task)")
    parser.add_argument("--out", type=Path, default=REPO / "tmp/skill-ab", help="where the runs are laid out")
    args = parser.parse_args(argv)
    tasks = {path.stem: parse(path) for path in sorted((HOME / "tasks").glob("*.md"))}
    chosen = args.task or sorted(tasks)
    unknown = sorted(set(chosen) - set(tasks))
    if unknown:
        parser.error(f"no task named {', '.join(unknown)}: there are {', '.join(sorted(tasks))}")
    out = args.out.resolve()
    if out.exists():
        parser.error(f"{out} is there already: remove it, or name another folder with --out")
    (out / ".fixtures").mkdir(parents=True)
    rows, number = [], 0
    for name in chosen:
        # The variants alternate which gets the lower number, so a folder's name says nothing of its skills.
        for variant in (("base", "head") if len(rows) % 4 == 0 else ("head", "base")):
            number += 1
            run = out / f"r{number:02d}"
            prepare(run, tasks[name], args.base if variant == "base" else None, out / ".fixtures")
            rows.append(f"r{number:02d}\t{variant}\t{name}\t{tasks[name]['expect']}")
            print(f"{run}/BRIEF.md")
    (out / "runs.tsv").write_text("run\tskills\ttask\texpect\n" + "\n".join(rows) + "\n", encoding="utf-8")
    print(f"\n{len(rows)} runs laid out in {out}: give each BRIEF.md to a fresh agent, then grade against runs.tsv")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
