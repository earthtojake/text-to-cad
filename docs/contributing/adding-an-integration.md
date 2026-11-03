# Adding an integration

An **integration** is our support for one third-party tool, named for the tool's own project
(`build123d`, `kicad`; later perhaps `netgen`, `calculix`), never for a capability. It is three
things: one extra, `cad[<name>]`, grouping the dependencies our code for it needs; our code for it --
helpers that take its objects, producers and operations; and a process kind: in-process, separate
process, or both. The definitions and laws are the library's README
([`packages/cad/README.md`](../../packages/cad/README.md), **Definitions** and laws 24 to 28); the
mechanism is the engine README's **Document types and integrations**.

An integration usually makes or checks a document type, and adding a type has its own guide:
[Adding a document type](adding-a-document-type.md), whose
[walkthrough](adding-a-document-type.md#walkthrough-a-type-and-its-integration-together-kicad) adds
KiCad's boards and the `kicad` integration together.

How an integration gets installed on a person's computer is covered for a Python library alone: `cad
run` makes a program's environment with the integrations its imports use, and an operation the `cad`
command runs that needs one its own environment lacks (a 3D type's `dfm`, the `trimesh`
integration's) runs in the environment of that integration, made once by the engine the same way
(`cad_server/_internal/integration_env.py`). An external program that ships as a Python package (KiCad's
`kicad-cli`, in kicode) is its integration's extra and installs the same way; any other is the person's to
install, found by its probe. `cad doctor` reports no integration.

## Is it really an integration?

cad supports a tool only where cad's own code calls it. A **dependency** -- one package or binary --
becomes an integration only when we write code for that tool; it is named in `pyproject.toml` and
the lock files alone, never in the API, the CLI or the docs. OCP is a dependency of `build123d`, not
an integration.

| Kind | What it is | Examples | An integration? |
| --- | --- | --- | --- |
| A | Python libraries model code imports | build123d, pandas | yes, where we write helpers that take its objects or producers of its values |
| B | Python libraries our producers call | ezdxf, Pillow, netgen | yes, where the code that calls it is ours for that tool |
| C | External programs our code runs | kicad-cli, ccx, freecadcmd | yes: a probe, headless runs, one missing-tool result |
| D | Tools only the agent runs | a slicer's CLI the agent calls | no: the skill teaches it, cad's code never calls it |
| E | Remote services | a quoting API | no |
| F | Desktop apps the person uses, which cad never launches | KiCad's editor, FreeCAD's GUI | no: Open in hands the file to it, nothing more |

## Checklist

- [ ] **The definition test**, above: name the code of ours that calls the tool. If there is none, it
      is not an integration; if the code is ours for a file format, it is a document type's.
- [ ] **The name**: the tool's own project name, lowercase, a Python name. Never a capability
      (`fea`, `pcb`, `cam`).
- [ ] **The extra and its pins**, in `packages/cad/pyproject.toml` (`[project.optional-dependencies]`):
      exactly the packages our code for it imports, each bounded as the `build123d` extra's are, with a
      comment saying why. An external program needs no extra until it ships as a package.
- [ ] **The registry entry**, `INTEGRATIONS` in `packages/cad/src/cad/registry.py`: name, summary,
      extra, process kind (`in-process`, `separate`, `both`) and, for an external program, its `Probe`
      (the program, its minimum version, its install hint, the variable that names it outright).
- [ ] **Our code**, in `packages/cad/src/cad/<name>/` for the library's side (helpers that take the
      tool's objects; producers in `_producers.py`, gathered in `cad.registry._producers`), and in the
      server for a program the server runs. Add the name to `cad._INTEGRATIONS` when it has a
      namespace. It imports only its own extra's dependencies and re-exports nothing of the tool
      (`tests/python/packages/cad_server/test_core_imports.py`).
- [ ] **Producer registration.** Each producer is `(type, matcher, writer, integration)`, with what it
      accepts and which parts of the type's content it provides. A producer whose decorator does more
      than the engine's model declares it (`declare`, for the targets `decorates` takes): KiCad's
      `@kicad_pcb` board script, and the `@step` stacked on one. A matcher reads type names and
      modules, never imports the library. Exactly one producer per return type per document type
      (`tests/python/packages/cad/test_registry.py`).
- [ ] **An external program's probe and headless rules**: found through the library's one helper
      (`packages/cad/src/cad/_internal/programs.py`, the standard library alone, which the server's
      commands import too) -- the override, then `PATH` (never, for a program the extra carries:
      `search_path=False`), then the places the tool installs itself or the extra's package;
      the minimum version checked; run headless with a private home and no display;
      one missing-tool result saying the install hint. Only the program itself is ever run, never a
      desktop app or a wrapper that starts one; test each rule.
- [ ] **Licensing**: the tool's license allows how we call it (a library we import, a program we run)
      and how it would ship; say which in the pull request.
- [ ] **A CI job** where its tests need the tool installed, reached by a runner under `scripts/test/`
      and selected in `scripts/github-workflows/select_checks.py`. Its cost goes in the pull request:
      CI time is a budget, and a change that lengthens a job says what it costs and why.
- [ ] **Tests** follow the repository's rules: every test reached by CI, fixtures built by the tests
      in temporary folders, never reading `models/`; a test that needs the tool runs only in the job
      that installs it, and says so by name where it skips.
- [ ] **Skill install notes**: the skill that uses it says how to get the tool, in its setup block,
      the way the server's setup block is said.
