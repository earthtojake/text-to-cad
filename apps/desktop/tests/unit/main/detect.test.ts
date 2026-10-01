import fs from "node:fs";
import os from "node:os";
import path from "node:path";

import { describe, expect, it } from "vitest";

import { AgentDetector, nodeProbes, parseVersion, which, type DetectorProbes } from "@main/agents/detect";
import type { AgentStatus } from "@shared/agents";
import { CLAUDE_ADAPTER, CODEX_ADAPTER, agentProvider } from "@main/agents/registry";
import { parseEnv, stripHostSession } from "@main/agents/shell-env";

/** A fake machine: which files are executable, what each prints, which credential files exist. */
function machine(options: {
  executables?: string[];
  files?: string[];
  outputs?: Record<string, { stdout?: string; stderr?: string; code?: number | null }>;
  env?: Record<string, string>;
  platform?: NodeJS.Platform;
}): DetectorProbes {
  const executables = new Set(options.executables ?? []);
  const files = new Set(options.files ?? []);
  return {
    env: async () => ({ PATH: "/usr/local/bin:/opt/homebrew/bin", ...options.env }),
    isExecutable: async (file) => executables.has(file),
    exists: async (file) => files.has(file) || executables.has(file),
    exec: async (file, args) => {
      const key = `${file} ${args.join(" ")}`.trim();
      const answer = options.outputs?.[key];
      if (!answer) {
        throw new Error(`unexpected exec ${key}`);
      }
      return { stdout: answer.stdout ?? "", stderr: answer.stderr ?? "", code: answer.code ?? 0 };
    },
    homeDir: () => "/Users/me",
    platform: options.platform ?? "darwin",
  };
}

describe("parseVersion", () => {
  it("takes the first semver in the output", () => {
    expect(parseVersion("2.1.261 (Claude Code)")).toBe("2.1.261");
    expect(parseVersion("codex-cli 0.149.1")).toBe("0.149.1");
    expect(parseVersion("gemini 1.2.3-nightly.4")).toBe("1.2.3-nightly.4");
    expect(parseVersion("no version here")).toBeNull();
  });
});

describe("which", () => {
  it("walks PATH in order", async () => {
    const probes = machine({ executables: ["/opt/homebrew/bin/codex"] });
    expect(await which("codex", { PATH: "/usr/local/bin:/opt/homebrew/bin" }, probes)).toBe(
      "/opt/homebrew/bin/codex",
    );
    expect(await which("nothing", { PATH: "/usr/local/bin" }, probes)).toBeNull();
  });

  it("tries PATHEXT on Windows", async () => {
    const probes = machine({ executables: ["C:\\tools\\codex.CMD"], platform: "win32" });
    // path.join on a POSIX host uses "/", so only the extension logic is under test here.
    const found = await which("codex", { PATH: "C:\\tools", PATHEXT: ".EXE;.CMD" }, {
      ...probes,
      isExecutable: async (file) => file.endsWith("codex.CMD"),
    });
    expect(found).toMatch(/codex\.CMD$/);
  });
});

describe("the real executable probe", () => {
  it.skipIf(process.platform === "win32")("is a regular executable file, never a directory of that name", async () => {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), "text-to-cad-detect-"));
    try {
      fs.mkdirSync(path.join(dir, "claude"));
      fs.writeFileSync(path.join(dir, "codex"), "#!/bin/sh\n", { mode: 0o755 });
      expect(await nodeProbes.isExecutable(path.join(dir, "claude"))).toBe(false);
      expect(await nodeProbes.isExecutable(path.join(dir, "codex"))).toBe(true);
    } finally {
      fs.rmSync(dir, { recursive: true, force: true });
    }
  });
});

