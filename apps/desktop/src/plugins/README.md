# Plugins

Hardcore is a base app plus plugins. The base app is everything a session needs whatever the
files are: the chat and its agents, the explorer and its tab strip, the FileViewer and the shared
CAD renderers, the terminal, browser, documents and drawings, and the MCP bridge that hands app
tools to the agent. A **plugin** is one folder here that adds a capability for one kind of file:

| It declares | So that |
| --- | --- |
| **file types** (extensions, media type, how main reads them) | the explorer detects the files (`src/main/explorer/fs.ts`) |
| a **viewer** (a `FileRendererDefinition`) | the file tab shows them (`features/explorer/renderers/index.tsx`) |
| **agent tools** and the **renderer commands** they relay | the agent can read and steer what the person sees (`integrations/registry.mjs`, `shared/ipc/integrations.ts`, `state/integration-commands.ts`) |
| **skills** (its own, or repository skills it pairs with) | the agent knows the domain (`scripts/build-skills.mjs`) |

None of those files has a plugin in it by name. Each derives its rows from the list in
[`index.mjs`](index.mjs), so adding a plugin is adding a folder and one line in each of the three
lists below — never an edit to the explorer, the IPC contract, the relay or the skill build.

## The shape of a plugin

```
src/plugins/
  index.mjs          plugins: the manifests, validated (one list; order is registration order)
  main.mjs           pluginIntegrations: main's half of each, same order
  renderer.ts        rendererPlugins: the page's half of each, same order; the RendererPlugin type
  results.ts         imageResult(), for a tool that returns a picture
  <id>/
    manifest.mjs     plain data, read by main, the page and the build
    integration.mjs  main/MCP: the agent tools (zod contracts) for the manifest's commands
    renderer.ts      the page: { manifest, renderers(tab), perform(kind, params, scope) }
    viewer.ts        the FileRendererDefinition; loads the component lazily
    <Viewer>.tsx     the component
```

A manifest:

```js
export default /** @type {const} */ ({
  id: "gcode",                         // lower-case; names its MCP server `hardcore-gcode`
  name: "G-code",
  description: "Toolpath viewing for sliced G-code, …",
  fileTypes: [{ kind: "text", mime: "text/x-gcode", extensions: ["gcode", "gco", "ngc"] }],
  skills: [],                          // app-owned skill folders, relative to apps/desktop
  repoSkills: ["gcode"],               // repository skills (skills/<name>) it pairs with
  commands: { gcode_state: "gcode-state", set_gcode_layer: "gcode-layer", capture_gcode: "gcode-capture" },
});
```

`definePlugins` refuses a list two plugins could not share: a repeated id, an extension claimed
twice (and `fs.ts` refuses one a plugin shares with the base table), a tool name used twice, or a
command kind not prefixed `<id>-`. `kind` is how main reads the file (`text`, `binary`, `image`,
`pdf`, `cad`), not which viewer shows it; the viewer is chosen by its own `matches`.

`tests/unit/main/plugins.test.ts` and `tests/unit/renderer/plugins.test.ts` hold the two halves to
the manifests: one integration and one page plugin per manifest, in order, with the manifest's
commands, tools and skills; the file types detected; the repo skills shipped; each viewer chosen
for its files over the code editor.

## Add a viewer

A viewer alone — the file opens in a tab, no agent tools — is a plugin with no `commands`:

1. `manifest.mjs` with `fileTypes` and empty `commands`, `skills` and `repoSkills`.
2. `viewer.ts`: `defineFileRenderer({ id, priority: 100, matches, prepare, load })`. `prepare`
   reads through the `FileSource` it is given (`readText`, or `readAsset` whose `release` is the
   prepared `dispose`) and returns `data`; `load` imports the component. A priority above 0 wins
   over the code editor, which takes any text file.
3. The component gets `FileRendererProps<Data>`: `data`, `file`, `source`, `onReady` (call it when
   something is on screen), `state`/`onStateChange` (a JSON slice that persists per tab). Offer
   **Add to prompt** with `PromptContextAction` from `@hardcore/ui/host`: a `reference` part for
   the file and an `attachment` for a capture, as the G-code and PDF viewers do. Use
   `@hardcore/ui/primitives/*` and the type scale (`text-ui`, `text-tiny`), not pixel sizes.
4. `renderer.ts`: `{ manifest, renderers: () => [myRenderer], perform: () => { throw … } }`, and
   an `integration.mjs` with no tools: `{ id, description, skills: [], rendererCommands: {}, tools: [] }`.
5. One line in each of `index.mjs`, `main.mjs` and `renderer.ts`.

