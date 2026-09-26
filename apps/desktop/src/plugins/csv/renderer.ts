/** Step 3a: the page's half — the viewer registration, and the answer to each agent command. */
import { defineFileRenderer } from "@hardcore/ui/file-viewer";

import type { RendererPlugin } from "../renderer";
import manifest from "./manifest.mjs";
import { parseTable, separatorFor, tableState } from "./table";

const EXTENSIONS = new Set<string>(manifest.fileTypes.flatMap(type => type.extensions));

const csvViewer = defineFileRenderer<{ text: string }>({
  id: "csv",
  priority: 100, // above the code editor, which takes any text file at 0
  matches: (file) => EXTENSIONS.has(file.extension.toLowerCase()),
  async prepare({ file, source, signal }) {
    if (!source.readText) throw new Error(`This file source cannot read text files: ${file.path}`);
    const { content } = await source.readText(file.path, { signal });
    return { data: { text: content } };
  },
  load: () => import("./CsvTable"),
});

const csv: RendererPlugin = {
  manifest,
  viewers: () => ({ renderers: [csvViewer] }),
  // `csv_state`: read the tab's file and describe it. `scope` is the session's, already checked.
  async perform(kind, _params, { projectId, root, path }) {
    if (kind !== "csv-state") throw new Error(`Unknown CSV command: ${kind}`);
    const { content } = await window.hardcore.explorer.readText({ projectId, ...(root ? { root } : {}), path });
    return tableState(path, parseTable(content, separatorFor(path)));
  },
};
export default csv;
