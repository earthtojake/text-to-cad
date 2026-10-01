/**
 * `gitEnv()` on Windows: there is no login shell to ask, so the captured
 * environment is not merged (the process's own stays). The listener is the
 * one `git.ts` registers with `onLoginEnv`; the test fires it by hand.
 */
import { afterEach, expect, it, vi } from "vitest";

const hooks = vi.hoisted(() => ({ listeners: [] as ((env: Record<string, string>) => void)[] }));
vi.mock("@main/agents/shell-env", () => ({
  onLoginEnv: (listener: (env: Record<string, string>) => void) => { hooks.listeners.push(listener); },
  loginEnv: async () => ({}),
}));

import * as git from "@main/projects/git";

afterEach(() => {
  vi.restoreAllMocks();
  git.setLoginEnvForGit(null);
});

function capture(platform: NodeJS.Platform): void {
  vi.spyOn(process, "platform", "get").mockReturnValue(platform);
  for (const listener of hooks.listeners) listener({ PATH: "/login-shell-marker/bin", LOGIN_ONLY: "1" });
}

it("does not merge the login environment on win32", () => {
  capture("win32");
  const env = git.gitEnv();
  expect(env.LOGIN_ONLY, "the login shell's variables must not reach git on win32").toBeUndefined();
  expect(env.PATH).not.toBe("/login-shell-marker/bin");
});

it("merges the login environment elsewhere (the control)", () => {
  capture("darwin");
  const env = git.gitEnv();
  expect(env.LOGIN_ONLY).toBe("1");
  expect(env.PATH).toBe("/login-shell-marker/bin");
});

it("still pins the language to C on win32 (the pin is not platform-specific)", () => {
  capture("win32");
  expect(git.gitEnv()).toMatchObject({ LC_ALL: "C", LANG: "C" });
});
