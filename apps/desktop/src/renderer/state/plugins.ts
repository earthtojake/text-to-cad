import { create } from "zustand";

import { setEnabledPlugins } from "@plugins/renderer";
import type { PluginInfo } from "@shared/ipc/plugins";

/**
 * The plugins this run has, as main read them from `HARDCORE_PLUGINS`: loaded once before the
 * window's first render (main.tsx), so every viewer composition after it sees the same set.
 * Settings › Plugins lists them.
 */
type PluginsState = { plugins: PluginInfo[] };

export const usePlugins = create<PluginsState>(() => ({ plugins: [] }));

export async function loadPlugins(): Promise<void> {
  try {
    const plugins = await window.hardcore.plugins.list();
    usePlugins.setState({ plugins });
    setEnabledPlugins(plugins.filter((plugin) => plugin.enabled).map((plugin) => plugin.id));
  } catch (error) {
    // Without an answer the window runs every plugin it carries, as it did before plugins could be off.
    console.error("[plugins] could not read the enabled plugins", error);
  }
}
