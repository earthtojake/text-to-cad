/**
 * Streamdown's Mermaid plugin, loaded on the first diagram.
 *
 * `@streamdown/mermaid` imports `mermaid` at its top level, so handing its
 * plugin to `<Streamdown>` put ~0.8 MB of diagram engine in the window's
 * first chunk for a transcript that almost never draws one. Streamdown only
 * asks the plugin for an instance and awaits `render`, which is already
 * asynchronous — so the instance here is a stand-in that imports the real
 * plugin there, and a config given before then is handed over with the first
 * render. Mermaid's configuration is one global, so deferring `initialize`
 * changes nothing a diagram can see.
 */
import type { DiagramPlugin as StockPlugin, MermaidConfig } from "@streamdown/mermaid";
import type { DiagramPlugin } from "streamdown";

type MermaidInstance = ReturnType<DiagramPlugin["getMermaid"]>;
/** Streamdown's own, looser spelling of the config (`theme: string`). */
type StreamdownConfig = Parameters<MermaidInstance["initialize"]>[0];

let loading: Promise<StockPlugin> | undefined;
const load = () =>
  (loading ??= import("@streamdown/mermaid").then(
    (module) => module.mermaid,
    (error: unknown) => {
      // A failed import (a chunk that did not load) is retried by the next diagram, like math.ts's,
      // not remembered for the life of the window; this render still fails.
      loading = undefined;
      throw error;
    },
  ));

/** A config set before the real instance exists; `undefined` once it has been handed over. */
let pending: StreamdownConfig | undefined;

const instance: MermaidInstance = {
  initialize(config) {
    pending = config;
  },
  async render(id, source) {
    const plugin = await load();
    // The same object Streamdown hands the stock plugin; only the two packages'
    // declarations of it differ.
    const real = plugin.getMermaid(pending as MermaidConfig | undefined);
    pending = undefined;
    return real.render(id, source);
  },
};

export const mermaid: DiagramPlugin = {
  name: "mermaid",
  type: "diagram",
  language: "mermaid",
  getMermaid(config) {
    if (config) instance.initialize(config);
    return instance;
  },
};
