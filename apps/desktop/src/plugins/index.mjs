/**
 * The plugins this app is composed of: the one list of what each adds (README.md). Every other
 * list — file types, agent tools, renderer commands, viewers, shipped skills — is derived from
 * these manifests, by `main.mjs` for main and `renderer.ts` for the page, in this order.
 */
import pdf from "./pdf/manifest.mjs";
import gcode from "./gcode/manifest.mjs";

/**
 * @typedef {{ kind: "text" | "image" | "pdf" | "cad" | "binary", mime: string, extensions: readonly string[] }} PluginFileType
 * @typedef {{ id: string, name: string, description: string, fileTypes: readonly PluginFileType[], skills: readonly string[], repoSkills: readonly string[], commands: Readonly<Record<string, string>> }} PluginManifest
 */

/**
 * Refuse a list two plugins could not both live in: a repeated id, an extension claimed twice, a
 * tool name used twice, or a renderer command outside its plugin's `<id>-` prefix (which is how
 * the renderer routes a command to the plugin that owns it).
 * @template {readonly PluginManifest[]} T
 * @param {T} manifests
 * @returns {T}
 */
export function definePlugins(manifests) {
  const ids = new Set(), extensions = new Set(), tools = new Set();
  for (const manifest of manifests) {
    if (!/^[a-z][a-z0-9-]*$/.test(manifest.id) || ids.has(manifest.id)) throw new Error(`Duplicate or invalid plugin: ${manifest.id}`);
    ids.add(manifest.id);
    for (const extension of manifest.fileTypes.flatMap(type => type.extensions)) {
      if (extension !== extension.toLowerCase() || extensions.has(extension)) throw new Error(`Extension claimed twice or not lower case: .${extension} (${manifest.id})`);
      extensions.add(extension);
    }
    for (const [tool, kind] of Object.entries(manifest.commands)) {
      if (tools.has(tool)) throw new Error(`Duplicate plugin tool: ${tool}`);
      tools.add(tool);
      if (!kind.startsWith(`${manifest.id}-`)) throw new Error(`Plugin command ${kind} must start with "${manifest.id}-"`);
    }
  }
  return Object.freeze(manifests);
}

export const plugins = definePlugins([pdf, gcode]);

/**
 * The plugin that declares a renderer command, or null for the app's own commands.
 * @param {string} kind
 */
export function pluginForCommand(kind) {
  return plugins.find(plugin => Object.values(plugin.commands).includes(kind)) ?? null;
}
