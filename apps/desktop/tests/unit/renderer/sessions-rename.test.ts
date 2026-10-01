/**
 * A rename shows at once and is undone when main refuses it.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useSessions } from "@renderer/state/sessions";
import type { Session } from "@shared/types";
import { toast } from "sonner";

vi.mock("sonner", () => ({ toast: { error: vi.fn() } }));

const row = (id: string, title: string) => ({ id, projectId: "p1", title }) as Session;

beforeEach(() => {
  vi.mocked(toast.error).mockClear();
  useSessions.setState({ sessions: [row("s1", "Bracket"), row("s2", "Other")], ready: true, activeId: null });
});

describe("rename", () => {
  it("puts the old title back and says why when main refuses", async () => {
    vi.mocked(window.textToCad.sessions.rename).mockRejectedValueOnce(new Error("disk full"));
    await useSessions.getState().rename("s1", "Renamed");
    expect(useSessions.getState().sessions.map((session) => session.title)).toEqual(["Bracket", "Other"]);
    expect(toast.error).toHaveBeenCalledWith(expect.stringContaining("disk full"));
  });

  it("shows the new title before main has answered", async () => {
    let answer!: () => void;
    vi.mocked(window.textToCad.sessions.rename).mockReturnValueOnce(new Promise<undefined>((resolve) => (answer = () => resolve(undefined))) as never);
    const pending = useSessions.getState().rename("s1", "Renamed");
    expect(useSessions.getState().sessions[0]?.title).toBe("Renamed");
    answer();
    await pending;
    expect(useSessions.getState().sessions[0]?.title).toBe("Renamed");
  });

  it("leaves a title main has written since alone", async () => {
    vi.mocked(window.textToCad.sessions.rename).mockImplementationOnce(async () => {
      useSessions.setState({ sessions: [row("s1", "From main"), row("s2", "Other")] });
      throw new Error("late");
    });
    await useSessions.getState().rename("s1", "Renamed");
    expect(useSessions.getState().sessions[0]?.title).toBe("From main");
  });
});
