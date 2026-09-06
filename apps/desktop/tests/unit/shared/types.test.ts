import { describe, expect, it } from "vitest";

import {
  ExplorerTabSchema,
  SessionSchema,
  SettingsSchema,
  defaultSettings,
} from "@shared/types";

describe("Settings", () => {
  it("parses an empty object into a complete settings record", () => {
    const settings = defaultSettings();
    expect(settings.theme).toBe("system");
    expect(settings.defaultGitMode).toBe("checkout");
    expect(settings.branchPrefix).toBe("hardcore/");
    expect(settings.layout.sidebar + settings.layout.session + settings.layout.explorer).toBe(100);
  });

  it("keeps telemetry off unless it is asked for", () => {
    expect(defaultSettings().telemetry).toBe(false);
  });

  it("fills in fields a row written by an older build is missing", () => {
    const fromOldRow = SettingsSchema.parse({ theme: "dark" });
    expect(fromOldRow.theme).toBe("dark");
    expect(fromOldRow.worktreeKeepLimit).toBe(10);
  });

  it("drops keys it does not know, which is how window state hides in the same table", () => {
    const parsed = SettingsSchema.parse({ __window: { width: 800, height: 600 } });
    expect("__window" in parsed).toBe(false);
  });
});

describe("Session", () => {
  const base = {
    id: "s1",
    projectId: "p1",
    agentId: "claude-code",
    cwd: "/tmp/project",
    gitMode: "worktree",
    branch: "hardcore/wrist",
    title: "Model the wrist",
    createdAt: 1,
    updatedAt: 2,
    status: "running",
  };

  it("accepts a worktree session", () => {
    expect(SessionSchema.parse(base).branch).toBe("hardcore/wrist");
  });

  it("rejects a git mode that is not one of the three", () => {
    expect(SessionSchema.safeParse({ ...base, gitMode: "submodule" }).success).toBe(false);
  });
});

describe("ExplorerTab", () => {
  it("discriminates the four kinds", () => {
    const file = ExplorerTabSchema.parse({
      id: "t1",
      sessionId: "s1",
      order: 0,
      kind: "file",
      path: "/tmp/a.step",
    });
    expect(file.kind === "file" && file.viewSource).toBe(false);

    const terminal = ExplorerTabSchema.parse({
      id: "t2",
      sessionId: "s1",
      order: 1,
      kind: "terminal",
      ptyId: null,
    });
    expect(terminal.kind).toBe("terminal");
  });

  it("has no kind for a bottom panel, because there is not one", () => {
    expect(
      ExplorerTabSchema.safeParse({ id: "t3", sessionId: "s1", order: 0, kind: "panel" }).success,
    ).toBe(false);
  });
});
