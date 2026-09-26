/**
 * Main's half of each plugin: its agent tools and the renderer commands they relay, in `plugins`
 * order. `HARDCORE_PLUGINS` decides which of them this run turns on (index.mjs, parsePluginList);
 * the build and the skill packager read every plugin, whatever the variable says.
 */
import { parsePluginList, plugins } from "./index.mjs";
import cad from "./cad/integration.mjs";
import pdf from "./pdf/integration.mjs";
import gcode from "./gcode/integration.mjs";
import csv from "./csv/integration.mjs";

/** Every plugin's integration, enabled or not. */
export const allPluginIntegrations = [cad, pdf, gcode, csv];

/** The ids this process runs with, read once from the environment. */
export const enabledPluginIds = parsePluginList(typeof process === "undefined" ? undefined : process.env.HARDCORE_PLUGINS);

/** @param {string} id */
export function pluginEnabled(id) {
  return enabledPluginIds.includes(id);
}

/** The integrations of the plugins this run enables. */
export const pluginIntegrations = allPluginIntegrations.filter(integration => pluginEnabled(integration.id));

/** The enabled plugins' manifests. */
export const enabledPlugins = plugins.filter(plugin => pluginEnabled(plugin.id));

/** The skill names (as shipped under resources/skills) of the plugins this run leaves off. */
export const disabledPluginSkills = plugins
  .filter(plugin => !pluginEnabled(plugin.id))
  .flatMap(plugin => [...plugin.skills.map(skill => skill.split("/").at(-1) ?? skill), ...plugin.repoSkills]);
