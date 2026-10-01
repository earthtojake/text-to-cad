/**
 * The Git page's per-project worktree card: which worktrees offer Delete, and
 * what a row says about why one does not.
 */
import { beforeEach, expect, it, vi } from "vitest";
import { toast } from "sonner";
import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { TooltipProvider } from "@text-to-cad/ui/primitives/tooltip";
import { SettingsRoute } from "@renderer/features/settings/SettingsRoute";
import { GitPage } from "@renderer/features/settings/pages/GitPage";
import {
  ensureWorktrees,
  noteSessions,
  resetForTests,
  seedSessions,
  useWorktreeCache,
} from "@renderer/features/settings/worktree-cache";
import { useUi } from "@renderer/state/ui";
import { useProjects } from "@renderer/state/projects";
import { useSettings } from "@renderer/state/settings";
import { defaultSettings } from "@shared/types";
import type { Session } from "@shared/types";
import type { Worktree } from "@shared/ipc/git";

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn(), dismiss: vi.fn(), info: vi.fn() } }));

const worktree = (over: Partial<Worktree>): Worktree => ({
  path: "/w/p/fillet",
  branch: "text-to-cad/fillet",
  lastUsedAt: null,
  openSessions: 0,
  dirty: false,
  stranded: false,
  locked: false,
  ...over,
});

beforeEach(() => {
  vi.clearAllMocks();
  resetForTests();
  useSettings.setState({ settings: defaultSettings(), ready: true });
  useProjects.setState({ projects: [{ id: "p", name: "p", path: "/p", createdAt: 0 }], activeId: "p" });
});

it("does not offer Delete on a locked worktree, and names the lock", async () => {
  vi.mocked(window.textToCad.git.worktrees).mockResolvedValue([worktree({ locked: true })]);
  render(
    <TooltipProvider>
      <GitPage />
    </TooltipProvider>,
  );
  const remove = await screen.findByRole("button", { name: "Delete" });
  expect(remove).toBeDisabled();
  expect(remove).toHaveAccessibleDescription(/locked/);
});

it("says on the row why a worktree is kept: in use, locked", async () => {
  vi.mocked(window.textToCad.git.worktrees).mockResolvedValue([
    worktree({ path: "/w/p/busy", branch: "busy", openSessions: 1 }),
    worktree({ path: "/w/p/held", branch: "held", locked: true }),
  ]);
  render(
    <TooltipProvider>
      <GitPage />
    </TooltipProvider>,
  );
  expect(await screen.findByText(/busy · 1 open session \(in use\)/)).toBeInTheDocument();
  expect(screen.getByText(/held · locked/)).toBeInTheDocument();
});

it("words a worktree root that is now a file as a file, and drops \"created again\" for it", async () => {
  useSettings.setState({ settings: { ...defaultSettings(), worktreeRoot: "/a-file" }, ready: true });
  vi.mocked(window.textToCad.git.worktrees).mockResolvedValue([]);
  vi.mocked(window.textToCad.settings.fallbacks).mockResolvedValue({ refused: {}, gone: { worktreeRoot: { path: "/a-file", reason: "file" } } });
  render(
    <TooltipProvider>
      <GitPage />
    </TooltipProvider>,
  );
  expect(await screen.findByText(/is a file, not a folder, so worktrees cannot be made here/)).toBeInTheDocument();
  expect(screen.queryByText(/created again/)).not.toBeInTheDocument();
});

it("keeps \"created again with the next worktree\" for a worktree root that is missing", async () => {
  useSettings.setState({ settings: { ...defaultSettings(), worktreeRoot: "/gone" }, ready: true });
  vi.mocked(window.textToCad.git.worktrees).mockResolvedValue([]);
  vi.mocked(window.textToCad.settings.fallbacks).mockResolvedValue({ refused: {}, gone: { worktreeRoot: { path: "/gone", reason: "missing" } } });
  render(
    <TooltipProvider>
      <GitPage />
    </TooltipProvider>,
  );
  expect(await screen.findByText(/no longer exists; it is created again with the next worktree/)).toBeInTheDocument();
});

it("reads afresh each time the search mounts the Git page, and keeps the list on the page meanwhile", async () => {
  const user = userEvent.setup();
  vi.mocked(window.textToCad.git.worktrees).mockClear();
  vi.mocked(window.textToCad.git.worktrees).mockResolvedValue([worktree({})]);
  useUi.setState({ route: "settings", settingsSection: "general", commandPaletteOpen: false });
  render(
    <TooltipProvider>
      <SettingsRoute />
    </TooltipProvider>,
  );
  const search = screen.getByPlaceholderText("Search settings");
  await user.type(search, "a");
  expect(await screen.findAllByText("text-to-cad/fillet")).not.toHaveLength(0);
  await user.clear(search);
  await user.type(search, "a");
  // The list from the first mount is on the page at once, not after the new read.
  expect(screen.getAllByText("text-to-cad/fillet")).not.toHaveLength(0);
  // A file removed on disk makes a worktree clean: a mount reads again, over the old list.
  await waitFor(() => expect(window.textToCad.git.worktrees).toHaveBeenCalledTimes(2));
});

const deferred = <T,>() => {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => {
    resolve = done;
  });
  return { promise, resolve };
};