describe("AgentDetector", () => {
  const providers = [agentProvider("claude-code")!, agentProvider("codex")!, agentProvider("gemini-cli")!];

  it("reports installed binaries with their version and login state", async () => {
    const detector = new AgentDetector(
      providers,
      machine({
        executables: ["/opt/homebrew/bin/claude", "/usr/local/bin/codex"],
        outputs: {
          "/opt/homebrew/bin/claude --version": { stdout: "2.1.261 (Claude Code)" },
          "/opt/homebrew/bin/claude auth status": { stdout: '{"loggedIn":true}', code: 0 },
          "/usr/local/bin/codex --version": { stdout: "codex-cli 0.149.1" },
          "/usr/local/bin/codex login status": { stdout: "Not logged in", code: 1 },
        },
      }),
    );
    const statuses = await detector.refresh();
    const byId = Object.fromEntries(statuses.map((status) => [status.id, status]));
    expect(byId["claude-code"]).toMatchObject({
      installed: true,
      binaryPath: "/opt/homebrew/bin/claude",
      version: "2.1.261",
      auth: "authenticated",
    });
    expect(byId.codex).toMatchObject({ installed: true, version: "0.149.1", auth: "unauthenticated" });
    expect(byId["gemini-cli"]).toMatchObject({ installed: false, binaryPath: null, version: null });
  });

  it("carries the registry's adapter pin onto the status, installed or not", async () => {
    const detector = new AgentDetector(providers, machine({}));
    const byId = Object.fromEntries((await detector.refresh()).map((status) => [status.id, status]));
    expect(byId["claude-code"]?.adapter).toEqual({
      package: "@agentclientprotocol/claude-agent-acp",
      version: CLAUDE_ADAPTER.version,
    });
    expect(byId.codex?.adapter).toEqual({ package: "@agentclientprotocol/codex-acp", version: CODEX_ADAPTER.version });
    expect(byId["gemini-cli"]?.adapter).toBeNull();
  });

  it("falls back to the credential file when the auth probe fails for a reason that is not a sign-out", async () => {
    const detector = new AgentDetector(
      [agentProvider("claude-code")!],
      machine({
        executables: ["/opt/homebrew/bin/claude"],
        files: ["/Users/me/.claude/.credentials.json"],
        outputs: {
          "/opt/homebrew/bin/claude --version": { stdout: "1.0.0 (Claude Code)" },
          "/opt/homebrew/bin/claude auth status": { stderr: "error: unknown command 'auth'", code: 1 },
        },
      }),
    );
    const [claude] = await detector.refresh();
    expect(claude).toMatchObject({ installed: true, auth: "authenticated" });
  });

  it("treats an API key in the environment as authenticated without running anything", async () => {
    const detector = new AgentDetector(
      providers,
      machine({
        executables: ["/usr/local/bin/codex"],
        env: { OPENAI_API_KEY: "sk-test" },
        outputs: { "/usr/local/bin/codex --version": { stdout: "codex-cli 0.149.1" } },
      }),
    );
    const [, codex] = await detector.refresh();
    expect(codex?.auth).toBe("authenticated");
  });

  it("falls back to credential files, and to unknown when there is nothing to go on", async () => {
    const detector = new AgentDetector(
      providers,
      machine({
        executables: ["/usr/local/bin/gemini"],
        files: ["/Users/me/.gemini/oauth_creds.json"],
        outputs: { "/usr/local/bin/gemini --version": { stdout: "0.58.0" } },
      }),
    );
    const statuses = await detector.refresh();
    expect(statuses.find((s) => s.id === "gemini-cli")?.auth).toBe("authenticated");
    // Claude is not installed and has no credential file: nothing is known.
    expect(statuses.find((s) => s.id === "claude-code")?.auth).toBe("unknown");
  });

  it("notifies listeners and serves the cache from list()", async () => {
    const detector = new AgentDetector(providers, machine({}));
    const seen: number[] = [];
    detector.onChange((statuses) => seen.push(statuses.length));
    // list() on an empty cache starts a probe; refresh() joins that same
    // in-flight probe rather than starting a second one.
    expect(detector.list()).toEqual([]);
    await detector.refresh();
    expect(seen).toEqual([3]);
    expect(detector.list()).toHaveLength(3);
  });

  it("re-probes one agent after an install or a login", async () => {
    const executables = new Set<string>();
    const probes: DetectorProbes = {
      ...machine({}),
      isExecutable: async (file) => executables.has(file),
      exec: async () => ({ stdout: "1.0.0", stderr: "", code: 0 }),
    };
    const detector = new AgentDetector(providers, probes);
    await detector.refresh();
    executables.add("/usr/local/bin/gemini");
    const status = await detector.refreshOne("gemini-cli");
    expect(status?.installed).toBe(true);
    expect(detector.list().find((s) => s.id === "gemini-cli")?.version).toBe("1.0.0");
  });
});

