import { describe, expect, it } from "vitest";

import { gitModeAvailability, localGitMode, resolveGitMode } from "@renderer/lib/git-mode";
import type { ProjectGitInfo } from "@shared/ipc/git";

/**
 * Two choices in the composer, three `GitMode`s underneath (plan §9). What is
 * worth a test is the mapping between them: which mode "Local" is for this
 * project, and what a project that cannot make a worktree gets instead.
 */
function info(overrides: Partial<ProjectGitInfo>): ProjectGitInfo {
  return {
    isRepository: true,
    branch: "main",
    upstream: null,
    defaultBranch: "main",
    dirty: false,
    detached: false,
    unborn: false,
    hasRemote: false,
    hasGh: false,
    worktreeCount: 0,
    worktreeDir: "",
    ...overrides,
  };
}

describe("the git mode a session runs in", () => {
  it("calls the project's own folder Local, whether or not it is a repository", () => {
    expect(localGitMode(info({}))).toBe("checkout");
    expect(localGitMode(info({ isRepository: false }))).toBe("none");
    // Nothing read yet: assume the ordinary case rather than flickering.
    expect(localGitMode(null)).toBe("checkout");
  });

  it("falls back to Local when the project cannot make a worktree", () => {
    expect(resolveGitMode("worktree", info({}))).toBe("worktree");
    expect(resolveGitMode("worktree", info({ isRepository: false }))).toBe("none");
    expect(resolveGitMode("worktree", info({ unborn: true }))).toBe("checkout");
    expect(resolveGitMode("checkout", info({ isRepository: false }))).toBe("none");
  });

  it("says why a worktree is not on offer", () => {
    expect(gitModeAvailability("worktree", info({ isRepository: false }))).toMatchObject({
      available: false,
      reason: expect.stringContaining("not a git repository"),
    });
    expect(gitModeAvailability("worktree", info({ unborn: true }))).toMatchObject({
      available: false,
      reason: expect.stringContaining("no commits"),
    });
  });
});
