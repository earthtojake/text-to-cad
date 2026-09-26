import { describe, expect, it } from "vitest";

import { integrations } from "@main/integrations/registry.mjs";
import { detectType } from "@main/explorer/fs";
import { IntegrationCommandKindSchema } from "@shared/ipc/integrations";
import { definePlugins, plugins } from "../../../src/plugins/index.mjs";
import { pluginIntegrations } from "../../../src/plugins/main.mjs";
import { planSkills } from "../../../scripts/build-skills.mjs";
import path from "node:path";

const repoRoot = path.resolve(import.meta.dirname, "../../../../..");

/** Main's half of the plugin list, against the manifests it is derived from. */
describe("plugins, from main", () => {
  it("main composes one integration per plugin, in order, carrying its manifest's commands and skills", () => {
    expect(pluginIntegrations.map(integration => integration.id)).toEqual(plugins.map(plugin => plugin.id));
    pluginIntegrations.forEach((integration, index) => {
      const manifest = plugins[index]!;
      expect(integration.rendererCommands).toEqual(manifest.commands);
      expect(integration.skills).toEqual(manifest.skills);
      // Every command has its tool, and every tool a command: the relay is the only way in.
      expect(integration.tools.map(tool => tool.name).sort()).toEqual(Object.keys(manifest.commands).sort());
      expect(integrations).toContain(integration);
    });
  });

  it("a plugin's file types are the explorer's, and its commands are IPC commands", () => {
    expect(detectType("paper.pdf")).toMatchObject({ kind: "pdf", mime: "application/pdf" });
    expect(detectType("parts/cup.gcode")).toMatchObject({ kind: "text", mime: "text/x-gcode" });
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
    expect(() => definePlugins([{ ...base, id: "a", commands: { a_state: "b-state" } }])).toThrow(/must start with "a-"/);
    expect(() => definePlugins([{ ...base, id: "a", commands: { t: "a-x" } }, { ...base, id: "b", commands: { t: "b-x" } }])).toThrow(/Duplicate plugin tool/);
  });
});
