# Adding an integration

An **integration** is our support for one third-party tool: an extra (`cad[<name>]`), our code for
the tool, and a process kind. The words and the laws are the library's README
([`packages/cad/README.md`](../../packages/cad/README.md), **Definitions** and laws 22 to 29). How the
registry, the commands and each integration's operations work is the engine's
[Document types and integrations](../../packages/cad/src/cad_server/engine/docs/document-types-and-integrations.md),
and how an extra reaches a person's computer its
[Running a model](../../packages/cad/src/cad_server/engine/docs/running-a-model.md). This guide says
what to decide and what to touch. It records what the integrations so far needed, and is no template
for the next.

## Start from the tool

Three questions decide most of it.

1. **What does the tool already do, and how is it reached?** Its Python API, its command line, its own
   app. All of that stays the tool's: a script imports it, `cad run <its command>` runs it, a person
   opens its app. We add nothing that renames or repeats it (law 28).
2. **Who looks at its files?** A file cad shows, in the viewer, the CAD app and a snapshot, is a
   document type ([Adding a document type](adding-a-document-type.md)). A file the tool's own app
   shows, which cad only writes or checks, is not: it is the integration's, with at most an operation
   of its own. An MJCF is one: MuJoCo Studio shows it, so there is no `cad mjcf`, and its check is
   `cad mujoco check`.
3. **What is missing without us?** Name it: a result every check shares, a guarantee the tool does not
   give, a fact it does not report, the tie between its objects and our documents. That is the whole
   of what we write. If nothing is missing, the skill teaches the tool as it is and there is no
   integration to add. Check what the tool itself does before writing code around its files:
   `cad orcaslicer` completed presets from OrcaSlicer's own folders, could not once OrcaSlicer kept
   them in binary caches, and is deprecated.

What those answers gave so far:

| Integration | What the tool already has | What we add, and why |
| --- | --- | --- |
| `build123d` | the modelling API a model is written in | the model API over it, the memo, element names, the producers of every type with a decorator: the engine's documents are made from its shapes |
| `kicad` | `kicad-cli` and an IPC API; its own editors | a board's and a schematic's `drc`, `erc` and `export` as typed commands with one result shape and the project left as found; an edit of a saved file through its API. Everything else is `cad run kicad-cli ...` |
| `trimesh` | mesh measurements as a library | a mesh's 3D printing check: the measurements judged against cited rules, in the shape every manufacturing check answers |
| `netgen`, `calculix` | a mesher, a solver | a B-rep type's `solve`: the study read, the document meshed and solved, the results as standard files |
| `coacd` | convex decomposition of a mesh | nothing a person calls: it backs `cad.mujoco.decompose`, run in a process of its own, its hulls kept in the cache |
| `blender` | all of Blender as a Python module, `bpy` | one helper, `cad.blender.load`: a GLB cad wrote, in Blender's scene, with each node's object by its name and its clips to play. The framing, the lights and the render are `bpy`'s own, in the script. No document type and no command |
| `mujoco` | a compiler, a simulator, `MjSpec`, MuJoCo Studio | a document as an `MjSpec`, a part's collision chosen by its label path, a spec saved as a folder that travels, and one operation on a file that is no document type, `cad mujoco check`. No reader, no viewer and no still of an MJCF: Studio shows one |

