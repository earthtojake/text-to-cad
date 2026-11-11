# Adding an integration

An **integration** is our support for one third-party tool, named for the tool's own project
(`build123d`, `kicad`, `trimesh`, `mujoco`, `coacd`, `netgen`, `calculix`, `blender`), never for a capability.
It is three things: one extra, `cad[<name>]`, grouping the dependencies our code for it needs; our code for it --
helpers that take its objects, producers and operations; and a process kind: in-process, separate
process, or both. The definitions and laws are the library's README
([`packages/cad/README.md`](../../packages/cad/README.md), **Definitions** and laws 24 to 29); the
mechanism is the engine README's **Document types and integrations**.

## Start from the tool

This guide records what the integrations so far needed. It is a checklist for a tool like one of
them and not a template for the next: read it, and the laws, with a grain of salt, and decide what is
best for this tool before fitting it to either. Three questions decide most of it.

1. **What does the tool already do, and how is it reached?** Its Python API, its command line, its own
   app. All of that stays the tool's: a script imports it, `cad run <its command>` runs it, a person
   opens its app. We add nothing that renames or repeats it (law 30).
2. **Who looks at its files?** A file cad shows, in the viewer, the CAD app and a snapshot, is a
   document type ([Adding a document type](adding-a-document-type.md)). A file the tool's own app
   shows, which cad only writes or checks, is not: it is the integration's, with at most an operation
   of its own.
3. **What is missing without us?** Name it: a result every check shares, a guarantee the tool does not
   give, a fact it does not report, the tie between its objects and our documents. That is the whole
   of what we write. If nothing is missing, the skill teaches the tool as it is and there is no
   integration to add.

The integrations so far came out in different shapes, each from those answers:

| Integration | What the tool already has | What we add, and why |
| --- | --- | --- |
| `build123d` | the modelling API a model is written in | the model API over it, the memo, element names, the producers of every type with a decorator: the engine's documents are made from its shapes |
| `kicad` | `kicad-cli` and an IPC API; its own editors | a board's and a schematic's `drc`, `erc` and `export` as typed commands with one result shape and the project left as found; an edit of a saved file through its API. Everything else is `cad run kicad-cli ...` |
| `trimesh` | mesh measurements as a library | a mesh's 3D printing check: the measurements judged against cited rules, in the shape every manufacturing check answers |
| `netgen`, `calculix` | a mesher, a solver | a B-rep type's `solve`: the study read, the document meshed and solved, the results as standard files |
| `coacd` | convex decomposition of a mesh | nothing a person calls: it backs `cad.mujoco.decompose`, run in a process of its own, its hulls kept in the cache |
| `blender` | all of Blender as a Python module, `bpy` | one helper, `cad.blender.load`: a GLB cad wrote, in Blender's scene, with each node's object by its name and its clips to play. The framing, the lights and the render are `bpy`'s own, in the script. No document type and no command |
| `mujoco` | a compiler, a simulator, `MjSpec`, MuJoCo Studio | a document as an `MjSpec`, a part's collision chosen by its label path, a spec saved as a folder that travels, and one operation on a file that is no document type, `cad mujoco check` (below). No reader, no viewer and no still of an MJCF: Studio shows one |

