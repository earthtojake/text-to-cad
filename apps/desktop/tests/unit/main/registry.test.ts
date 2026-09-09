import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import { AGENT_PROVIDERS, agentProvider } from "@main/agents/registry";
import { AgentProviderSchema } from "@shared/agents";

describe("the agent registry", () => {
  it("parses every row against the provider schema", () => {
    for (const provider of AGENT_PROVIDERS) {
      expect(() => AgentProviderSchema.parse(provider), provider.id).not.toThrow();
    }
  });

  it("has unique ids and registry ids", () => {
    const ids = AGENT_PROVIDERS.map((provider) => provider.id);
    expect(new Set(ids).size).toBe(ids.length);
    const registryIds = AGENT_PROVIDERS.map((provider) => provider.registryId).filter(Boolean);
    expect(new Set(registryIds).size).toBe(registryIds.length);
  });

  it("carries the agents the plan names", () => {
    for (const id of [
      "claude-code",
      "codex",
      "gemini-cli",
      "github-copilot",
      "opencode",
      "amp",
      "qwen-code",
      "kiro",
      "auggie",
      "goose",
      "mistral-vibe",
      "cursor-agent",
      "droid",
      "hermes",
    ]) {
      expect(agentProvider(id), id).not.toBeNull();
    }
  });

  it("launches Claude Code and Codex through the public ACP adapters", () => {
    expect(agentProvider("claude-code")?.launch).toEqual({
      command: "npx",
      args: ["-y", "@agentclientprotocol/claude-agent-acp@latest"],
      env: {},
    });
    expect(agentProvider("codex")?.launch).toEqual({
      command: "npx",
      args: ["-y", "@agentclientprotocol/codex-acp@latest"],
      env: {},
    });
    expect(agentProvider("gemini-cli")?.launch).toEqual({ command: "gemini", args: ["--acp"], env: {} });
  });

  it("gives every provider a launch command, a binary, and at least one install line somewhere", () => {
    for (const provider of AGENT_PROVIDERS) {
      expect(provider.launch.command, provider.id).not.toBe("");
      expect(provider.binaryNames.length, provider.id).toBeGreaterThan(0);
      const installs = [...provider.install.macos, ...provider.install.linux, ...provider.install.windows];
      // Two registry-binary agents (Junie, Devin) document no CLI installer.
      if (installs.length === 0) {
        expect(["junie", "devin"]).toContain(provider.id);
      }
      for (const install of installs) {
        expect(install.command, `${provider.id} ${install.label}`).toMatch(/\S/);
      }
    }
  });

  it("says which agents load the skills root Hardcore names, and which need telling", () => {
    // The two adapters that read `additionalDirectories` / `_meta.additionalRoots`
    // and load `<root>/.claude/skills` and `<root>/.agents/skills` themselves.
    expect(agentProvider("claude-code")?.skillRoots).toBe("native");
    expect(agentProvider("codex")?.skillRoots).toBe("native");
    // Gemini's ACP `newSession` ignores additional directories; the rest are
    // assumed to as well, so they get the preamble.
    expect(agentProvider("gemini-cli")?.skillRoots).toBe("preamble");
    const preamble = AGENT_PROVIDERS.filter((provider) => provider.skillRoots === "preamble");
    expect(preamble.length).toBe(AGENT_PROVIDERS.length - 2);
  });

  it("describes auth as cli-login, api-key or none, with the env vars an api-key needs", () => {
    for (const provider of AGENT_PROVIDERS) {
      expect(provider.authMethods.length, provider.id).toBeGreaterThan(0);
      for (const method of provider.authMethods) {
        if (method.type === "api-key") {
          expect(method.envVars.length, provider.id).toBeGreaterThan(0);
        }
      }
    }
    expect(agentProvider("claude-code")?.authProbe.checkArgs).toEqual(["auth", "status"]);
    expect(agentProvider("codex")?.authProbe.checkArgs).toEqual(["login", "status"]);
  });

  it("points every icon at a committed asset, and says so when there is none", () => {
    // The `icon` column names a file in src/renderer/assets/agents/, downloaded
    // by scripts/fetch-agent-icons.mjs. A name with no file behind it would be
    // an empty square in the Agents list, so the file is what is asserted.
    const assets = path.resolve(
      path.dirname(fileURLToPath(import.meta.url)),
      "..",
      "..",
      "..",
      "src",
      "renderer",
      "assets",
      "agents",
    );
    for (const provider of AGENT_PROVIDERS) {
      if (provider.icon === null) {
        // Only for agents the ACP registry has no logo for; anything else is a
        // fetch that was never run.
        expect(["kiro", "hermes"], provider.id).toContain(provider.id);
        continue;
      }
      expect(provider.icon, provider.id).toBe(provider.id);
      expect(fs.existsSync(path.join(assets, `${provider.icon}.svg`)), provider.id).toBe(true);
    }
  });

  it("marks the two adapters that run without the CLI on PATH", () => {
    expect(agentProvider("claude-code")?.launchWithoutBinary).toBe(true);
    expect(agentProvider("codex")?.launchWithoutBinary).toBe(true);
    expect(agentProvider("gemini-cli")?.launchWithoutBinary).toBe(false);
  });
});