An integration that makes or checks a document type is added with that type: the type's guide has a
[walkthrough](adding-a-document-type.md#walkthrough-a-type-and-its-integration-together-kicad) of
KiCad's boards and the `kicad` integration together.

## Is it really an integration?

cad supports a tool only where cad's own code calls it (law 24). A dependency, one package or binary,
is named in `pyproject.toml` and the lock file alone, never in the API, the CLI or the docs, until we
write code for that tool: OCP is a dependency of `build123d`, not an integration.

| Kind | What it is | Examples | An integration? |
| --- | --- | --- | --- |
| A | Python libraries model code imports | build123d, mujoco, pandas | yes, where we write helpers that take its objects or producers of its values |
| B | Python libraries our producers call | ezdxf, Pillow, netgen | yes, where the code that calls it is ours for that tool |
| C | External programs our code runs | kicad-cli, ccx, freecadcmd | yes: a probe, headless runs, one missing-tool result |
| D | Tools only the agent runs | a slicer's CLI the agent calls | no: the skill teaches the tool's own command line and what its app exports, and cad's code never calls it |
| E | Remote services | a quoting API | no |
| F | Desktop apps the person uses, which cad never launches | KiCad's editor, FreeCAD's GUI | no: Open in hands the file to it, nothing more |

## Checklist

- [ ] **The three questions**, [above](#start-from-the-tool), answered in the pull request.
- [ ] **The definition test**: name the code of ours that calls the tool, or makes the file it needs
      and cannot make. If there is none, it is not an integration; if the code is ours for a file
      format cad shows, it is a document type's.
- [ ] **The purpose test**, for each helper and each command we add: say what is missing without it.
      One that renames the tool's own function or command, or does again what the tool does, is not
      added (law 28).
- [ ] **The name**: the tool's own project name, lowercase, a Python name. Never a capability
      (`fea`, `pcb`, `cam`).
- [ ] **The extra and its pins**, in `packages/cad/pyproject.toml` (`[project.optional-dependencies]`):
      exactly the packages our code for it imports, each bounded as the `build123d` extra's are, with a
      comment saying why. Take the smallest distribution that carries it and stays headless
      (`mujoco-core` and `mujoco-studio`, never the `mujoco` meta-package, which adds a native
      window). A tool with no build for some Python or platform carries markers that install it only
      where it has one (`blender`: `bpy` has wheels for Python 3.13 alone). Then run `uv lock`: CI
      installs with `uv sync --locked`. Add the extra to the root `pyproject.toml`'s `dev` group only
      if the package suites need it there.
- [ ] **The registry entry**, `INTEGRATIONS` in `packages/cad/src/cad/registry.py`, whose `Integration`
      class says what each field is:
      - `name`, `summary`, `extra`, the process kind (`in-process`, `separate`, `both`);
      - with an extra, `modules` (the top-level modules a script imports it by, from which `cad run`
        picks the extra), `distributions` (the extra's requirements, by name), `identity` (the
        distributions that are the tool itself, other builds of its modules among them), and `holds`
        and `download_mb`, said as its environment is made;
      - `alongside`, the integrations its operations need in the same environment (calculix's: the
        kernel, which reads the B-rep a study solves, and netgen, which meshes it);
      - `python`, `platforms` and `homes`, only for what its tool alone decides of its environment: the
        one Python line it is built for, its platforms (`cad.registry.PLATFORMS`' words) and the
        variables naming its own settings folders, which a run points at private folders;
      - `commands`, the tool's own command lines its extra installs;
      - for an external program, its `Probe`;
      - only for the tool's own files that are no document type, `operations` and the `files` those
        that take one file take (`FILE_OPERATIONS`).

      `python -m cad.registry <name>` prints the entry's help. `cad run`'s choice of extra and
      `cad doctor`'s line for the integration come from the entry, with nothing more to write.
- [ ] **An operation of its own**, only for such files: a function `cad.<name>.<operation>` that is
      fully annotated and answers its operation's one result (a check's findings), named from the
      closed set (`cad.registry.INTEGRATION_OPERATIONS`), and its command
      `cad <name> <operation> [FILE]`, generated from the function (`cad_server/cli/integrations.py`).
      Its module, `cad_server/cli/<name>.py`, is a copy of `cli/mujoco.py` with the name changed. Pin
      both in `tests/python/packages/cad/test_registry.py` and, under
      `tests/python/packages/cad_server/`, `test_cli_commands.py` and `test_public_surface.py`. A file
      that has a document type has its operations there, never here (law 26).
- [ ] **Our code**, in `packages/cad/src/cad/<name>/` for the library's side (helpers that take the
      tool's objects; producers in `_producers.py`, gathered in `cad.registry._producers`), and in the
      server for a program the server runs. It imports only its own extra's dependencies and
      re-exports nothing of the tool. `tests/python/packages/cad_server/test_core_imports.py` holds
      the package to the registry: add the name to `cad._INTEGRATIONS`
      (`packages/cad/src/cad/__init__.py`) and the modules the extra brings to the test's
      `EXTRA_MODULES`; it also holds `distributions`, `python` and `platforms` to the extra's
      requirements and markers. Code of an engine process whose environment lacks the extra runs in a
      process of its own, in the environment the engine makes for it (`coacd`'s decomposer,
      `cad.engine.hulls`).
- [ ] **Producer registration.** Each producer is `(type, matcher, writer, integration)`, with what it
      accepts and which parts of the type's content it provides; it regenerates a file from what a
      model returns. A tool that changes a native file in place is no producer but the type's edit
      (`cad.registry.Edit`, `<type>.edit`, a `with` block: KiCad's `kicad_pcb.edit`). A matcher reads
      type names and modules, never imports the library. Exactly one producer per return type per
      document type (`tests/python/packages/cad/test_registry.py`).
- [ ] **An external program's probe and headless rules.** The program comes with the extra where it
      ships as a Python package (KiCad's `kicad-cli`, in kicode; CalculiX's `ccx`, in the cad-ccx
      package). Where it ships none, packaging it, its own binary unmodified in a wheel per platform
      with a launcher that names where it is, is usually better than asking a person to install it
      (`earthtojake/ccx` is that for CalculiX); otherwise the integration has no extra and the person
      installs the program. It is found and run through the library's one helper
      (`packages/cad/src/cad/_internal/programs.py`, the standard library alone, which the server's
      commands import too): the extra's own copy, never one on `PATH` (`search_path=False`), or, for a
      program a person installs, `PATH`, then the places the tool installs itself; its minimum
      version checked; run headless with a private home and no display; one missing-tool result
      saying the install hint. Only the program itself is ever run, never a desktop app or a wrapper
      that starts one; test each rule. A variable that names another copy (`CAD_KICAD_CLI`, `CAD_CCX`) is
      the last resort where the pinned copy does not run on a person's computer: add one only for a
      program the extra carries (the registry's probe, `override`), and name it in the refusal for a
      missing program.
- [ ] **The tool's own commands**, when its extra puts a command line in an environment (kicode's
      `kicad-cli`): name each in the registry entry's `commands`, and give the integration a `_command`
      module (`cad/<name>/_command.py`, `main(argv)`, argv the command's name and its arguments) that
      runs it headless in the integration's private homes, the environment's own command (the one
      beside its Python) and never one on `PATH`, its arguments, stdio and exit code the tool's.
      `cad run <command> …` then makes the integration's environment and runs that module there
      (`cad.kicad._command` is the example), and the skill documents the tool's command line as
      `cad run <command> …`. Test that the bare command adds the integration, in the unit suite, and
      that it runs, in the job that installs the tool.
- [ ] **Licensing**: the tool's license allows how we call it (a library we import, a program we run)
      and how it would ship; say which in the pull request.
- [ ] **Tests and a CI job.** A test that needs the tool runs only in the job that installs it, and
      says so by name where it skips. That job is reached by a runner under `scripts/test/` and
      selected in `scripts/github-workflows/select_checks.py`, and its pull request says what it costs
      ([Adding a CI job](testing.md#adding-a-ci-job)).
- [ ] **Docs to touch**: the library README's **Definitions** (the list of names) and its shape of the
      package, and the engine's Document types and integrations page for what the integration runs.
- [ ] **Skill notes**: the skill that uses it says what the tool is and when it is fetched, after its
      setup block (the setup block itself is the shared text every skill carries word for word).
- [ ] **The docs site's copy of the registry**: regenerate it (`python -m
      cad.registry --docs > apps/docs/src/lib/docs/registry.generated.json`,
      which `tests/python/packages/cad/test_registry.py` holds to the table).
