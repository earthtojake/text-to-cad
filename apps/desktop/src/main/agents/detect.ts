/**
 * Which agents are on this machine (plan §5).
 *
 * Probes every provider's binaries along the login-shell PATH, reads a
 * version, and asks the CLI (or the environment, or a credential file)
 * whether the user is signed in. Results are cached; `refresh()` re-runs
 * everything and `onChange` fans the new table out. Nothing here spawns an
 * agent — the Agents page must be able to show state without starting
 * anything.
 *
 * The probes are injectable so the unit tests can run the detector against a
 * fake filesystem and a fake `--version` without a real PATH.
 */
import { execFile } from "node:child_process";
import { access, constants } from "node:fs/promises";
import os from "node:os";
import path from "node:path";

import type { AgentProvider, AgentStatus, AuthState } from "../../shared/agents";
import { trackChild } from "../children";
import { AGENT_PROVIDERS } from "./registry";
import { loginEnv, type Env } from "./shell-env";

export type ExecResult = { stdout: string; stderr: string; code: number | null };

export type DetectorProbes = {
  /** Resolve the environment agents run in. */
  env: (force: boolean) => Promise<Env>;
  /** Is this path an executable file? */
  isExecutable: (file: string) => Promise<boolean>;
  /** Does this path exist at all? */
  exists: (file: string) => Promise<boolean>;
  /** Run a binary with argv and answer with its output and exit code. */
  exec: (file: string, args: string[], env: Env) => Promise<ExecResult>;
  /** The user's home directory. */
  homeDir: () => string;
  platform: NodeJS.Platform;
};

const EXEC_TIMEOUT_MS = 10_000;

export const nodeProbes: DetectorProbes = {
  env: (force) => loginEnv({ force }),
  isExecutable: async (file) => {
    try {
      await access(file, constants.X_OK);
      return true;
    } catch {
      return false;
    }
  },
  exists: async (file) => {
    try {
      await access(file, constants.F_OK);
      return true;
    } catch {
      return false;
    }
  },
  exec: (file, args, env) =>
    new Promise((resolve) => {
      trackChild(execFile(
        file,
        args,
        { env, timeout: EXEC_TIMEOUT_MS, maxBuffer: 1024 * 1024, encoding: "utf8" },
        (error, stdout, stderr) => {
          const code =
            error && typeof (error as { code?: unknown }).code === "number"
              ? ((error as { code: number }).code ?? null)
              : error
                ? null
                : 0;
          resolve({ stdout, stderr, code });
        },
      ), "probe");
    }),
  homeDir: () => os.homedir(),
  platform: process.platform,
};

/** `which`, without shelling out: walk PATH, honour PATHEXT on Windows. */
export async function which(name: string, env: Env, probes: DetectorProbes): Promise<string | null> {
  const pathValue = env.PATH ?? env.Path ?? "";
  const dirs = pathValue.split(path.delimiter).filter(Boolean);
  const extensions =
    probes.platform === "win32"
      ? (env.PATHEXT ?? ".COM;.EXE;.BAT;.CMD").split(";").filter(Boolean)
      : [""];
  for (const dir of dirs) {
    for (const ext of extensions) {
      const candidate = path.join(dir, name + ext);
      if (await probes.isExecutable(candidate)) {
        return candidate;
      }
    }
  }
  return null;
}

/** First `x.y.z` in a `--version` output, or null. Exported for the tests. */
export function parseVersion(output: string): string | null {
  const match = /(\d+)\.(\d+)\.(\d+)(?:[-+][0-9A-Za-z.-]+)?/.exec(output);
  return match ? match[0] : null;
}

export class AgentDetector {
  private statuses: AgentStatus[] = [];
  private inflight: Promise<AgentStatus[]> | null = null;
  private readonly listeners = new Set<(statuses: AgentStatus[]) => void>();
  private env: Env | null = null;

  constructor(
    private readonly providers: readonly AgentProvider[] = AGENT_PROVIDERS,
    private readonly probes: DetectorProbes = nodeProbes,
  ) {}

  /** The cached table; empty (not blocking) before the first probe finishes. */
  list(): AgentStatus[] {
    if (this.statuses.length === 0 && !this.inflight) {
      void this.refresh();
    }
    return this.statuses;
  }

  /** The environment the last probe used, for spawning agents. */
  async environment(): Promise<Env> {
    return this.env ?? (await this.probes.env(false));
  }

  onChange(listener: (statuses: AgentStatus[]) => void): () => void {
    this.listeners.add(listener);
    return () => {
      this.listeners.delete(listener);
    };
  }

  /** Re-resolve the shell environment and re-probe everything. */
  refresh(force = true): Promise<AgentStatus[]> {
    if (!this.inflight) {
      this.inflight = this.probeAll(force).finally(() => {
        this.inflight = null;
      });
    }
    return this.inflight;
  }

  /** Probe one provider now (after an install or a login). */
  async refreshOne(agentId: string): Promise<AgentStatus | null> {
    const provider = this.providers.find((candidate) => candidate.id === agentId);
    if (!provider) {
      return null;
    }
    const env = await this.probes.env(true);
    this.env = env;
    const status = await this.probe(provider, env);
    this.statuses = this.providers.map(
      (candidate) =>
        (candidate.id === agentId ? status : this.statuses.find((s) => s.id === candidate.id)) ??
        missing(candidate),
    );
    this.emit();
    return status;
  }

  private async probeAll(force: boolean): Promise<AgentStatus[]> {
    const env = await this.probes.env(force);
    this.env = env;
    const statuses = await Promise.all(this.providers.map((provider) => this.probe(provider, env)));
    this.statuses = statuses;
    this.emit();
    return statuses;
  }

  private async probe(provider: AgentProvider, env: Env): Promise<AgentStatus> {
    let binaryPath: string | null = null;
    for (const name of provider.binaryNames) {
      binaryPath = await which(name, env, this.probes);
      if (binaryPath) {
        break;
      }
    }
    const installed = binaryPath !== null;
    const version = installed ? await this.version(provider, binaryPath!, env) : null;
    const auth = await this.authState(provider, binaryPath, env);
    return { ...provider, installed, binaryPath, version, auth, checkedAt: Date.now() };
  }

  private async version(provider: AgentProvider, binary: string, env: Env): Promise<string | null> {
    try {
      const result = await this.probes.exec(binary, provider.versionArgs, env);
      return parseVersion(result.stdout) ?? parseVersion(result.stderr);
    } catch {
      return null;
    }
  }

  private async authState(
    provider: AgentProvider,
    binary: string | null,
    env: Env,
  ): Promise<AuthState> {
    if (provider.authMethods.every((method) => method.type === "none")) {
      return "not-required";
    }
    if (provider.authProbe.envVars.some((name) => Boolean(env[name]))) {
      return "authenticated";
    }
    if (binary && provider.authProbe.checkArgs) {
      try {
        const result = await this.probes.exec(binary, provider.authProbe.checkArgs, env);
        if (result.code === 0) {
          return "authenticated";
        }
        if (result.code !== null) {
          return "unauthenticated";
        }
      } catch {
        // Fall through to the file probe.
      }
    }
    const home = this.probes.homeDir();
    for (const file of provider.authProbe.files) {
      if (await this.probes.exists(path.join(home, file))) {
        return "authenticated";
      }
    }
    return "unknown";
  }

  private emit() {
    for (const listener of this.listeners) {
      listener(this.statuses);
    }
  }
}

function missing(provider: AgentProvider): AgentStatus {
  return {
    ...provider,
    installed: false,
    binaryPath: null,
    version: null,
    auth: "unknown",
    checkedAt: 0,
  };
}
