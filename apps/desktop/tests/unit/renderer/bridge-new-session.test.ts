import { toast } from "sonner";
import { afterEach, expect, it, vi } from "vitest";

import { runUiCommand } from "@renderer/state/bridge";
import { useProjects } from "@renderer/state/projects";
import { useSessions } from "@renderer/state/sessions";

vi.mock("sonner", () => ({ toast: Object.assign(vi.fn(), { error: vi.fn(), info: vi.fn() }) }));

afterEach(() => { vi.mocked(toast.error).mockClear(); });

it("says so when New session in this worktree cannot start", async () => {
  const start = vi.fn().mockRejectedValue(new Error("fatal: not a git repository"));
  useSessions.setState({ start } as never);
  vi.spyOn(console, "error").mockImplementation(() => {});
  useProjects.setState({ activeId: "p1" } as never);
  runUiCommand({ command: "new-session", projectId: "p1", cwd: "/bracket-wt" } as never);
  await vi.waitFor(() => expect(toast.error).toHaveBeenCalledTimes(1));
  expect(toast.error).toHaveBeenCalledWith("Could not start a session in this worktree: fatal: not a git repository");
});
