/**
 * Install an agent: one of the provider's documented commands, run through
 * the user's login shell in a pty (plan §5). The shell is what makes `curl …
 * | bash` and `brew install` behave as they would in Terminal — same PATH,
 * same Homebrew prefix, same npm prefix.
 */
import os from "node:os";

import type { AgentProvider, Platform } from "../../shared/agents";
import type { Job, JobRunner } from "./jobs";
import type { Env } from "./shell-env";

export function currentPlatform(platform: NodeJS.Platform = process.platform): Platform {
  switch (platform) {
    case "darwin":
      return "macos";
    case "win32":
      return "windows";
    default:
      return "linux";
  }
}

/** The shell line and how to run it, without running it. Exported for the tests. */
export function installCommand(
  provider: AgentProvider,
  platform: Platform,
  index: number,
  env: Env,
): { file: string; args: string[]; command: string } {
  const choices = provider.install[platform];
  const choice = choices[index] ?? choices[0];
  if (!choice) {
    throw new Error(`${provider.name} has no install command for ${platform}`);
  }
  if (platform === "windows") {
    return {
      file: "powershell.exe",
      args: ["-NoProfile", "-Command", choice.command],
      command: choice.command,
    };
  }
  const shell = env.SHELL || "/bin/sh";
  return { file: shell, args: ["-lc", choice.command], command: choice.command };
}

export function startInstall(
  runner: JobRunner,
  provider: AgentProvider,
  env: Env,
  options: { platform?: Platform; index?: number } = {},
): Job {
  const platform = options.platform ?? currentPlatform();
  const { file, args } = installCommand(provider, platform, options.index ?? 0, env);
  return runner.start(provider.id, "install", { file, args, cwd: os.homedir(), env });
}