An integration that makes or checks a document type is added with that type, and the type's guide has
a [walkthrough](adding-a-document-type.md#walkthrough-a-type-and-its-integration-together-kicad) that
adds KiCad's boards and the `kicad` integration together.

## The smaller shapes

`mujoco` makes a document a `mujoco.MjSpec`, checks a MuJoCo model's file and shows the person a
model. Its
extra, `cad[mujoco]`, is `mujoco-core` (MuJoCo's compiler and Python bindings, numpy their one dependency)
and `mujoco-studio` (MuJoCo Studio, whose web viewer serves the page from Python: websockets beside the
core's, no GL), about 20 MB, headless, Apache-2.0. Never `mujoco` itself, a meta-package that adds glfw and
PyOpenGL for Studio's native window (a display and a GPU an agent's sandbox has neither of), nor the
menagerie. Studio is the integration's command (`commands=("mujoco-studio",)`, `cad.mujoco._command`): `cad
run mujoco-studio --model scene.xml` serves the model in Studio's web viewer, reloading it as the file
changes, for the person to open at the URL it prints. MuJoCo 4.0's web viewer listens on every interface
with no host to choose, so the run says so first. The compile is in-process: `cad.mujoco._compile` loads the model
with `MjModel.from_xml_path` and turns what MuJoCo refuses and warns into findings.

An MJCF is the example of **a file that is no document type**. A document type is a file cad shows
(the viewer, the CAD app, a snapshot); cad writes an MJCF and asks MuJoCo about one, and MuJoCo Studio
shows it. So it has no `cad mjcf` command and nothing reads it but MuJoCo. What cad does with it is the
integration's own operation: `cad.mujoco.check(path)`, and `cad mujoco check FILE`, its command
(`cad_server/cli/integrations.py`), generated from the function's signature, run in this process where
its environment holds mujoco, else in the environment of `cad[mujoco]`, made once by the engine
(`integration_env`). The registry entry names both: `operations=(Operation("check", ...),)` and
`files=(".xml", ".mjcf")`. Give an integration an operation only for such a file: one that has a document
type has its operations there (law 28). A script that imports `mujoco` gets the extra from `cad run`
through the registry entry's `modules`.

How an integration gets installed on a person's computer is covered for a Python library alone: `cad
run` makes a program's environment with the integrations its imports use, and an operation the `cad`
command runs that needs one its own environment lacks (a mesh's `dfm`, the `trimesh`
integration's) runs in the environment of that integration, made once by the engine the same way
(`cad_server/_internal/integration_env.py`); an integration whose operations need another beside it says
so in the registry (`alongside`), and its environment holds them all (a B-rep type's `solve` reads the
document with the kernel, meshes it with netgen and solves it with CalculiX: the environment of
`cad[build123d,calculix,netgen]`). A process of the engine's own that needs an integration its environment lacks
asks the engine for that environment over its door (`{"op": "integration"}`, `integration_env.made`), which makes
it the same way and answers its Python, and runs the integration's code there in a process of its own: a worker's
decomposition of a collision, the `coacd` integration's (`cad.engine.hulls`), so no model names `cad[coacd]` in its
header. An external program that ships as a Python package (KiCad's `kicad-cli`, in
kicode; CalculiX's `ccx`, in the cad-ccx package) is its integration's extra and installs the same way; any other is
the person's to install, found by its probe: an integration with no extra and a probe alone. When a program
ships no package, packaging it, its own binary unmodified in a wheel per platform with a launcher that names
where it is, is usually better than asking a person to install it (`earthtojake/ccx` is that for CalculiX). `cad doctor` says, for each integration with an extra but build123d (the
kernel's own line), whether this installation carries it or where its environment is and whether it is
made (`integration_env.found`, read and never made); a new integration gets its line from the registry.

**A tool built for one Python, or not for every platform.** Such a tool is an integration like any other:
an extra, a namespace, an environment with `cad` pinned in it. Its extra's markers install it only where it
has a build, and nothing anywhere else (Blender's `bpy`: cp313 wheels alone, none for Intel Macs or Linux
arm64), and its registry entry says the same, which a test holds to the markers: the one Python line it is
built for (`python="3.13"`) and its platforms (`platforms`, `cad.registry.PLATFORMS`' words), with the
variables that name its own settings folders (`homes`). `cad run`
makes an environment with it on that line (a Python uv manages, where the engine's own is another), points
those variables at private folders in the cache, and refuses in one line a `--python` or a `requires-python`
that leaves the line out and a platform without a build. The packages' floor (`requires-python`) is the
oldest such line, so the library runs there; CI holds it with the library's suite on that Python
(`scripts/test/test-floor.sh`). `blender` is the example.

## Is it really an integration?

cad supports a tool only where cad's own code calls it. A **dependency** -- one package or binary --
becomes an integration only when we write code for that tool; it is named in `pyproject.toml` and
the lock files alone, never in the API, the CLI or the docs. OCP is a dependency of `build123d`, not
an integration.

| Kind | What it is | Examples | An integration? |
| --- | --- | --- | --- |
| A | Python libraries model code imports | build123d, mujoco, pandas | yes, where we write helpers that take its objects or producers of its values |
| B | Python libraries our producers call | ezdxf, Pillow, netgen | yes, where the code that calls it is ours for that tool |
| C | External programs our code runs | kicad-cli, ccx, freecadcmd | yes: a probe, headless runs, one missing-tool result |
| D | Tools only the agent runs | a slicer's CLI the agent calls | no: the skill teaches it, cad's code never calls it |
| E | Remote services | a quoting API | no |
| F | Desktop apps the person uses, which cad never launches | KiCad's editor, FreeCAD's GUI | no: Open in hands the file to it, nothing more |

## Checklist

- [ ] **The three questions**, [above](#start-from-the-tool), answered in the pull request: what the
      tool already does, who looks at its files, what is missing without us.
- [ ] **The definition test**, above: name the code of ours that calls the tool. If there is none, it
      is not an integration; if the code is ours for a file format cad shows, it is a document type's.
- [ ] **The purpose test**, for each helper and each command we add: say what is missing without it.
      One that renames the tool's own function or command, or does again what the tool does, is not
      added (law 30).
- [ ] **The name**: the tool's own project name, lowercase, a Python name. Never a capability
      (`fea`, `pcb`, `cam`).
- [ ] **The extra and its pins**, in `packages/cad/pyproject.toml` (`[project.optional-dependencies]`):
      exactly the packages our code for it imports, each bounded as the `build123d` extra's are, with a
      comment saying why. An external program needs no extra until it ships as a package. A tool with no
      build for some Python or platform carries markers that install it only where it has one (above).
- [ ] **The registry entry**, `INTEGRATIONS` in `packages/cad/src/cad/registry.py`: name, summary,
      extra, process kind (`in-process`, `separate`, `both`) and, for an external program, its `Probe`
      (the program, its minimum version, its install hint, the variable that names it outright); what
      only its tool decides of its environment, where it decides any (`python`, `platforms`, `homes`); and
      `alongside`, the integrations its operations need in the same environment (calculix's: the kernel,
      which reads the B-rep a study solves, and netgen, which meshes it), which the environment the `cad`
      command makes for it holds too; `commands`, the tool's own command lines its extra installs; and,
      only for a file of the tool's that is no document type, `operations` and the `files` they take.
- [ ] **An operation of its own**, only for such a file: a function `cad.<name>.<operation>` that is
      fully annotated and answers the result every check answers, named from the closed set
      (`cad.registry.INTEGRATION_OPERATIONS`), and its command `cad <name> <operation> FILE`, generated
      from the function (`cad_server/cli/integrations.py`, with the two-line module
      `cad_server/cli/<name>.py`). Pin both in `tests/python/packages/cad/test_registry.py`,
      `test_cli_commands.py` and `test_public_surface.py`. A file that has a document type has its
      operations there, never here.
- [ ] **Our code**, in `packages/cad/src/cad/<name>/` for the library's side (helpers that take the
      tool's objects; producers in `_producers.py`, gathered in `cad.registry._producers`), and in the
      server for a program the server runs. Add the name to `cad._INTEGRATIONS` when it has a
      namespace. It imports only its own extra's dependencies and re-exports nothing of the tool
      (`tests/python/packages/cad_server/test_core_imports.py`).
- [ ] **Producer registration.** Each producer is `(type, matcher, writer, integration)`, with what it
      accepts and which parts of the type's content it provides; it regenerates a file from what a model
      returns. A tool that changes a native file in place is no producer but the type's edit
      (`cad.registry.Edit`, `<type>.edit`, a `with` block: KiCad's `kicad_pcb.edit`). A matcher reads type names and
      modules, never imports the library. Exactly one producer per return type per document type
      (`tests/python/packages/cad/test_registry.py`).
- [ ] **An external program's probe and headless rules**: found through the library's one helper
      (`packages/cad/src/cad/_internal/programs.py`, the standard library alone, which the server's
      commands import too) -- the override, then `PATH` (never, for a program the extra carries:
      `search_path=False`), then the places the tool installs itself or the extra's package;
      the minimum version checked; run headless with a private home and no display;
      one missing-tool result saying the install hint. Only the program itself is ever run, never a
      desktop app or a wrapper that starts one; test each rule.
- [ ] **The tool's own commands**, when its extra puts a command line in an environment (kicode's
      `kicad-cli`): name each in the registry entry's `commands`, and give the integration a `_command`
      module (`cad/<name>/_command.py`, `main(argv)`, argv the command's name and its arguments) that
      runs it headless in the integration's private homes, the environment's own command first (the one
      beside its Python) and never one on `PATH`, its arguments, stdio and exit code the tool's. `cad
      run <command> …` then adds the extra as `--with cad[<name>]` would and runs that module in the
      integration's environment (`cad_server.cli.run`; `cad.kicad._command` is the example). A typed
      command wraps one only where it adds something (the library's law 30); the skill documents the
      rest as `cad run <command> …`. Test that the bare command adds the integration, in the unit suite,
      and that it runs, in the job that installs the tool.
- [ ] **Licensing**: the tool's license allows how we call it (a library we import, a program we run)
      and how it would ship; say which in the pull request.
- [ ] **A CI job** where its tests need the tool installed, reached by a runner under `scripts/test/`
      and selected in `scripts/github-workflows/select_checks.py`. Its cost goes in the pull request:
      CI time is a budget, and a change that lengthens a job says what it costs and why.
- [ ] **Tests** follow the repository's rules: every test reached by CI, fixtures built by the tests
      in temporary folders, never reading `models/`; a test that needs the tool runs only in the job
      that installs it, and says so by name where it skips.
- [ ] **Skill notes**: the skill that uses it says what the tool is and when it is fetched, after its
      setup block (the setup block itself is the shared text every skill carries word for word).
