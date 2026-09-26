/** One composition point for app-owned integrations and the plugins' (src/plugins). Imported by main, MCP and skill packaging. */
import workspace from "./workspace/module.mjs";
import browser from "./browser/module.mjs";
import cad from "./cad/module.mjs";
import documents from "./documents/module.mjs";
import terminals from "./terminals/module.mjs";
import drawings from "./drawings/module.mjs";
import { pluginIntegrations } from "../../plugins/main.mjs";

/**
 * @typedef {{ id: string, description: string, skills: string[], tools: Array<{name: string, description: string, inputSchema: import('zod').ZodType<Record<string, unknown>>, output: string}>, hostTools?: Array<{name: string, description: string, inputSchema: import('zod').ZodType<Record<string, unknown>>, output: string}>, runtime?: string, rendererCommands?: Record<string, string> }} Integration
 */
/** @param {Integration[]} entries */
export function defineIntegrations(entries) {
  const ids = new Set(), methods = new Set();
  for (const entry of entries) {
    if (!/^[a-z][a-z-]*$/.test(entry.id) || ids.has(entry.id)) throw new Error(`Duplicate or invalid integration: ${entry.id}`);
    ids.add(entry.id);
    for (const tool of [...entry.tools, ...(entry.hostTools ?? [])]) {
      if (methods.has(tool.name)) throw new Error(`Duplicate integration method: ${tool.name}`);
      if (!tool.inputSchema?.safeParse || !tool.description) throw new Error(`Invalid tool contract: ${tool.name}`);
      methods.add(tool.name);
    }
  }
  return Object.freeze(entries);
}
export const integrations = defineIntegrations([workspace, browser, ...pluginIntegrations, cad, documents, terminals, drawings]);
export function integrationById(id) {
  const found = integrations.find(entry => entry.id === id);
  if (!found) throw new Error(`Unknown integration: ${id}`);
  return found;
}
export function toolByName(name) {
  for (const integration of integrations) {
    const tool = [...integration.tools, ...(integration.hostTools ?? [])].find(tool => tool.name === name);
    if (tool) return { integration, tool };
  }
  return null;
}