it("reads again after an invalidation discards a read in flight, instead of handing back the discarded one", async () => {
  const first = deferred<Worktree[]>();
  const second = deferred<Worktree[]>();
  vi.mocked(window.textToCad.git.worktrees).mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise);
  const a = ensureWorktrees("p");
  useWorktreeCache.getState().invalidate();
  const b = ensureWorktrees("p");
  first.resolve([]);
  second.resolve([]);
  await Promise.all([a, b]);
  expect(useWorktreeCache.getState().lists.p).toEqual([]);
});

it("keeps the previous list on the page while a re-read is under way", async () => {
  const again = deferred<Worktree[]>();
  vi.mocked(window.textToCad.git.worktrees)
    .mockResolvedValueOnce([worktree({})])
    .mockReturnValueOnce(again.promise);
  render(
    <TooltipProvider>
      <GitPage />
    </TooltipProvider>,
  );
  expect(await screen.findByText("text-to-cad/fillet")).toBeInTheDocument();
  act(() => useWorktreeCache.getState().invalidate());
  expect(window.textToCad.git.worktrees).toHaveBeenCalledTimes(2);
  expect(screen.getByText("text-to-cad/fillet")).toBeInTheDocument();
  await act(async () => again.resolve([worktree({ branch: "text-to-cad/other" })]));
  expect(await screen.findByText("text-to-cad/other")).toBeInTheDocument();
  expect(screen.queryByText("text-to-cad/fillet")).not.toBeInTheDocument();
});

it("invalidates on a session that appeared, moved or was archived, and not on status churn", () => {
  const session = (over: Partial<Session>) =>
    ({ id: "s1", cwd: "/w/p/fillet", archived: false, status: "idle", title: "t", insertions: 0, ...over }) as Session;
  seedSessions([session({})]);
  const epoch = () => useWorktreeCache.getState().epoch;
  noteSessions([session({ status: "running", title: "renamed", insertions: 9 })]);
  expect(epoch()).toBe(0);
  noteSessions([session({ archived: true })]);
  expect(epoch()).toBe(1);
  noteSessions([session({ archived: true }), session({ id: "s2" })]);
  expect(epoch()).toBe(2);
  noteSessions([session({ archived: true }), session({ id: "s2", cwd: "/w/p/other" })]);
  expect(epoch()).toBe(3);
});

it("says so when a project's worktrees cannot be read, and drops it when a read lands", async () => {
  vi.mocked(window.textToCad.git.worktrees).mockRejectedValueOnce(new Error("git exploded"));
  render(
    <TooltipProvider>
      <GitPage />
    </TooltipProvider>,
  );
  expect(await screen.findByText(/Could not read the worktrees: git exploded/)).toBeInTheDocument();
  vi.mocked(window.textToCad.git.worktrees).mockResolvedValue([worktree({})]);
  act(() => useWorktreeCache.getState().invalidate());
  await screen.findByRole("button", { name: "Delete" });
  expect(screen.queryByText(/Could not read the worktrees/)).toBeNull();
});

it("drops a failed Delete's message once the next read lands", async () => {
  vi.mocked(window.textToCad.git.worktrees).mockResolvedValue([worktree({})]);
  vi.mocked(window.textToCad.git.removeWorktree).mockRejectedValueOnce(new Error("busy dir"));
  render(
    <TooltipProvider>
      <GitPage />
    </TooltipProvider>,
  );
  await userEvent.setup().click(await screen.findByRole("button", { name: "Delete" }));
  expect(await screen.findByText("busy dir")).toBeInTheDocument();
  vi.mocked(window.textToCad.git.worktrees).mockResolvedValue([worktree({ branch: "other" })]);
  act(() => useWorktreeCache.getState().invalidate());
  await waitFor(() => expect(screen.queryByText("busy dir")).toBeNull());
});

it("toasts when the folder chooser itself fails", async () => {
  vi.mocked(window.textToCad.git.worktrees).mockResolvedValue([]);
  vi.mocked(window.textToCad.dialogs.chooseDirectory).mockRejectedValueOnce(new Error("no dialog"));
  render(
    <TooltipProvider>
      <GitPage />
    </TooltipProvider>,
  );
  await userEvent.setup().click(screen.getAllByRole("button", { name: /Choose/ })[0]!);
  await waitFor(() => expect(toast.error).toHaveBeenCalledWith("Could not open the folder chooser: no dialog"));
});

it("describes a worktree holding only stranded commits as that, not as uncommitted files", async () => {
  vi.mocked(window.textToCad.git.worktrees).mockResolvedValue([
    worktree({ path: "/w/p/detached", branch: null, stranded: true }),
    worktree({ path: "/w/p/edited", branch: "edited", dirty: true }),
  ]);
  render(
    <TooltipProvider>
      <GitPage />
    </TooltipProvider>,
  );
  expect(await screen.findByText(/detached · .*commits on a detached HEAD, or an unfinished merge or rebase/)).toBeInTheDocument();
  expect(screen.queryByText(/detached · .*uncommitted or ignored files/)).toBeNull();
  expect(screen.getByText(/edited · .*uncommitted or ignored files/)).toBeInTheDocument();
  const [stranded] = screen.getAllByRole("button", { name: "Delete" });
  expect(stranded).toBeDisabled();
  expect(stranded).toHaveAccessibleDescription(/holds commits on a detached HEAD no branch reaches/);
});
