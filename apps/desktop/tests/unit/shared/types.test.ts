import { describe, expect, it } from "vitest";

import {
  ExplorerTabSchema,
  REVIEW_SCOPE_LABELS,
  ReviewScopeSchema,
  SessionSchema,
  SettingsSchema,
  defaultSettings,
  diffScopeFor,
  resolveDiffScope,
  scopeNeedsSession,
} from "@shared/types";

describe("Settings", () => {
  it("parses an empty object into a complete settings record", () => {
    const settings = defaultSettings();
    expect(settings.theme).toBe("system");
    expect(settings.defaultGitMode).toBe("checkout");
    expect(settings.branchPrefix).toBe("hardcore/");
    // Pixels, Codex's proportions: a 230px sidebar and a 560px session column.
    expect(settings.layout).toMatchObject({ sidebarWidth: 230, sessionWidth: 560, sidebarCollapsed: false });
  });

  it("has telemetry on with an opt-out (plan §14)", () => {
    expect(defaultSettings().telemetry).toBe(true);
    // And the opt-out survives, which is the half that matters: a stored false
    // is not a missing field, so a later build cannot default it back on.
    expect(SettingsSchema.parse({ telemetry: false }).telemetry).toBe(false);
  });

  it("fills in fields a row written by an older build is missing", () => {
    // Settings rows are per-key JSON in sqlite, so a new field is not a schema
    // migration: it is a default, and this is the test that it is a complete
    // one. A field without a default would make every older install parse to a
    // half-formed object.
    const fromOldRow = SettingsSchema.parse({ theme: "dark" });
    expect(fromOldRow.theme).toBe("dark");
    expect(fromOldRow.worktreeKeepLimit).toBe(10);
    expect(fromOldRow.accentColor).toBe("neutral");
    expect(fromOldRow.uiFontSize).toBe("default");
    expect(fromOldRow.fileOpenDestination).toBe("reveal");
    expect(fromOldRow.notificationSoundTiming).toBe("unfocused");
    expect(fromOldRow.agentOverrides).toEqual({});
    expect(fromOldRow.commitInstructions).toBe("");
  });

  it("gives every field a default, so no row is ever half-formed", () => {
    const parsed = defaultSettings();
    for (const key of Object.keys(SettingsSchema.shape)) {
      expect(parsed, key).toHaveProperty(key);
      expect(parsed[key as keyof typeof parsed], key).not.toBeUndefined();
    }
  });

  it("stores the launch amendments an agent's drawer writes", () => {
    const parsed = SettingsSchema.parse({
      agentOverrides: { codex: { extraArgs: ["--verbose"], env: { CODEX_HOME: "/tmp" } } },
    });
    expect(parsed.agentOverrides["codex"]).toEqual({
      extraArgs: ["--verbose"],
      env: { CODEX_HOME: "/tmp" },
    });
    // Both halves are optional; an entry with neither is still a valid entry.
    expect(SettingsSchema.parse({ agentOverrides: { codex: {} } }).agentOverrides["codex"]).toEqual({
      extraArgs: [],
      env: {},
    });
  });

  it("refuses an accent or a font size it does not have tokens for", () => {
    expect(SettingsSchema.safeParse({ accentColor: "chartreuse" }).success).toBe(false);
    expect(SettingsSchema.safeParse({ uiFontSize: "enormous" }).success).toBe(false);
    expect(SettingsSchema.safeParse({ worktreeKeepLimit: 0 }).success).toBe(false);
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
      projectId: "p1",
      order: 0,
      kind: "file",
      path: "/tmp/a.step",
    });
    expect(file.kind === "file" && file.viewSource).toBe(false);

    const terminal = ExplorerTabSchema.parse({
      id: "t2",
      projectId: "p1",
      order: 1,
      kind: "terminal",
      ptyId: null,
    });
    expect(terminal.kind).toBe("terminal");
  });

  it("has no kind for a bottom panel, because there is not one", () => {
    expect(
      ExplorerTabSchema.safeParse({ id: "t3", projectId: "p1", order: 0, kind: "panel" }).success,
    ).toBe(false);
  });
});

describe("review scopes", () => {
  it("names every scope the dropdown offers", () => {
    for (const scope of ReviewScopeSchema.options) {
      expect(REVIEW_SCOPE_LABELS[scope]).toBeTruthy();
    }
    expect(ReviewScopeSchema.options).toContain("turn");
    expect(ReviewScopeSchema.options).toContain("session");
  });

  it("turns a named scope into the one git is asked for", () => {
    expect(diffScopeFor("all")).toEqual({ kind: "working-tree" });
    expect(diffScopeFor("4h")).toEqual({ kind: "since", since: "4 hours ago" });
    expect(diffScopeFor("turn")).toEqual({ kind: "turn" });
    expect(scopeNeedsSession("turn")).toBe(true);
    expect(scopeNeedsSession("session")).toBe(true);
    expect(scopeNeedsSession("24h")).toBe(false);
  });

  it("resolves the two session scopes from the session's recorded marks", () => {
    const marks = { turnHead: "bbb", sessionHead: "aaa" };

    // An open-ended range: git measures it against the working tree, so an
    // edit the agent has not committed is in the answer.
    expect(resolveDiffScope({ kind: "session" }, marks)).toEqual({ kind: "range", from: "aaa" });
    expect(resolveDiffScope({ kind: "turn" }, marks)).toEqual({ kind: "range", from: "bbb" });

    // No session, or no mark on it: the working tree, which is the honest
    // answer — everything in it is new since a point that was never recorded.
    expect(resolveDiffScope({ kind: "turn" }, null)).toEqual({ kind: "working-tree" });
    expect(
      resolveDiffScope({ kind: "turn" }, { turnHead: null, sessionHead: "aaa" }),
    ).toEqual({ kind: "working-tree" });

    // Everything else passes through untouched, including no scope at all.
    expect(resolveDiffScope(undefined, marks)).toEqual({ kind: "working-tree" });
    expect(resolveDiffScope({ kind: "since", since: "1 hour ago" }, marks)).toEqual({
      kind: "since",
      since: "1 hour ago",
    });
  });
});
