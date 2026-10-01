/**
 * Archive, pin and delete from the menus say so when main refuses them, in the shape of the rename
 * sentence, and a refused archive or delete does not walk the user away from the open session.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { toast } from "sonner";

import { useSessions } from "@renderer/state/sessions";
import type { Session } from "@shared/types";

vi.mock("sonner", () => ({ toast: { error: vi.fn(), success: vi.fn(), message: vi.fn() } }));

const row = (id: string) => ({ id, projectId: "p1", title: id }) as Session;

beforeEach(() => {
  vi.mocked(toast.error).mockClear();
  useSessions.setState({ sessions: [row("s1")], ready: true, activeId: "s1" });
});

describe("a refused menu write", () => {
  it("archive toasts and keeps the session open", async () => {
    vi.mocked(window.textToCad.sessions.archive).mockRejectedValueOnce(new Error("disk full"));
    await useSessions.getState().archive("s1", true);
    expect(toast.error).toHaveBeenCalledWith("Could not archive the thread: disk full");
    expect(useSessions.getState().activeId).toBe("s1");
  });

  it("unarchive, pin, unpin and delete each toast their own sentence", async () => {
    const { sessions } = window.textToCad;
    vi.mocked(sessions.archive).mockRejectedValueOnce(new Error("no"));
    await useSessions.getState().archive("s1", false);
    vi.mocked(sessions.setPinned).mockRejectedValueOnce(new Error("no"));
    await useSessions.getState().setPinned("s1", true);
    vi.mocked(sessions.setPinned).mockRejectedValueOnce(new Error("no"));
    await useSessions.getState().setPinned("s1", false);
    vi.mocked(sessions.delete).mockRejectedValueOnce(new Error("no"));
    vi.mocked(sessions.list).mockResolvedValueOnce([row("s1")]);
    await useSessions.getState().remove("s1");
    expect(vi.mocked(toast.error).mock.calls.map(([text]) => text)).toEqual([
      "Could not unarchive the thread: no",
      "Could not pin the thread: no",
      "Could not unpin the thread: no",
      "Could not delete the thread: no",
    ]);
    expect(useSessions.getState().activeId).toBe("s1");
  });
});

describe("a delete rejected after the row went", () => {
  it("drops the active id and does not toast when the list no longer has the row", async () => {
    vi.mocked(window.textToCad.sessions.delete).mockRejectedValueOnce(new Error("cleanup failed"));
    vi.mocked(window.textToCad.sessions.list).mockResolvedValueOnce([]);
    await useSessions.getState().remove("s1");
    expect(toast.error).not.toHaveBeenCalled();
    expect(useSessions.getState().activeId).toBeNull();
  });

  it("toasts and keeps the id when the list still has the row", async () => {
    vi.mocked(window.textToCad.sessions.delete).mockRejectedValueOnce(new Error("locked"));
    vi.mocked(window.textToCad.sessions.list).mockResolvedValueOnce([row("s1")]);
    await useSessions.getState().remove("s1");
    expect(toast.error).toHaveBeenCalledWith("Could not delete the thread: locked");
    expect(useSessions.getState().activeId).toBe("s1");
  });
});

describe("an archive", () => {
  it("offers Undo, which unarchives the thread", async () => {
    vi.mocked(toast.success).mockClear();
    vi.mocked(window.textToCad.sessions.archive).mockClear();
    await useSessions.getState().archive("s1", true);
    const [text, options] = vi.mocked(toast.success).mock.calls[0]!;
    expect(text).toBe("Thread archived.");
    expect(options?.action).toMatchObject({ label: "Undo" });
    (options!.action as unknown as { onClick: () => void }).onClick();
    expect(window.textToCad.sessions.archive).toHaveBeenLastCalledWith({ id: "s1", archived: false });
  });

  it("offers none for an unarchive, and none when main refuses", async () => {
    vi.mocked(toast.success).mockClear();
    await useSessions.getState().archive("s1", false);
    vi.mocked(window.textToCad.sessions.archive).mockRejectedValueOnce(new Error("no"));
    await useSessions.getState().archive("s1", true);
    expect(toast.success).not.toHaveBeenCalled();
  });
});