describe("AgentDetector on a cold table", () => {
  const providers = [agentProvider("claude-code")!, agentProvider("codex")!];
  const deferred = <T,>() => {
    let resolve!: (value: T) => void;
    const promise = new Promise<T>((done) => (resolve = done));
    return { promise, resolve };
  };

  it("folds a refreshed row into the probe in flight, not over it, and never caches a row it did not check", async () => {
    const written: AgentStatus[][] = [];
    const gate = deferred<Record<string, string>>();
    const probes = machine({ executables: ["/usr/local/bin/claude", "/usr/local/bin/codex"], outputs: {
      "/usr/local/bin/claude --version": { stdout: "2.0.0" },
      "/usr/local/bin/claude auth status": { code: 0 },
      "/usr/local/bin/codex --version": { stdout: "0.1.0" },
      "/usr/local/bin/codex login status": { code: 0 },
    } });
    let first = true;
    const detector = new AgentDetector(providers, {
      ...probes,
      env: async () => {
        if (first) {
          first = false;
          return gate.promise;
        }
        return { PATH: "/usr/local/bin" };
      },
    }, { read: () => null, write: (statuses) => written.push(statuses) });
    const seen: AgentStatus[][] = [];
    detector.onChange((statuses) => seen.push(statuses));

    const all = detector.refresh(false);
    const one = detector.refreshOne("claude-code");
    gate.resolve({ PATH: "/usr/local/bin" });
    await Promise.all([all, one]);

    expect(seen.every((table) => table.every((row) => row.checkedAt > 0))).toBe(true);
    expect(written.every((table) => table.every((row) => row.checkedAt > 0))).toBe(true);
    expect(detector.list().map((row) => [row.id, row.installed])).toEqual([["claude-code", true], ["codex", true]]);
  });

  it("keeps the flagged rows in view when a login re-probes one agent after a cold probe failed", async () => {
    const written: AgentStatus[][] = [];
    const probes = machine({ executables: ["/usr/local/bin/claude"], outputs: {
      "/usr/local/bin/claude --version": { stdout: "2.0.0" },
      "/usr/local/bin/claude auth status": { code: 0 },
    } });
    // The cached environment is what fails; a forced re-resolve, as a login does, works.
    const detector = new AgentDetector(providers, {
      ...probes,
      env: async (force) => {
        if (!force) throw new Error("the login shell went away");
        return { PATH: "/usr/local/bin" };
      },
    }, { read: () => null, write: (statuses) => written.push(statuses) });
    const seen: AgentStatus[][] = [];
    detector.onChange((statuses) => seen.push(statuses));
    await detector.refresh(false).catch(() => undefined);

    await detector.refreshOne("claude-code");
    let table = seen.at(-1)!;
    expect(table.map((row) => [row.id, row.probeFailed === true])).toEqual([["claude-code", false], ["codex", true]]);
    expect(table.find((row) => row.id === "claude-code")?.installed).toBe(true);
    expect(written.flat().some((row) => row.checkedAt === 0)).toBe(false);

    // A later probe that fails again does not flag the row this run has checked.
    await detector.refresh(false).catch(() => undefined);
    table = seen.at(-1)!;
    expect(table.map((row) => [row.id, row.probeFailed === true])).toEqual([["claude-code", false], ["codex", true]]);
  });

  it("does not resolve the environment again for a list, and leaves no rejection unhandled when it fails", async () => {
    const forced: boolean[] = [];
    const unhandled: unknown[] = [];
    const onUnhandled = (reason: unknown) => unhandled.push(reason);
    process.on("unhandledRejection", onUnhandled);
    try {
      const detector = new AgentDetector(providers, {
        ...machine({}),
        env: async (force) => {
          forced.push(force);
          throw new Error("the login shell went away");
        },
      });
      detector.list();
      // Nothing here waits on the probe, so nobody else handles its rejection: if `list` did not,
      // it is reported once the microtasks are done.
      await new Promise<void>((resolve) => setImmediate(resolve));
      expect(forced).toEqual([false]);
      expect(unhandled).toEqual([]);
    } finally {
      process.off("unhandledRejection", onUnhandled);
    }
  });

  it("says a probe that failed with no last launch to fall back on: every row flagged, not an empty table", async () => {
    const detector = new AgentDetector(providers, {
      ...machine({}),
      env: async () => {
        throw new Error("the login shell went away");
      },
    });
    const seen: AgentStatus[][] = [];
    detector.onChange((statuses) => seen.push(statuses));
    await detector.refresh(false).catch(() => undefined);
    expect(seen).toHaveLength(1);
    expect(seen[0]!.map((row) => row.probeFailed)).toEqual([true, true]);
    expect(seen[0]!.some((row) => row.probing)).toBe(false);
  });
});

describe("the login shell environment", () => {
  it("parses env -0 output and drops the shell's own bookkeeping", () => {
    const env = parseEnv("PATH=/a:/b\0SHLVL=2\0MULTI=line1\nline2\0_=/usr/bin/env\0");
    expect(env).toEqual({ PATH: "/a:/b", MULTI: "line1\nline2" });
  });

  it("parses plain env output too", () => {
    expect(parseEnv("PATH=/a\nHOME=/Users/me\n")).toEqual({ PATH: "/a", HOME: "/Users/me" });
  });

  it("strips a host Claude Code session's variables, and only then", () => {
    const nested = stripHostSession({
      CLAUDECODE: "1",
      CLAUDE_CODE_ENTRYPOINT: "cli",
      CLAUDE_PID: "1",
      ANTHROPIC_BASE_URL: "http://host",
      ANTHROPIC_API_KEY: "sk",
      PATH: "/a",
    });
    expect(nested).toEqual({ ANTHROPIC_API_KEY: "sk", PATH: "/a" });
    const plain = { ANTHROPIC_BASE_URL: "http://proxy", PATH: "/a" };
    expect(stripHostSession(plain)).toBe(plain);
  });

  it("strips the host session's scratch and plugin directories too", () => {
    // Both are set in a host Claude Code session (seen 2026-09-29); a nested
    // `claude` would write its temp files and plugin data into the host's.
    const nested = stripHostSession({
      CLAUDECODE: "1",
      CLAUDE_TMPDIR: "/private/tmp/claude-501",
      CLAUDE_PLUGIN_DATA: "/Users/me/.claude/plugins/data/x",
      CLAUDE_CONFIG_DIR: "/Users/me/.claude-work",
      PATH: "/a",
    });
    expect(nested).toEqual({ CLAUDE_CONFIG_DIR: "/Users/me/.claude-work", PATH: "/a" });
  });
});
