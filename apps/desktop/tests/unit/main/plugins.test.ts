import { describe, expect, it } from "vitest";

import { allIntegrations, integrations } from "@main/integrations/registry.mjs";
import { detectType } from "@main/explorer/fs";
import { IntegrationCommandKindSchema } from "@shared/ipc/integrations";
import { definePlugins, parsePluginList, plugins } from "../../../src/plugins/index.mjs";
import { allPluginIntegrations, pluginIntegrations } from "../../../src/plugins/main.mjs";
import { planSkills } from "../../../scripts/build-skills.mjs";
import path from "node:path";

const repoRoot = path.resolve(import.meta.dirname, "../../../../..");

/** Main's half of the plugin list, against the manifests it is derived from. */
describe("plugins, from main", () => {
  it("main has one integration per plugin, in order, carrying its manifest's commands and skills", () => {
    expect(allPluginIntegrations.map(integration => integration.id)).toEqual(plugins.map(plugin => plugin.id));
    allPluginIntegrations.forEach((integration, index) => {
      const manifest = plugins[index]!;
      expect(integration.rendererCommands).toEqual(manifest.commands);
      expect(integration.skills).toEqual(manifest.skills);
      // Every command has its tool, and every tool a command: the relay is the only way in.
      expect(integration.tools.map(tool => tool.name).sort()).toEqual(Object.keys(manifest.commands).sort());
      expect(allIntegrations).toContain(integration);
    });
  });

  it("with HARDCORE_PLUGINS unset (the tests), every plugin is on", () => {
    expect(pluginIntegrations).toEqual(allPluginIntegrations);
    expect(integrations.map(integration => integration.id)).toEqual(allIntegrations.map(integration => integration.id));
  });

  it("the base app's own integrations are there with no plugins at all", () => {
    const pluginIds = new Set<string>(plugins.map(plugin => plugin.id));
    const base = allIntegrations.filter(integration => !pluginIds.has(integration.id)).map(integration => integration.id);
    expect(base).toEqual(["workspace", "browser", "documents", "terminals", "drawings"]);
  });

  it("HARDCORE_PLUGINS: unset or all is every plugin, none is the base app, a list is those, an unknown id is refused", () => {
    const every = plugins.map(plugin => plugin.id);
    expect(parsePluginList(undefined)).toEqual(every);
    expect(parsePluginList("")).toEqual(every);
    expect(parsePluginList(" ALL ")).toEqual(every);
    expect(parsePluginList("none")).toEqual([]);
    expect(parsePluginList("csv, cad,csv")).toEqual(["cad", "csv"]);
    expect(() => parsePluginList("cad,spreadsheet")).toThrow(/unknown plugin\(s\): spreadsheet\. Known: cad, pdf, gcode, csv/);
  });

  it("a plugin's file types are the explorer's, and its commands are IPC commands", () => {
    expect(detectType("paper.pdf")).toMatchObject({ kind: "pdf", mime: "application/pdf" });
    expect(detectType("parts/cup.gcode")).toMatchObject({ kind: "text", mime: "text/x-gcode" });
    expect(detectType("parts/bracket.step")).toMatchObject({ kind: "cad", mime: "model/step" });
    expect(detectType("data/sheet.csv")).toMatchObject({ kind: "text", mime: "text/csv" });
    for (const kind of plugins.flatMap(plugin => Object.values(plugin.commands))) {
      expect(IntegrationCommandKindSchema.safeParse(kind).success).toBe(true);
    }
  });

  it("a repo skill a plugin pairs with ships in the app", () => {
    const shipped = planSkills(repoRoot).map(skill => skill.name);
    for (const name of plugins.flatMap(plugin => plugin.repoSkills)) expect(shipped).toContain(name);
  });

  it("refuses a plugin list two plugins could not share", () => {
    const base = { name: "X", description: "x", skills: [], repoSkills: [], fileTypes: [], commands: {} };
    expect(() => definePlugins([{ ...base, id: "a" }, { ...base, id: "a" }])).toThrow(/Duplicate/);
    expect(() => definePlugins([
      { ...base, id: "a", fileTypes: [{ kind: "text", mime: "text/plain", extensions: ["x"] }] },
      { ...base, id: "b", fileTypes: [{ kind: "text", mime: "text/plain", extensions: ["x"] }] },
    ])).toThrow(/claimed twice/);
    expect(() => definePlugins([{ ...base, id: "a", commands: { t: "a-x" } }, { ...base, id: "b", commands: { t: "b-x" } }])).toThrow(/Duplicate plugin tool/);
    expect(() => definePlugins([{ ...base, id: "a", commands: { s: "same" } }, { ...base, id: "b", commands: { t: "same" } }])).toThrow(/Duplicate plugin tool or command/);
    expect(() => definePlugins([{ ...base, id: "a", repoSkills: ["cad"] }, { ...base, id: "b", repoSkills: ["cad"] }])).toThrow(/Skill owned by two plugins/);
  });
});
