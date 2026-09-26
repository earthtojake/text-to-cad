import { defineFileRenderer } from "@hardcore/ui/file-viewer";

import type { PluginTab } from "../renderer";
import { bindGcodeView, type LiveGcodeView } from "./live";
import manifest from "./manifest.mjs";

export interface GcodeRendererData {
  text: string;
  revision?: string;
  /** Registers the mounted view for this tab's agent commands. */
  bind: (view: LiveGcodeView) => () => void;
}

const EXTENSIONS = new Set<string>(manifest.fileTypes.flatMap(type => type.extensions));

/** The toolpath viewer, for one tab: its live view is bound to that tab's commands. */
export function createGcodeRenderer(tab: PluginTab) {
  return defineFileRenderer<GcodeRendererData>({
    id: "gcode",
    // Above the code editor, which takes any text file at 0.
    priority: 100,
    matches: (file) => EXTENSIONS.has(file.extension.toLowerCase()),
    async prepare({ file, source, signal }) {
      if (!source.readText) throw new Error(`This file source cannot read text files: ${file.path}`);
      const document = await source.readText(file.path, { signal });
      if (document.truncated) throw new Error("This G-code file is too large to show here.");
      return { data: { text: document.content, revision: document.revision, bind: view => bindGcodeView(tab, view) } };
    },
    load: () => import("./GcodeRenderer"),
  });
}
