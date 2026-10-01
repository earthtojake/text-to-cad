/**
 * Which agents are on this machine (plan §5).
 *
 * Probes every provider's binaries along the login-shell PATH, reads a
 * version, and asks the CLI (or the environment, or a credential file)
 * whether the user is signed in. The table is kept in memory and, through
 * `./cache.ts`, between launches, where the next launch answers from it (rows
 * flagged `probing`) until its own probe lands; `refresh()` re-runs
 * everything and `onChange` fans the new table out. Nothing here spawns an
 * agent — the Agents page must be able to show state without starting
 * anything.
 *
 * The probes are injectable so the unit tests can run the detector against a
 * fake filesystem and a fake `--version` without a real PATH.
 */
import { execFile } from "node:child_process";
import { access, constants, stat } from "node:fs/promises";
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

/**
 * How long anything that must not act on the last launch's rows waits for this
 * launch's probe: a cold `agents.list`, a session that would refuse an agent
 * as "not installed". The probe starts with the window, so it is usually done
 * or nearly; this bounds a login shell that never returns.
 */
export const PROBE_WAIT_MS = 3_000;

/**
 * Where the last table is kept between launches (`./cache.ts`). Read once, at
 * the first question; written after every finished probe. A cache that cannot
 * be read or written is no cache: neither may fail a probe.
 */
export type AgentsCache = {
  read: () => AgentStatus[] | null;
  write: (statuses: AgentStatus[]) => void;
};

/** What an auth probe prints when the person is signed out (`Not logged in`, `{"loggedIn":false}`). */
const SIGNED_OUT = /not (logged|signed) in|logged out|signed out|"loggedIn"\s*:\s*false|not authenticated|unauthenticated|login required/i;

