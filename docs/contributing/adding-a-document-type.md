# Adding a document type

A **document type** is what is in a file: one lowercase underscore id, the same in Python, the CLI,
the registry, the server, the viewer and the JavaScript. The definitions and the laws they bind
are the library's README ([`packages/cad/README.md`](../../packages/cad/README.md), **Definitions**
and laws 24 to 28); the mechanism is the engine README's **Document types and integrations**
([`packages/cad-server/src/cad_server/engine/README.md`](../../packages/cad-server/src/cad_server/engine/README.md)).

A type usually arrives with the tool that makes or checks it. That tool is an **integration**, and
adding one has its own guide: [Adding an integration](adding-an-integration.md). The
[walkthrough](#walkthrough-a-type-and-its-integration-together-kicad) below adds both at once, with
KiCad's boards as the example.

How an integration gets installed on a person's computer is not covered yet: no release installs
one on demand, and this guide does not decide how one will.

## Checklist

- [ ] **The id.** Lowercase, a valid Python name, the tool's own word for the format where it has one
      (`kicad_pcb`, not `pcb`; `threemf`, because `3mf` is no Python name). It never changes.
- [ ] **The registry entry**, in `packages/cad/src/cad/registry.py` (`_TYPES`): the id, its title, a
      one-line summary, its extensions (the first the one a written file takes), its MIME type, how it
      is viewed (`document`, `mesh`, `drawing`, `robot`, `plot`), the content it carries, its
      operations (from `export`, `snapshot`, `inspect`, `check`, each with the integration it needs),
      and whether it has a decorator or a reader. `wire` only if a released protocol already spells it
      otherwise; a new type never needs one.
- [ ] **Regenerate the JavaScript**: `python -m cad.registry --js >
      packages/core/src/lib/documentTypes.generated.js`. `tests/python/packages/cad/test_registry.py`
      fails until you do.
- [ ] **The type's package**, `packages/cad/src/cad/<id>/__init__.py`, ending in
      `_bind(__name__)` (`cad._internal.document_type`). Put here only what takes paths, plain values
      or our own types (the signature rule): its reader, its `check`, its standard's own vocabulary.
      It imports no third-party library; a helper that takes a tool's objects is that integration's.
      Add the id to `cad._TYPES` in `packages/cad/src/cad/__init__.py`.
- [ ] **Its operations.** Every operation it lists must run, as a function (`cad.<id>.<operation>`)
      and as a command (`cad <id> <operation>`). `export`, `snapshot` and `inspect` of a file the
      engine reads are the engine's verbs; a `check` is the type's own function, answering
      `cad.results.CheckResult` (findings with a severity, a code and a location). A new operation
      name is a change to the fixed set: it must be code-free, frequently needed and meaningful across
      types.
- [ ] **Its command module**, `packages/cad-server/src/cad_server/cli/<id>.py`, the same three lines
      as every other type's; options of its own live with the type
      (`cad_server/cli/document_types.py`). Pin it in
      `tests/python/packages/cad_server/test_cli_commands.py`.
- [ ] **The viewer.** A renderer for its view in `packages/ui/src/renderers/` (or an existing one's
      registration, `packages/ui/docs/renderers.md`), its icon (`renderCapabilities.js` reads the view),
      and, for a view the server resolves, the route its kind answers (`cad_server/viewer/http_app.py`
      reads `_VIEW_ROUTES` by view).
- [ ] **The receiver.** A new kind crosses the analytics wire: add it to `apps/api/src/events.mjs`
      in a new schema version; `tests/python/global/test_telemetry_vocabulary_sync.py` holds the two
      together.
- [ ] **Tests**, at the cheapest level that exercises the real path: the reader and the checks on
      fixtures the test builds in a temporary folder (never `models/`), the command's refusals, a
      renderer unit. Every test is reached by a runner under `scripts/test/` and a `test.yml` job.
- [ ] **CI selection.** A test that reads a new kind of path gets a rule in
      `scripts/github-workflows/select_checks.py`; `tests/python/global/test_ci_workspace_selection.py`
      checks the table against the tree.
- [ ] **Docs to touch**: the library README's **Definitions** (the list of ids) and its shape of the
      package, the engine README's **CLI**, the server README's **Commands**, the skill that teaches
      the type, the README and the docs site's homepage (`apps/docs/src/lib/content.ts`) if they list
      formats, and `AGENTS.md` only if a repo-level rule changed.

## Walkthrough: a type and its integration together (KiCad)

This pull request adds KiCad's boards: the `kicad_pcb` document type and the `kicad` integration
that runs KiCad's own command, `kicad-cli`. Each step names the checklist it belongs to.

1. **Is KiCad an integration?** Yes, by the definition test ([Adding an
   integration](adding-an-integration.md#is-it-really-an-integration)): our code runs `kicad-cli` for
   design-rule checks and fabrication exports. It is kind C, an external program our code runs.
   Reading a `.kicad_pcb` file is not KiCad's code but ours, for a file format: that is the document
   type's, not the integration's.
2. **The integration's entry** (`INTEGRATIONS["kicad"]`): process kind `separate`, the probe
   `kicad-cli` with the minimum version our exports need and the install hint the server says when it
   is missing, and `CAD_KICAD_CLI` as the variable that names it outright. No extra yet: nothing is
   installed with pip for it, and a packaged `kicad-cli` is a later change.
3. **The type's entry** (`DOCUMENT_TYPES["kicad_pcb"]`): `.kicad_pcb`, viewed as a `plot`, its content
   (the board's layers, footprints and pads, nets, tracks, vias and zones, its outline), and its
   operations: `snapshot` and `inspect` our own code's, `check` and `export` the `kicad` integration's.
   No decorator: what would write a board from a model's code depends on how the integration's
   program runs in a build, which is open.
4. **The type's package**, `cad/kicad_pcb/`: `read_board(path)` and `inside(...)`, which take paths and
   our own board objects, so they are the type's (the signature rule); `snapshot` and `inspect`, the
   library's board renderer and summary. `check` and `export` run `kicad-cli`, which the server runs,
   not a model's process: as functions they raise, naming the command (`cad kicad_pcb check`), since
   making them work in Python needs an operation of the engine's, which is open.
5. **The commands**: `cad kicad_pcb check BOARD` (KiCad's DRC: it fails on errors or unconnected items,
   says the warnings, and answers `kicad_failed` when KiCad refuses the board), `cad kicad_pcb export
   BOARD --to gerbers|drill|pos|step -o DIR`, `cad kicad_pcb snapshot` and `cad kicad_pcb inspect`
   (its parts, nets and layers).
6. **The external program**: the server's one helper for programs our code runs
   (`cad_server/_internal/programs.py`) finds `kicad-cli` by its override, then `PATH`, then the
   places KiCad installs it, checks the minimum version, runs it headless with a private home, and
   says one line when it is missing. Every rule that keeps a desktop app out holds and is tested: only
   `kicad-cli` (`kicad-cli.exe`) is ever run, an override of any other name is refused, no
   `DISPLAY` or `WAYLAND_DISPLAY` reaches it, and Open in refuses a `.kicad_*` file.
7. **The viewer**: the board renderer (`packages/ui/src/renderers/board/`), the plot payload the
   server resolves (`cad_server/viewer/plots.py`), its icon, and the `plot` route of its kind.
8. **Tests and CI**: board fixtures written by the tests, the commands' refusals, the parity of the
   board-reference grammar between Python and JavaScript, and a CI job that installs KiCad, with its
   cost stated in the pull request.
