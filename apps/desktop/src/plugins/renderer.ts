/** The page's half of each plugin: its viewers and the answers to its renderer commands, in `plugins` order. */
import type { RendererRegistration } from "@hardcore/ui/file-viewer";
import type { ExplorerRoot } from "@shared/types";

import type { PluginManifest } from "./index.mjs";
import gcode from "./gcode/renderer";
import pdf from "./pdf/renderer";

/** The file tab a plugin's viewers are composed for. */
export interface PluginTab { projectId: string; root: ExplorerRoot; tabId: string }
/** Where a command was sent: the session's workspace and the file tab's path in it, already checked. */
export interface PluginCommandScope { projectId: string; root: string | null; path: string }

export interface RendererPlugin {
  manifest: PluginManifest;
  /** This tab's viewers, registered with the app's own (`features/explorer/renderers`). */
  renderers(tab: PluginTab): RendererRegistration[];
  /**
   * Answer one of the manifest's `commands` for the file tab `params.tabId` names. The tab is the
   * session's and a file; the plugin checks it is showing what the command expects.
   */
  perform(kind: string, params: Record<string, unknown> & { tabId: string }, scope: PluginCommandScope): Promise<unknown>;
}

export const rendererPlugins: readonly RendererPlugin[] = [pdf, gcode];

