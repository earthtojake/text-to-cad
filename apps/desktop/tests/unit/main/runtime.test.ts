import { describe, expect, it } from "vitest";

describe("mainCheckoutOfWorktree", () => {
  it("follows a worktree's gitdir back to the main checkout", async () => {
    const fs = await import("node:fs");
    const os = await import("node:os");
    const path = await import("node:path");
    const { mainCheckoutOfWorktree } = await import("@main/cad/runtime");
    const main = fs.mkdtempSync(path.join(os.tmpdir(), "hardcore-main-"));
    const worktree = fs.mkdtempSync(path.join(os.tmpdir(), "hardcore-wt-"));
    fs.mkdirSync(path.join(main, ".git", "worktrees", "wt"), { recursive: true });
    fs.writeFileSync(path.join(worktree, ".git"), `gitdir: ${path.join(main, ".git", "worktrees", "wt")}\n`);
    expect(mainCheckoutOfWorktree(worktree)).toBe(main);
    fs.rmSync(path.join(worktree, ".git"));
    fs.mkdirSync(path.join(worktree, ".git"));
    expect(mainCheckoutOfWorktree(worktree)).toBeNull();
    expect(mainCheckoutOfWorktree(path.join(os.tmpdir(), "does-not-exist"))).toBeNull();
  });
});