A renderer both apps (desktop and the web CAD Viewer) need belongs in `@hardcore/ui/renderers/*`
instead, and a CAD format needs the core format tables too — see *What is not a plugin*.

## Add a skill

A skill is instructions and scripts the agent loads; it needs no viewer.

- **A repository skill** (`skills/<name>/`, shipped to every agent installer too) is written in the
  repository's form — `SKILL.md` with `name` and `description`, `references/`, thin `scripts/`
  over `cadgen` — and the app ships every one of them already (`build-skills.mjs`, except
  `cad-viewer`). A plugin that pairs with one names it in `repoSkills`; the build fails if it
  would not ship.
- **An app-owned skill** (`apps/desktop/skills/<name>/`) is for the app only, usually about the
  plugin's own tools. Name its folder in the manifest's `skills`, relative to `apps/desktop`; the
  build copies it into `resources/skills` beside the repository's and refuses a duplicate name.

Either way the session receives it as a real file in its skills root (README, *Skills and tools in
a session*); nothing is installed into an agent's configuration.

## Add a plugin (skill + viewer): the G-code walkthrough

`gcode/` pairs the repository's `gcode` skill (slice meshes into G-code, validate it) with a
toolpath viewer and three tools, so an agent that just sliced a part can open the result, look at
it and show the person a layer.

1. **Manifest** (`gcode/manifest.mjs`): `.gcode`/`.gco`/`.ngc` read as text with the
   `text/x-gcode` media type, `repoSkills: ["gcode"]`, and three commands prefixed `gcode-`.
2. **Tools** (`gcode/integration.mjs`): one `tool(name, description, zodShape, output)` per
   command, from `main/integrations/definition.mjs`; `capture_gcode` returns `"image"`. The
   registry gives the plugin its own `hardcore-gcode` MCP server and token.
3. **Parser** (`gcode/parse.ts`): G0/G1 moves and G2/G3 arcs into line segments, extrusion
   grouped into layers, with counts, extents and filament — pure, and unit-tested against
   `tests/fixtures/gcode/cup.gcode`.
4. **Viewer** (`gcode/viewer.ts`, `GcodeRenderer.tsx`): `createGcodeRenderer(tab)` reads the text
   in `prepare` and closes over the tab, so the mounted component can bind itself for that tab's
   commands. The component draws the toolpath with three.js (extrusion coloured by layer, travel on
   request, a bed grid, orbit controls), a layer slider, Fit and **Add to prompt**.
5. **Commands** (`gcode/live.ts`): the component registers `{ state, setLayer, capture }` while it
   is mounted; `perform` answers `gcode-state`, `gcode-layer` and `gcode-capture` from it, after
   checking the binding is the same project, root and path the command was scoped to. A tab that
   is not showing a toolpath is refused, never answered from another tab.
6. **Lists**: `gcode` in `index.mjs`, `main.mjs` and `renderer.ts`.
7. **Checks**: the unit tests above, and `tests/e2e/integrations.spec.ts`, where a real ACP session
   opens `cup.gcode`, reads its state, sets a layer (the slider follows) and captures it.

PDF (`pdf/`) is the same shape with one difference: it predates plugins, so its live document is
bound through the host's `pdf` port (`@hardcore/ui/host`) and kept by `state/live-documents.ts`,
and its `perform` answers from there. A new plugin keeps its bindings in its own folder, as G-code
does, and needs no change to the host contract.

## What is not a plugin (yet)

- **The CAD formats** (STEP, GLB, STL, 3MF, DXF, URDF/SRDF/SDF) are the base app's: their viewers
  are shared with the web CAD Viewer (`@hardcore/ui/renderers/*`), their backend is `cadgen`, and
  a format is also a row in `@hardcore/core`'s format tables (`lib/fileFormats.js`,
  `lib/renderCapabilities.js`), the STEP renderer's exclusion pattern
  (`packages/ui/src/renderers/step/index.ts`), `CAD_EXTENSIONS` (`src/shared/cad-refs.ts`) and the
  transcript's file-link grammar. Adding one is `packages/ui/docs/render-types.md`, not this folder.
- **The app's own domains** — workspace, browser, documents, terminals, drawings, the CAD viewer's
  tools — stay in `src/main/integrations/`; they are part of every session, not a capability a
  file type brings.
- **Icons**: a plugin's files show the explorer's generic file icon.
- **Loading at run time**: plugins are compiled into the app. There is no plugin directory to
  drop a folder into and no third-party code loaded after launch; a plugin is reviewed and shipped
  like the rest of the app.
