# Adding a document type

A **document type** is a file cad shows: one lowercase underscore id, the same in Python, the CLI, the
registry, the server, the viewer and the JavaScript, with a view (`document`, `mesh`, `drawing`,
`robot`, `plot`), a place in the viewer and a snapshot. The words and the laws are the library's
README ([`packages/cad/README.md`](../../packages/cad/README.md), **Definitions** and laws 22 to 29);
how the registry, a type's object and its commands work is the engine's
[Document types and integrations](../../packages/cad/src/cad_server/engine/docs/document-types-and-integrations.md).

A file cad only writes or checks is no document type, however much cad does with it: give its tool's
integration an operation instead
([Adding an integration](adding-an-integration.md#start-from-the-tool), the second question). A type
usually arrives with the tool that makes or checks it, an integration with that guide of its own; the
[walkthrough](#walkthrough-a-type-and-its-integration-together-kicad) below adds both at once. This
guide records what the types so far needed, and is no template for the next.

## Checklist

- [ ] **The id.** Lowercase, a valid Python name, the tool's own word for the format where it has one
      (`kicad_pcb`, not `pcb`; `threemf`, because `3mf` is no Python name). It never changes.
- [ ] **The registry entry**, a `DocumentTypeEntry` in `_TYPES` (`packages/cad/src/cad/registry.py`):
      the id, its title, a one-line summary, its extensions (the first the one a written file takes),
      its MIME type, its view, the content it carries, its operations (each from the closed set,
      `cad.registry.OPERATIONS`, with the integration it needs), whether it has a reader (and the
      integration that reader needs, `reader_integration`), and whether its files are made by a
      producer (`decorator`) or changed in place by an edit (`Edit`: `<type>.edit`, a `with` block),
      never both (law 29). `wire` only if a released protocol already spells it otherwise; a new type
      never needs one. `python -m cad.registry <id>` prints the entry's help.
- [ ] **Regenerate the JavaScript**: `python -m cad.registry --js >
      packages/core/src/lib/documentTypes.generated.js`, and the documentation site's copy,
      `python -m cad.registry --docs > apps/docs/src/lib/docs/registry.generated.json`.
      `tests/python/packages/cad/test_registry.py` fails until you do.
- [ ] **The type's package**, `packages/cad/src/cad/<id>/__init__.py`, ending in `_bind(__name__)`
      (`cad._internal.document_type.bind`), with the id added to `cad._TYPES`
      (`packages/cad/src/cad/__init__.py`). Put here only what takes paths, plain values or our own
      types (the signature rule, law 24): its reader, its check (`validate`, `drc`, ...), its
      standard's own vocabulary. It imports no third-party library; a helper that takes a tool's
      objects is that integration's. `tests/python/packages/cad_server/test_core_imports.py` holds
      both.
- [ ] **Its operations.** Every operation it lists must run, as a function (`cad.<id>.<operation>`)
      and as a command (`cad <id> <operation>`). `export`, `snapshot` and `inspect` of a file the
      engine reads are the engine's verbs; a check is the type's own function, named for what it
      checks (`validate`, `drc`, `erc`; a 3D type's `dfm` is the one manufacturing check every 3D type
      shares), answering `cad.results.CheckResult` (findings with a severity, a code and a location). A
      new operation name is a change to the closed set; a new shared one must be code-free, frequently
      needed and meaningful across types (law 26).
- [ ] **Its command module**, `packages/cad/src/cad_server/cli/<id>.py`: a copy of another type's
      (`cli/step.py`) with the id changed. A check's options are generated from its function's
      signature; an operation that needs a parser of its own gets one in
      `cad_server/cli/document_types.py` (`_OWN`). Pin the command in
      `tests/python/packages/cad_server/test_cli_commands.py`.
- [ ] **The viewer.** A renderer for its view in `packages/ui/src/renderers/` (or an existing one's
      registration), listed in `cadRenderers` (`packages/ui/src/cad-viewer/OffscreenPicture.tsx`) and
      designed as [Designing its viewer](#designing-its-viewer) says; its icon
      (`packages/core/src/lib/renderCapabilities.js` reads the view); and, for a view the server
      resolves, the route its kind answers (`cad_server/viewer/http_app.py` reads `_VIEW_ROUTES` by
      view).
- [ ] **The receiver.** A new kind crosses the analytics wire: add it to `apps/api/src/events.mjs`
      in a new schema version; `tests/python/global/test_telemetry_vocabulary_sync.py` holds the two
      together.
- [ ] **Tests**: the reader and the checks on fixtures the test builds, the command's refusals, a
      renderer unit ([Testing](testing.md#adding-a-test)). A test in a suite's folder runs with that
      suite; a kind of path no rule in `scripts/github-workflows/select_checks.py` names runs every
      job until it has one ([CI](testing.md#ci)).
- [ ] **Docs to touch**: the library README's **Definitions** (the list of ids) and its shape of the
      package, the engine's **CLI** page, the server README's **Commands**, the skill that teaches
      the type, the README and the docs site's homepage (`apps/docs/src/lib/content.ts`) if they list
      formats, and `AGENTS.md` only if a repo-level rule changed.

## Designing its viewer

The rules are the shared UI's documents. Read, in this order:

- [`design-system.md`](../../packages/ui/docs/design-system.md), binding for every control: the tokens
  (`tokens.css`) and the two scales (a desktop's `text-ui` 13/20, the panel's `text-xs` 12/16; a phone's each step 2px
  up), the components (the toolbar button, `ValueDropdown`, the panel's rows, `SettingsCard`, `PanelActions`), the
  floating surface, and touch.
- [`viewer-ux.md`](../../packages/ui/docs/viewer-ux.md), binding for the layout: what goes where and why
  (`FloatingToolBar`, `SubToolbar`, `ToolPopover`, `FlatPanel` (the view's panel), `ToolStack`, `ToolPanel`, the
  Display card), what each file shows, and the patterns.
- [`cad-renderer.md`](../../packages/ui/docs/cad-renderer.md): the renderer kit -- shell, inspector,
  viewport, tools, camera, view settings.
- [`renderers.md`](../../packages/ui/docs/renderers.md) and
  [`file-viewer.md`](../../packages/ui/docs/file-viewer.md): `defineFileRenderer` and registration.
- [`render-types.md`](../../packages/ui/docs/render-types.md): shared viewer code never asks what a
  format is.
- [`viewer-host.md`](../../packages/ui/docs/viewer-host.md): environmental effects come from the host.
- [`annotation.md`](../../packages/ui/docs/annotation.md),
  [`view-updates.md`](../../packages/ui/docs/view-updates.md),
  [`render-mode.md`](../../packages/ui/docs/render-mode.md) and
  [`loading.md`](../../packages/ui/docs/loading.md).

The steps:

1. **Pick the nearest existing view kind and compose it from the kit; never write a bespoke shell.**
   A 3D mesh view (the `xbf`, `glb` and `mesh` renderers), a flat drawing (`dxf`), or a flat plot
   (`kicad_pcb`, on the kit's `FlatViewFrame` and `useFlatView`).
2. **Support every standard tool that applies to the type**: Select (its picks are the type's refs,
   shown as chips), Draw, Measure, Display (the navbar's shared card, with the type's rows), and its panel's tabs (a
   tree, layers).
3. **Keep parity with the server**: `cad <type> snapshot` draws the same view server-side, and the
   renderer listed in `cadRenderers` also draws the home's picture of a model, off screen
   (`OffscreenPicture`).
4. **Say every string in all five locales** (`scripts/test/check-ui-strings.mjs` holds it).
5. **Respect the kit's boundaries** (`scripts/test/check-kit-boundaries.mjs`) and the design system's
   checks.
6. **Test at the cheapest level**: jsdom and unit tests first; one browser spec, through the shared
   harness, only for what needs WebGL; and the renderer in
   `packages/ui/src/renderers/registrations.test.ts`.

The worked example is the KiCad board view (`packages/ui/src/renderers/board/`): a flat view like a
drawing's, on `FlatViewFrame`, with Select, Draw and Measure, its Parts, Nets and Layers tabs, the shared
Display card with its own rows (Side, Mode, in 3D Projection, Style, Background) and Preview's shared Settings card, and
its refs as chips.

## Walkthrough: a type and its integration together (KiCad)

KiCad's boards came as one change: the `kicad_pcb` document type and the `kicad` integration, which
runs KiCad's own command, `kicad-cli`. Where each item of the two checklists landed:

1. **Is KiCad an integration?** Yes, kind C
   ([Is it really an integration?](adding-an-integration.md#is-it-really-an-integration)): our code
   runs `kicad-cli` for design-rule checks and fabrication exports. Reading a `.kicad_pcb` file is
   not KiCad's code but ours, for a file format: that is the document type's, not the integration's.
2. **The integration's entry** (`INTEGRATIONS["kicad"]`): process kind `separate`, the probe for
   `kicad-cli` with the minimum version our exports need and the install hint said when it is
   missing, and `commands`, so `cad run kicad-cli ...` runs it. Its extra, `cad[kicad]`, is kicode,
   pinned exactly: KiCad's headless `kicad-cli` and its IPC API client, KiPy, one nightly's build of
   both (GPL-3.0-or-later as KiCad is, run as a program and imported as KiPy's MIT client). The
   person's own KiCad is never run; the `cad` command installs the extra's environment the first time
   a board command needs it.
3. **The type's entry** (`DOCUMENT_TYPES["kicad_pcb"]`): `.kicad_pcb`, viewed as a `plot`, its content
   (the board's layers, footprints and pads, nets, tracks, vias and zones, its outline), and its
   operations: `snapshot` and `inspect` our own code's, `drc` and `export` the `kicad` integration's.
   It has no decorator: a board is no model's output but a file changed in place, so its entry names
   its edit (`Edit("kicad", ...)`).
4. **The type's package**, `cad/kicad_pcb/`: `read(path)` and `inside(...)`, which take paths and our
   own board objects, so they are the type's (the signature rule); `snapshot` and `inspect`, the
   library's board renderer and summary. `drc`, `export` and `edit` hand the board to the `kicad`
   integration (`cad.kicad._check`, `_export`, `_session`), imported when they run, so the type's
   package still imports no third-party library.
5. **The commands**: `cad kicad_pcb drc BOARD`, `cad kicad_pcb export BOARD --to
   gerbers|drill|pos|bom|step|glb|odb|ipc2581|pdf|dxf -o DIR`, `cad kicad_pcb snapshot` and
   `cad kicad_pcb inspect`, each with a parser of its own in `cli/document_types.py`.
6. **The external program and the edit**: `cad/kicad/_program.py` finds and runs `kicad-cli` through
   the library's one helper (`cad/_internal/programs.py`), and `cad/kicad/_session.py` is the edit;
   each module's docstring is its mechanism. Every rule that keeps a desktop app out holds and is
   tested: only `kicad-cli` (`kicad-cli.exe`) is ever run, kicode's (or the one
   `CAD_KICAD_CLI` names) and never one on `PATH` or in KiCad's installation folders, no `DISPLAY` or
   `WAYLAND_DISPLAY` reaches it, and the server never starts KiCad by itself: Open in hands a
   `.kicad_*` file to a person's own KiCad at their click (`cad_server/_internal/apps.py`). What is
   made from an edited board is an explicit call after the block:

   ```python
   from cad import kicad_pcb

   with kicad_pcb.edit("board.kicad_pcb") as b:   # KiPy's open Board (kicode's); the file is the source
       ...
   kicad_pcb.export("board.kicad_pcb", to="step", out="STEP")
   ```
7. **The viewer**: the board renderer (`packages/ui/src/renderers/board/`), the plot payload the
   server resolves (`cad_server/viewer/plots.py`), its icon, and the `plot` route of its kind.
8. **Tests and CI**: board fixtures written by the tests, the commands' refusals, the parity of the
   board-reference grammar between Python and JavaScript, the edit's lifecycle with the server
   and KiPy stood in for, and a CI job (`kicad`, `scripts/test/test-kicad.sh`) that makes the
   environment of `cad[kicad]` as the server does and runs the real round trip and every export in
   it, its cost stated in the pull request.
