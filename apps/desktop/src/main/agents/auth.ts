/**
 * Sign in to an agent: its `cli-login` method, run in a pty so the browser
 * hand-off, the device code and the "press Enter" all work (plan §5).
 *
 * API-key methods need no job — the key is in the environment or it is not,
 * and the detector reports which.
 */
import os from "node:os";

import type { AgentProvider } from "../../shared/agents";
import type { Job, JobRunner } from "./jobs";
import type { Env } from "./shell-env";

/** What to run for a login, without running it. Exported for the tests. */
export function loginCommand(
  provider: AgentProvider,
  binaryPath: string | null,
): { file: string; args: string[] } {
  const method = provider.authMethods.find((candidate) => candidate.type === "cli-login");
  if (!method || method.type !== "cli-login") {
    throw new Error(`${provider.name} has no interactive login; set one of its API keys instead`);
  }
  const file = binaryPath ?? provider.binaryNames[0];
  if (!file) {
    throw new Error(`${provider.name} has no binary to log in with`);
  }
  return { file, args: method.args };
}

export function startLogin(
  runner: JobRunner,
  provider: AgentProvider,
  binaryPath: string | null,
  env: Env,
): Job {
  const { file, args } = loginCommand(provider, binaryPath);
  return runner.start(provider.id, "login", { file, args, cwd: os.homedir(), env });
}
