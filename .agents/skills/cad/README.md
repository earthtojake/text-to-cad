<div align="center">

<img src="assets/text-to-cad-demo.gif" alt="Demo of the text-to-cad harness generating and previewing CAD geometry" width="100%">

<br>

# ⚙ CAD Skill ⚙

CAD workflows to programatically generate STEP/STL/3MF/DXF/GLB files; regenerate, inspect, validate, snapshot, resolve @cad refs, and hand off CAD Explorer links.

</div>

The CAD skill generates, regenerates, inspects, validates, snapshots, and hands off CAD models for local coding-agent workflows. It is the CAD engine inside the [text-to-cad harness](https://github.com/earthtojake/text-to-cad) and can also be used standalone in any project with the required Python runtime.

The skill operates on explicit source files and imported STEP/STP files. It does not assume a project root or directory layout; relative targets are resolved from the directory where you run the command.

## ✨ Features

- **Generate** - Create source-controlled CAD models from Python generator files.
- **Export** - Produce STEP, STL, 3MF, DXF, GLB, and topology artifacts from generated or imported CAD targets.
- **Browse** - Inspect generated geometry with the bundled CAD Explorer web app.
- **Reference** - Copy and resolve stable `@cad[...]` handles for precise follow-up edits.
- **Review** - Render quick snapshots and deterministic summaries during an iteration loop.
- **Reproduce** - Edit source or imported STEP/STP files first, then regenerate explicit targets.
- **Local** - Run the skill and CAD Explorer locally with no hosted backend.

## 🔁 Workflow

1. **Describe** - Ask your coding agent for the part, assembly, fixture, mechanism, or CAD edit you want.
2. **Edit** - Update the owning Python generator or imported STEP/STP source file.
3. **Regenerate** - Run the explicit STEP, STL, 3MF, DXF, GLB, or topology target.
4. **Inspect** - Open CAD Explorer or render snapshots to review the result.
5. **Reference** - Use `@cad[...]` handles when a follow-up prompt depends on specific faces, edges, corners, bodies, or occurrences.
6. **Commit** - Save source and generated artifacts together once the model is ready.

## 🚀 Quick Start

Inside the text-to-cad harness, this bundled skill lives at `.agents/skills/cad`. In a standalone install, replace `.agents/skills/cad` with the path to the skill checkout.

Install Python CAD dependencies:

```bash
python3.11 -m venv .venv
./.venv/bin/python -m pip install --upgrade pip
./.venv/bin/pip install -r .agents/skills/cad/requirements.txt
```

Install CAD Explorer dependencies:

```bash
npm --prefix .agents/skills/cad/explorer install
```

Run CAD Explorer from the project directory you want to scan:

```bash
npm --prefix .agents/skills/cad/explorer run dev:ensure
```

Then open [http://localhost:4178](http://localhost:4178).

## 🧰 Core Commands

Run commands from the project that owns the target files:

```bash
python <cad-skill>/scripts/gen_step_part/cli.py path/to/part.py
python <cad-skill>/scripts/gen_step_assembly/cli.py path/to/assembly.py --summary
python <cad-skill>/scripts/gen_dxf/cli.py path/to/drawing.py
python <cad-skill>/scripts/cadref/cli.py inspect '@cad[path/to/entry]' --json
python <cad-skill>/scripts/snapshot/cli.py path/to/.part.step/model.glb --view isometric --out /tmp/cad-review.png
```

The command interfaces are target-explicit. Generation tools write and overwrite their configured outputs, but they do not delete stale outputs when paths change.

## 📚 References

Use [SKILL.md](SKILL.md) for agent-facing workflow rules. Detailed command contracts live in [references/](references/):

- STEP part generation: [gen-step-part.md](references/gen-step-part.md)
- STEP assembly generation: [gen-step-assembly.md](references/gen-step-assembly.md)
- DXF generation: [gen-dxf.md](references/gen-dxf.md)
- Generator and imported STEP/STP contracts: [generator-contract.md](references/generator-contract.md)
- Geometry edit workflow: [geometry-workflow.md](references/geometry-workflow.md)
- Prompt references: [prompt-refs.md](references/prompt-refs.md)
- Validation and snapshots: [validation-and-snapshots.md](references/validation-and-snapshots.md)
- `@cad[...]` inspection: [cadref.md](references/cadref.md)
- Snapshot rendering: [snapshot.md](references/snapshot.md)
- Shared implementation notes: [common-library.md](references/common-library.md)

## 🧭 Project Harness

The text-to-cad harness is intentionally thin: it gives a local project a repo, setup commands, project notes, and bundled skills. This CAD skill owns the reusable CAD workflow, command references, prompt-reference grammar, CAD Explorer app, and validation tooling.

Keep project inventory, durable quirks, and preferred rebuild roots in project-local notes such as `PROJECT.md` or `AGENTS.md`. Keep reusable CAD workflow rules in this skill.
