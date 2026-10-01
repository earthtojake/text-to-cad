import { describe, expect, it } from "vitest";

import { AgentDetector, parseVersion, which, type DetectorProbes } from "@main/agents/detect";
import { agentProvider } from "@main/agents/registry";
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
});
