/**
 * The page's half of each plugin: its viewers and the answers to its renderer commands, in
 * `plugins` order. Which of them this window uses is main's `HARDCORE_PLUGINS` (`plugins.list`,
 * loaded before the first render by `@renderer/state/plugins`).
 */
import type { RendererRegistration } from "@hardcore/ui/file-viewer";
import type { DesktopCadConnection } from "@renderer/features/explorer/adapters/cadRuntime";
import type { ExplorerRoot } from "@shared/types";

import type { PluginManifest } from "./index.mjs";
import cad from "./cad/renderer";
import csv from "./csv/renderer";
import gcode from "./gcode/renderer";
import pdf from "./pdf/renderer";

/** The file tab a plugin's viewers are composed for. */
export interface PluginTab {
  projectId: string;
  root: ExplorerRoot;
  tabId: string;
  /**
   * The project's shared CAD backend for this root, when the host keeps one across tabs (the CAD
   * plugin borrows it instead of starting its own). Other plugins ignore it.
   */
  cadConnection?: DesktopCadConnection;
}
/** Where a command was sent: the session's workspace and the file tab's path in it, already checked. */
export interface PluginCommandScope { projectId: string; root: string | null; path: string }

/** A plugin's viewers for one tab, and what to release when the tab goes. */
export interface PluginViewers { renderers: RendererRegistration[]; dispose?: () => void }

export interface RendererPlugin {
  manifest: PluginManifest;
  /** This tab's viewers, registered beside the base app's own (`features/explorer/renderers`). */
  viewers(tab: PluginTab): PluginViewers;
  /**
   * Answer one of the manifest's `commands` for the file tab `params.tabId` names. The tab is the
   * session's and a file; the plugin checks it is showing what the command expects.
   */
  perform(kind: string, params: Record<string, unknown> & { tabId: string }, scope: PluginCommandScope): Promise<unknown>;
}

/** Every plugin's page half, whatever this run enables. */
export const allRendererPlugins: readonly RendererPlugin[] = [cad, pdf, gcode, csv];

let enabled: readonly string[] | null = null;

/** Set once, before the first render, from main's answer; until then every plugin counts. */
export function setEnabledPlugins(ids: readonly string[]): void {
  enabled = ids;
}

/** The plugins this window runs with. */
export function rendererPlugins(): readonly RendererPlugin[] {
  return enabled ? allRendererPlugins.filter(plugin => enabled!.includes(plugin.manifest.id)) : allRendererPlugins;
}

export function pluginEnabled(id: string): boolean {
  return rendererPlugins().some(plugin => plugin.manifest.id === id);
}
