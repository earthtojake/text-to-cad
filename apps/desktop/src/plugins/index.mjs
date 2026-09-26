/**
 * The plugins this app can be composed of: the one list of what each adds (README.md). Every other
 * list — file types, agent tools, renderer commands, viewers, shipped skills — is derived from
 * these manifests, by `main.mjs` for main and `renderer.ts` for the page, in this order.
 *
 * To add a plugin: write its folder, then add its manifest here and its halves to `main.mjs` and
 * `renderer.ts` (one line each).
 */
import cad from "./cad/manifest.mjs";
import pdf from "./pdf/manifest.mjs";
import gcode from "./gcode/manifest.mjs";
import csv from "./csv/manifest.mjs";

/**
 * @typedef {{ kind: "text" | "image" | "pdf" | "cad" | "binary", mime: string, extensions: readonly string[] }} PluginFileType
 * @typedef {{ id: string, name: string, description: string, fileTypes: readonly PluginFileType[], skills: readonly string[], repoSkills: readonly string[], commands: Readonly<Record<string, string>> }} PluginManifest
 */

/**
 * Refuse a list two plugins could not both live in: a repeated id, an extension claimed twice, or
 * a tool name or renderer command used twice (a command is routed to the plugin that declares it).
 * @template {readonly PluginManifest[]} T
 * @param {T} manifests
 * @returns {T}
 */
export function definePlugins(manifests) {
  const ids = new Set(), extensions = new Set(), tools = new Set(), kinds = new Set(), skills = new Set();
  for (const manifest of manifests) {
    if (!/^[a-z][a-z0-9-]*$/.test(manifest.id) || ids.has(manifest.id)) throw new Error(`Duplicate or invalid plugin: ${manifest.id}`);
    ids.add(manifest.id);
    for (const extension of manifest.fileTypes.flatMap(type => type.extensions)) {
      if (extension !== extension.toLowerCase() || extensions.has(extension)) throw new Error(`Extension claimed twice or not lower case: .${extension} (${manifest.id})`);
      extensions.add(extension);
    }
    for (const [tool, kind] of Object.entries(manifest.commands)) {
      if (tools.has(tool) || kinds.has(kind)) throw new Error(`Duplicate plugin tool or command: ${tool} / ${kind} (${manifest.id})`);
      tools.add(tool);
      kinds.add(kind);
    }
    for (const skill of [...manifest.skills, ...manifest.repoSkills]) {
      if (skills.has(skill)) throw new Error(`Skill owned by two plugins: ${skill} (${manifest.id})`);
      skills.add(skill);
    }
  }
  return Object.freeze(manifests);
}

/** Every plugin this build carries, whether or not this run enables it. */
export const plugins = definePlugins([cad, pdf, gcode, csv]);

/**
 * Which plugins a run enables, from `HARDCORE_PLUGINS`: unset, empty or `all` is every plugin,
 * `none` is the base app alone, and otherwise a comma list of ids (`csv,pdf`). An unknown id is
 * refused, naming the ones there are, rather than quietly launching without it.
 * @param {string | undefined | null} value
 * @returns {string[]}
 */
export function parsePluginList(value) {
  const text = (value ?? "").trim().toLowerCase();
  if (text === "" || text === "all") return plugins.map(plugin => plugin.id);
  if (text === "none") return [];
  const ids = [...new Set(text.split(",").map(id => id.trim()).filter(Boolean))];
  const unknown = ids.filter(id => !plugins.some(plugin => plugin.id === id));
  if (unknown.length) throw new Error(`HARDCORE_PLUGINS names unknown plugin(s): ${unknown.join(", ")}. Known: ${plugins.map(plugin => plugin.id).join(", ")}, or all / none.`);
  // In the list's own order, whatever order the variable named them in.
  return plugins.map(plugin => plugin.id).filter(id => ids.includes(id));
}

/**
 * The plugin that declares a renderer command, or null for the app's own commands.
 * @param {string} kind
 */
export function pluginForCommand(kind) {
  return plugins.find(plugin => Object.values(plugin.commands).includes(kind)) ?? null;
}
