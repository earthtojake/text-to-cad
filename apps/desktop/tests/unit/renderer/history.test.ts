import { beforeEach, describe, expect, it } from "vitest";

import { attachHistory, findLive, useHistory } from "@renderer/state/history";
import { useProjects } from "@renderer/state/projects";
import { useSessions } from "@renderer/state/sessions";
import type { Session } from "@shared/types";

/**
 * The top level's back and forward (`src/renderer/state/history.ts`).
 *
 * Entries are recorded by watching the selection, so these tests drive the
 * two stores the way the sidebar's rows and `Cmd+N` do and then assert what
 * the stack looks like — including the two things that are easy to get wrong:
 * back and forward must not push, and an entry whose session has been deleted
 * must be stepped over rather than landed on.
 */

const project = (id: string) => ({ id, name: id, path: `/tmp/${id}`, createdAt: 0 });

function session(id: string, projectId: string): Session {
  return {
    id,
    projectId,
    agentId: "fake",
    title: id,
    cwd: `/tmp/${projectId}`,
    gitMode: "none",
    createdAt: 0,
    updatedAt: 0,
    status: "idle",
    pinned: false,
    acpSessionId: null,
    changedFiles: 0,
    insertions: 0,
    deletions: 0,
    archived: false,
    sessionHead: null,
    turnHead: null,
    turnStartedAt: null,
  };
}

/** The selection landing, the way a click does: state, then the microtask. */
async function land(change: () => void) {
  change();
  await Promise.resolve();
}

let detach: () => void;

beforeEach(() => {
  useHistory.setState({ entries: [], index: -1 });
  useProjects.setState({ projects: [project("p1"), project("p2")], ready: true, activeId: null });
  useSessions.setState({
    sessions: [session("s1", "p1"), session("s2", "p1"), session("s3", "p2")],
    ready: true,
    activeId: null,
  });
  detach?.();
  detach = attachHistory();
});

describe("the top-level history", () => {
  it("records a project's new-session screen and each session once", async () => {
    await land(() => useProjects.getState().setActive("p1"));
    await land(() => useSessions.getState().select("s1"));
    await land(() => useSessions.getState().select("s2"));
    // `New chat` — the same selection the sidebar's link makes.
    await land(() => useSessions.getState().setActive(null));

    expect(useHistory.getState().entries).toEqual([
      { projectId: "p1", sessionId: null },
      { projectId: "p1", sessionId: "s1" },
      { projectId: "p1", sessionId: "s2" },
      { projectId: "p1", sessionId: null },
    ]);
    expect(useHistory.getState().index).toBe(3);
  });

  // `select` sets the project and then the session, which is two store
  // writes for one navigation.
  it("files one entry for a session in another project", async () => {
    await land(() => useProjects.getState().setActive("p1"));
    await land(() => useSessions.getState().select("s3"));
    expect(useHistory.getState().entries).toEqual([
      { projectId: "p1", sessionId: null },
      { projectId: "p2", sessionId: "s3" },
    ]);
  });

  it("does not record the same location twice", async () => {
    await land(() => useProjects.getState().setActive("p1"));
    await land(() => useSessions.getState().select("s1"));
    await land(() => useSessions.getState().select("s1"));
    expect(useHistory.getState().entries).toHaveLength(2);
  });

  it("moves the cursor on back and forward without pushing", async () => {
    await land(() => useProjects.getState().setActive("p1"));
    await land(() => useSessions.getState().select("s1"));
    await land(() => useSessions.getState().select("s2"));

    await land(() => useHistory.getState().back());
    expect(useSessions.getState().activeId).toBe("s1");
    expect(useHistory.getState()).toMatchObject({ index: 1 });
    expect(useHistory.getState().entries).toHaveLength(3);

    await land(() => useHistory.getState().back());
    expect(useSessions.getState().activeId).toBeNull();
    expect(useHistory.getState()).toMatchObject({ index: 0 });
    expect(useHistory.getState().entries).toHaveLength(3);

    await land(() => useHistory.getState().forward());
    expect(useSessions.getState().activeId).toBe("s1");
    expect(useHistory.getState()).toMatchObject({ index: 1 });
    expect(useHistory.getState().entries).toHaveLength(3);
  });

  it("has nothing to go to at either end", async () => {
    const live = { projectIds: ["p1"], sessionIds: ["s1", "s2"] };
    await land(() => useProjects.getState().setActive("p1"));
    expect(findLive(useHistory.getState().entries, 0, -1, live)).toBe(-1);
    expect(findLive(useHistory.getState().entries, 0, 1, live)).toBe(-1);

    await land(() => useSessions.getState().select("s1"));
    expect(findLive(useHistory.getState().entries, 1, -1, live)).toBe(0);
    expect(findLive(useHistory.getState().entries, 1, 1, live)).toBe(-1);
  });

  it("drops the forward stack when a new location is recorded", async () => {
    await land(() => useProjects.getState().setActive("p1"));
    await land(() => useSessions.getState().select("s1"));
    await land(() => useSessions.getState().select("s2"));
    await land(() => useHistory.getState().back());
    await land(() => useHistory.getState().back());
    await land(() => useSessions.getState().select("s3"));

    expect(useHistory.getState().entries).toEqual([
      { projectId: "p1", sessionId: null },
      { projectId: "p2", sessionId: "s3" },
    ]);
    expect(useHistory.getState().index).toBe(1);
  });

  it("steps over an entry whose session is gone", async () => {
    await land(() => useProjects.getState().setActive("p1"));
    await land(() => useSessions.getState().select("s1"));
    await land(() => useSessions.getState().select("s2"));
    // s1 deleted: `sessions.changed` arrives with it gone.
    await land(() => useSessions.getState().receive([session("s2", "p1"), session("s3", "p2")]));

    await land(() => useHistory.getState().back());
    expect(useHistory.getState().index).toBe(0);
    expect(useSessions.getState().activeId).toBeNull();
    // And the entry is still in the stack, so forward finds the way out.
    expect(useHistory.getState().entries).toHaveLength(3);
    await land(() => useHistory.getState().forward());
    expect(useHistory.getState().index).toBe(2);
    expect(useSessions.getState().activeId).toBe("s2");
  });

  it("steps over entries in a project that is gone", async () => {
    await land(() => useProjects.getState().setActive("p1"));
    await land(() => useSessions.getState().select("s3"));
    await land(() => useProjects.getState().setActive("p1"));
    await land(() => useProjects.getState().receive([project("p1")]));

    await land(() => useHistory.getState().back());
    expect(useHistory.getState().index).toBe(0);
    expect(useProjects.getState().activeId).toBe("p1");
  });

  it("records nothing while no project is bound", async () => {
    await land(() => useSessions.getState().setActive(null));
    expect(useHistory.getState().entries).toEqual([]);
  });
});
