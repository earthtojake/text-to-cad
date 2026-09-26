# The base app and its plugins

Hardcore is a **base app** plus **plugins**.

The base app is everything a session needs whatever the files are: chat with an agent (Claude
Code, Codex…), the file explorer and tabs, terminals, the built-in browser, documents, drawings,
and viewers for code, Markdown and images. On its own it knows nothing about CAD.

A plugin is one folder under `src/plugins/` that teaches the app one kind of file. It can add any
of four things:

| A plugin adds… | …so that |
| --- | --- |
| **file types** (`.csv`, `.step`…) | the explorer knows what the files are |
| a **viewer** | a file tab shows them |
| **agent tools** | the agent can read and steer what you see |
| **skills** | the agent knows the domain |

```
┌──────────────────────────────── Hardcore ────────────────────────────────┐
│                                                                          │
│  BASE APP   chat + agents · explorer + tabs · terminals · browser        │
│             documents · drawings · viewers for code, Markdown, images    │
│             ── anything else opens as "Not supported" ──                 │
│                                                                          │
├─────────────── plugins (src/plugins/<id>/, switch with HARDCORE_PLUGINS) ┤
│                                                                          │
│   cad     STEP/GLB/STL/3MF/DXF/URDF viewer · 7 tools · 12 CAD skills     │
│   pdf     PDF viewer · 4 tools · pdf skill                               │
│   gcode   toolpath viewer · 3 tools · gcode skill                        │
│   csv     table viewer · 1 tool          ← the example to copy           │
│                                                                          │
└──────────────────────────────────────────────────────────────────────────┘
```

Settings › **Plugins** shows the same thing inside the app: which plugins this run has, and for
each one the files it opens, the skills it brings and the agent tools it adds.

## See it

The same build runs with any set of plugins. `HARDCORE_PLUGINS` picks them at launch:

| Run | Command (in `apps/desktop`) | What you get |
| --- | --- | --- |
| Base app only | `npm run dev:base` | chat, files, terminals, browser; a `.step` or `.csv` is "Not supported" or plain text |
| Base + CSV | `npm run dev:plugins csv` | the base app, and `.csv`/`.tsv` open as tables |
| Base + a few | `npm run dev:plugins csv,pdf` | any comma list of plugin ids |
| Everything (default) | `npm run dev` | the Hardcore you know: CAD, PDF, G-code, CSV |

Outside `npm run`, set the variable yourself: `HARDCORE_PLUGINS=none` (base only), a comma list of
ids, or `all` / unset (every plugin). An unknown id stops the app at launch with the list of ids it
knows, so a typo never quietly launches without your plugin.

A plugin that is off is off everywhere: no viewer, no agent tools (its MCP server is not started),
and its skills are not handed to agents. With CAD off, the CAD runtime never starts and the
first-run welcome skips the CAD sample.

## Build your first plugin, in 5 steps

The CSV plugin (`csv/`) is the smallest complete plugin — five short files. Here is each one, in
the order you would write them. To make your own, copy the folder, rename it, and change the parts
marked below.

### 1. `manifest.mjs` — say what the plugin adds

Plain data. Main, the page and the build all read it, so it is the one place a plugin's file types,
skills and commands are written down.

```js
export default /** @type {const} */ ({
  id: "csv",                       // lower case; also the name of its MCP server, hardcore-csv
  name: "CSV",
  description: "Shows .csv and .tsv files as a table, and lets the agent read their shape.",
  fileTypes: [{ kind: "text", mime: "text/csv", extensions: ["csv", "tsv"] }],
  skills: [],                      // app skills: "skills/<name>" under apps/desktop/skills
  repoSkills: [],                  // repository skills by name: "gcode"
  commands: { csv_state: "csv-state" },   // agent tool name → command the page answers
});
```

`kind` is how the explorer reads the file: `text` (it has text contents), `image`, `pdf`, `cad` or
`binary`. An extension can belong to one plugin (or to the base app) only; the list refuses a
second claim.

### 2. `integration.mjs` — the agent tools

One `tool()` per key of `commands`: a name, what it does (the agent reads this), and its inputs as
a zod shape. `tabId` is the file tab the tool acts on.

```js
import { tool, tabId } from "../../main/integrations/definition.mjs";
import manifest from "./manifest.mjs";

export default { id: manifest.id, description: manifest.description, skills: [...manifest.skills], rendererCommands: manifest.commands, tools: [
  tool("csv_state", "Read the open CSV/TSV table's shape: its header, row count, column count and first rows.", { tabId }),
] };
```

When the agent calls `csv_state`, main relays it to the window as the command `csv-state`, with
the tab. You write no plumbing for that.

### 3. `renderer.ts` — the viewer, and the answer to each command

Two parts. The **viewer** says which files it takes (`matches`), reads what it needs (`prepare`) and
lazy-loads its component (`load`). The **plugin** hands the app its viewers and answers its
commands in `perform`.

```ts
const csvViewer = defineFileRenderer<{ text: string }>({
  id: "csv",
  priority: 100, // above the code editor, which takes any text file at 0
  matches: (file) => EXTENSIONS.has(file.extension.toLowerCase()),
  async prepare({ file, source, signal }) {
    const { content } = await source.readText!(file.path, { signal });
    return { data: { text: content } };
  },
  load: () => import("./CsvTable"),
});

const csv: RendererPlugin = {
  manifest,
  viewers: () => ({ renderers: [csvViewer] }),
  async perform(kind, _params, { projectId, root, path }) {
    const { content } = await window.hardcore.explorer.readText({ projectId, ...(root ? { root } : {}), path });
    return tableState(path, parseTable(content, separatorFor(path)));
  },
};
export default csv;
```