export const nodeProbes: DetectorProbes = {
  env: (force) => loginEnv({ force }),
  isExecutable: async (file) => {
    try {
      // `access(X_OK)` alone is true of a directory (search permission), so a
      // folder named `claude` on PATH would read as the CLI.
      if (!(await stat(file)).isFile()) {
        return false;
      }
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
  /** This run has finished a probe; until then any rows held are the last launch's. */
  private probed = false;
  private seeded = false;
  /** Providers `refreshOne` has checked in this run, before any whole table has: their rows are not the last launch's. */
  private readonly freshIds = new Set<string>();

  constructor(
    private readonly providers: readonly AgentProvider[] = AGENT_PROVIDERS,
    private readonly probes: DetectorProbes = nodeProbes,
    private readonly cache: AgentsCache | null = null,
  ) {}

  /**
   * The table: this run's once a probe has finished, the last launch's before
   * that (a machine's agents rarely change between launches, and a wrong
   * `installed` for a second is better than none — an empty table reads as "not
   * installed" to the session manager); empty on a first launch.
   */
  list(): AgentStatus[] {
    this.seed();
    if (!this.probed && !this.inflight) {
      // The environment already resolved is good enough for a read; a caller that asked for the
      // table did not ask for a second login shell. The failure reaches listeners (`probeAll`) and
      // the callers that wait on `settled()`: this one has nobody to tell.
      this.refresh(false).catch((error: unknown) => console.info(`[agents] the probe failed: ${String(error)}`));
    }
    return this.statuses;
  }

  /** The last launch's table, once, unless a probe has answered first. */
  private seed() {
    if (this.seeded) {
      return;
    }
    this.seeded = true;
    try {
      const cached = this.cache?.read();
      if (cached && this.statuses.length === 0) {
        this.statuses = cached;
      }
    } catch (error) {
      console.info(`[agents] the cached table was not read: ${String(error)}`);
    }
  }

  private persist() {
    try {
      // A placeholder for a probe that failed cold (`checkedAt` 0) is not something this machine said.
      this.cache?.write(this.statuses.filter((status) => status.checkedAt > 0));
    } catch (error) {
      console.info(`[agents] the table was not cached: ${String(error)}`);
    }
  }

  /**
   * The table for `agents.list`: the cache when there is one, and otherwise
   * the first probe's answer if it arrives within `waitMs`. An empty cache
   * answered at once is a renderer that draws "no agents" and then redraws
   * when `agents.status` lands — the model chip waited on that second answer
   * on every cold launch. A probe that hangs past the bound (a login shell
   * that never returns) still gets the old answer, empty, and the broadcast
   * follows as before.
   *
   * A warm launch answers at once instead: the last launch's table, every row
   * marked `probing`, while the probe runs. The fresh table replaces it on
   * `agents.status` (a row from the probe never carries the mark), so what a
   * screen draws from this answer is provisional and says so.
   */
  async listWithin(waitMs: number): Promise<AgentStatus[]> {
    const cached = this.list();
    if (!this.probed && cached.length > 0) {
      // A retry after a failed probe starts over: the failure's mark is not this run's.
      return cached.map((status) =>
        this.freshIds.has(status.id) ? status : { ...status, probing: true, probeFailed: undefined },
      );
    }
    const inflight = this.inflight;
    if (cached.length > 0 || !inflight) {
      return cached;
    }
    let timer: ReturnType<typeof setTimeout> | undefined;
    const bound = new Promise<AgentStatus[]>((resolve) => {
      timer = setTimeout(() => resolve(this.statuses), waitMs);
    });
    try {
      return await Promise.race([inflight.catch(() => this.statuses), bound]);
    } finally {
      clearTimeout(timer);
    }
  }

  /**
   * The first table: the probe in flight, the cache, or a new probe — never a
   * second probe on top of one already running or finished. What launch
   * starts, and what the adapter pre-warm waits on.
   */
  settled(): Promise<AgentStatus[]> {
    if (this.inflight) {
      return this.inflight;
    }
    this.seed();
    return this.probed ? Promise.resolve(this.statuses) : this.refresh(false);
  }

  /**
   * This launch's table, or null when no probe has finished within `waitMs`
   * (a hung login shell, or a probe that failed). For a caller about to act on
   * a row — refuse an agent as not installed, hand its binary to a login —
   * where the last launch's rows are a guess: the CLI may have been installed
   * since. Null means "unknown", never "absent".
   */
  async freshWithin(waitMs: number): Promise<AgentStatus[] | null> {
    if (this.probed) {
      return this.statuses;
    }
    let timer: ReturnType<typeof setTimeout> | undefined;
    const bound = new Promise<null>((resolve) => {
      timer = setTimeout(() => resolve(null), waitMs);
    });
    try {
      return await Promise.race([this.settled().catch(() => null), bound]);
    } finally {
      clearTimeout(timer);
    }
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
    if (!this.probed) {
      // A probe in flight would overwrite this row when it lands, and the rows held before it
      // are the last launch's or none: fold this one into the fresh table, not into them.
      await this.settled().catch(() => undefined);
    }
    const env = await this.probes.env(true);
    this.env = env;
    const status = await this.probe(provider, env);
    this.freshIds.add(agentId);
    // A provider with no row yet is left out rather than drawn as "not installed". The flagged
    // placeholders for a probe that failed cold stay, so the failure and the other agents stay on
    // screen as unknown; `persist` is where they are left out, and they are never cached as such.
    this.statuses = this.providers.flatMap((candidate) => {
      const row = candidate.id === agentId ? status : this.statuses.find((s) => s.id === candidate.id);
      return row ? [row] : [];
    });
    this.persist();
    this.emit();
    return status;
  }

  private async probeAll(force: boolean): Promise<AgentStatus[]> {
    try {
      const env = await this.probes.env(force);
      this.env = env;
      const statuses = await Promise.all(this.providers.map((provider) => this.probe(provider, env)));
      this.statuses = statuses;
    } catch (error) {
      if (!this.probed) {
        // No fresh table is coming: the last launch's rows would stay "probing" for good. They stay,
        // unmarked but flagged: an empty table would read as "no agent ready — sign in", the wrong cause.
        // With no last launch's either, the flagged rows are the registry's, so the failure reaches
        // the renderer as one all the same and not as a list that is still on its way.
        this.statuses = (this.statuses.length > 0 ? this.statuses : this.providers.map(missing)).map(
          // Not a row `refreshOne` has since checked: that one is this run's, and says so.
          (status) => (this.freshIds.has(status.id) ? status : { ...status, probing: undefined, probeFailed: true }),
        );
        this.emit();
      }
      throw error;
    }
    this.probed = true;
    this.persist();
    this.emit();
    return this.statuses;
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
        // Only a failure that reads as "signed out" is one. Anything else — a
        // CLI too old for `auth status`, a crash — says nothing about the
        // login, and the credential file below still can.
        if (result.code !== null && SIGNED_OUT.test(`${result.stdout}\n${result.stderr}`)) {
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
