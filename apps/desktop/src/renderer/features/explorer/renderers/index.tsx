import { rendererPlugins } from "@plugins/renderer";
import type { ExplorerRoot } from "@shared/types";
import type { DesktopCadConnection } from "../adapters/cadRuntime";
import { codeRenderer } from "./code";
import { imageRenderer } from "./image";
import { markdownRenderer } from "./markdown";
import { unsupportedRenderer } from "./unsupported";

/**
 * Application composition: the base app's own viewers — Markdown, code, image and the unsupported
 * fallback, which live beside this file — and the viewers of each plugin this run enables
 * (`src/plugins`: CAD, PDF, G-code, CSV). With no plugins, every other file is "unsupported".
 */
export function createDesktopRenderers(projectId: string, root: ExplorerRoot, tabId: string, cadConnection?: DesktopCadConnection) {
  const plugins = rendererPlugins().map(plugin => plugin.viewers({ projectId, root, tabId, ...(cadConnection ? { cadConnection } : {}) }));
  return {
    renderers: [markdownRenderer, codeRenderer, imageRenderer, ...plugins.flatMap(plugin => plugin.renderers), unsupportedRenderer],
    dispose: () => { for (const plugin of plugins) plugin.dispose?.(); },
  };
}