`perform` gets a `scope` the app has already checked: the session's project, its root, and the
path of the file in the tab. Whatever it returns is what the agent gets back.

### 4. `CsvTable.tsx` — the component

Any React component. It receives `data` (what `prepare` returned) and `file`, and calls
`onReady(true)` once it has drawn.

```tsx
export default function CsvTable({ data, file, onReady }: FileRendererProps<{ text: string }>) {
  const [header = [], ...rows] = useMemo(() => parseTable(data.text, separatorFor(file.path)), [data.text, file.path]);
  useEffect(() => onReady(true), [onReady]);
  return <table>…</table>;
}
```

(`table.ts` holds the plain functions both files use: `parseTable`, `tableState`, `separatorFor`.
Keeping them out of the component is what makes them easy to unit test.)

### 5. Register it — one line in each list

```js
// src/plugins/index.mjs
import csv from "./csv/manifest.mjs";
export const plugins = definePlugins([cad, pdf, gcode, csv]);

// src/plugins/main.mjs
import csv from "./csv/integration.mjs";
export const allPluginIntegrations = [cad, pdf, gcode, csv];

// src/plugins/renderer.ts
import csv from "./csv/renderer";
export const allRendererPlugins: readonly RendererPlugin[] = [cad, pdf, gcode, csv];
```

Keep the three lists in the same order; a unit test checks they match.

### Run it and test it

```bash
npm run dev:plugins csv            # the base app plus only your plugin
npx vitest run tests/unit/renderer/plugins.test.ts tests/unit/main/plugins.test.ts
```

- **See it:** open a `.csv` in the explorer; Settings › Plugins lists CSV with its extensions and
  tool.
- **Ask the agent:** "what columns does parts.csv have?" — it calls `csv_state` through
  `hardcore-csv`.
- **Tests to add:** your parser or helpers (`tests/unit/renderer/plugins.test.ts` has the CSV
  ones), and a line in `tests/e2e/plugins.spec.ts` if the viewer has something to click.

## Recipes

**Add a skill.** A skill is a folder with a `SKILL.md` (frontmatter `name` and `description`, then
instructions the agent reads).
- Yours alone: put it in `apps/desktop/skills/<name>/` and list `"skills/<name>"` in the manifest's
  `skills`.
- One from the repository's `skills/`: list its name in `repoSkills`.

Either way the build ships it (`scripts/build-skills.mjs` fails if it would not), and it is handed
to agents only while your plugin is on.

**Add an agent tool.** Three edits:
1. Add `tool_name: "<command>"` to the manifest's `commands`.
2. Add the matching `tool("tool_name", "what it does", { tabId, …inputs })` to `integration.mjs`.
3. Handle `"<command>"` in `perform`.

A tool that returns a picture passes `"image"` as `tool()`'s fourth argument and returns
`imageResult(blob, metadata)` from `results.ts`.

**Add a viewer to a plugin.** Return more than one registration from `viewers()`. The app picks
the highest `priority` whose `matches` is true (a tie is an error). The base app's viewers sit at
0 (code, for any text file), 100 (Markdown, images) and a fallback (Not supported). If the viewer
needs something per tab (a connection, a live binding), build it in `viewers(tab)` and release it
in the `dispose` you return beside `renderers`.

**Let the agent see the live view.** CSV answers `csv_state` from the file on disk. G-code answers
from the viewer the person is looking at: the mounted component registers itself for its tab, and
`perform` asks it. Copy `gcode/live.ts` when your tool needs what is on screen (the layer shown, a
capture).

## The bigger example: G-code

`gcode/` is a full plugin: a three.js toolpath viewer paired with the repository's `gcode` skill,
with three tools, one of them returning an image.

| File | What it does |
| --- | --- |
| `manifest.mjs` | `.gcode/.gco/.ngc`, `repoSkills: ["gcode"]`, three commands |
| `integration.mjs` | `gcode_state`, `set_gcode_layer`, `capture_gcode` (image) |
| `parse.ts` | G0/G1/G2/G3, absolute/relative, E modes, G92, inches → typed arrays per layer |
| `viewer.ts` | reads the text, binds the live view to its tab |
| `GcodeRenderer.tsx` | the 3D view, the layer slider, Travel, Fit, Add to prompt |
| `live.ts` | the per-tab binding the tools are answered from |

`cad/` is the same shape at full size: the shared CAD renderers from `@hardcore/ui`, a CAD
backend per tab (borrowed from the project when the host shares one), and seven viewer tools.
`pdf/` binds its live document through the host's `pdf` port, the one plugin that still does.

## What is not a plugin (yet)

- **The base app's integrations:** `workspace` (tabs and files), `browser`, `documents`,
  `terminals` and `drawings` are for every session, whatever the files, so they stay in
  `src/main/integrations/`.
- **The format tables in `@hardcore/core`:** `RENDER_FORMAT`, `isCadFile`, the render
  capabilities and the icons. They are shared with the web viewer and the snapshot CLI, so a new
  CAD-family format still gets a row there.
- **`CAD_EXTENSIONS`** (`shared/cad-refs.ts`) and the transcript's link grammar
  (`features/session/links/grammar.ts`): they turn `part.step#f3` in agent text into a reference.
  CAD-specific, but read by the base app's chat.
- **The STEP renderer's exclusion regex** (`@hardcore/ui/renderers/step`), so that a new CAD-family
  extension is not claimed by STEP.
- **Nothing is loaded at run time.** Plugins are compiled in, and `HARDCORE_PLUGINS` chooses among
  them. Installing a plugin from outside the build is a separate problem: signing, sandboxing and
  versioning.
