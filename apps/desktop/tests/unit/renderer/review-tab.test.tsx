import { act, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, it, vi, type Mock } from "vitest";

import { ReviewTab } from "@renderer/features/explorer/ReviewTab";
import { MAX_DIFF_HEIGHT, estimateHeight, sideText, singleSide } from "@renderer/features/explorer/review-diff";
import { useExplorer } from "@renderer/state/explorer";
import { useSessions } from "@renderer/state/sessions";
import type { FileDiff, GitStatus } from "@renderer/features/explorer/types";
import type { ProjectGitInfo } from "@shared/ipc/git";

let gitInfo: Partial<ProjectGitInfo> | null = null;
vi.mock("@renderer/lib/git-mode", () => ({ useProjectGitInfo: () => gitInfo }));
vi.mock("sonner", () => ({ toast: Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn() }) }));
import { toast } from "sonner";
// Monaco draws nothing readable in jsdom; the diff's `after` side stands in for it.
vi.mock("@renderer/features/explorer/review-diff", async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  ReviewDiff: ({ diff }: { diff: FileDiff }) => <pre data-testid="review-diff">{diff.after}</pre>,
}));

// Monaco's clipboard service (a WebKit workaround) builds a ClipboardItem on every click in the
// document; jsdom has none, and without this each click in these tests is an unhandled error.
// The next click cancels the previous item's promise, so the stub observes it.
if (!("ClipboardItem" in globalThis)) {
  Object.assign(globalThis, {
    ClipboardItem: class {
      constructor(items: Record<string, Promise<unknown>>) {
        for (const item of Object.values(items)) void Promise.resolve(item).catch(() => {});
      }
    },
  });
}

const PROJECT = { id: "p1", name: "bracket", path: "/bracket", createdAt: 0 };
const git = window.textToCad.git as unknown as {
  status: ReturnType<typeof vi.fn>; commit: ReturnType<typeof vi.fn>; fileDiff: ReturnType<typeof vi.fn>;
};
const original = { status: git.status, commit: git.commit, fileDiff: git.fileDiff };
// One read per refresh: the scope's answer carries the working tree's file count (what a commit takes).
let scoped: Mock<(request: unknown) => Promise<GitStatus>>;

const repo = (branch: string): GitStatus => ({
  isRepository: true, branch, unborn: false, ahead: 0, behind: 0, files: [], insertions: 0, deletions: 0, workingFiles: 0,
});
function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (error: Error) => void;
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}
const renderReview = () => render(<ReviewTab project={PROJECT} scope="session" sessionId="s1" tabId="t1" />);

const changed = (path: string) => ({ path, status: "modified" as const, insertions: 1, deletions: 0, binary: false });

beforeEach(() => {
  gitInfo = null;
  vi.mocked(toast.success).mockClear();
  scoped = vi.fn<(request: unknown) => Promise<GitStatus>>();
  git.status = scoped;
  git.commit = vi.fn();
});
afterEach(() => { git.status = original.status; git.commit = original.commit; git.fileDiff = original.fileDiff; });

it("a read that fails says so, with git's words and a retry — not that the folder is not a repository", async () => {
  const user = userEvent.setup();
  scoped.mockRejectedValueOnce(new Error("fatal: bad revision 'abc123'")).mockResolvedValueOnce(repo("main"));
  renderReview();

  expect(await screen.findByText("Could not read the changes")).toBeInTheDocument();
  expect(screen.getByText("fatal: bad revision 'abc123'")).toBeInTheDocument();
  expect(screen.queryByText("Not a repository")).toBeNull();

  await user.click(screen.getByRole("button", { name: "Try again" }));
  expect(await screen.findByText("main")).toBeInTheDocument();
  expect(screen.queryByText("Could not read the changes")).toBeNull();
});

it("an older read that answers after a newer one does not replace it", async () => {
  const slow = deferred<GitStatus>();
  const fast = deferred<GitStatus>();
  scoped.mockReturnValueOnce(slow.promise).mockReturnValueOnce(fast.promise);
  renderReview();

  // A batch of file changes asks again before the first read has answered.
  act(() => useExplorer.setState({ fsRevision: useExplorer.getState().fsRevision + 1 }));
  expect(scoped).toHaveBeenCalledTimes(2);
  await act(async () => fast.resolve(repo("newer")));
  await act(async () => slow.resolve(repo("older")));

  expect(screen.getByText("newer")).toBeInTheDocument();
  expect(screen.queryByText("older")).toBeNull();
});

it("a re-read that fails keeps the last answer on screen and marks it", async () => {
  scoped.mockResolvedValueOnce(repo("main")).mockRejectedValueOnce(new Error("index.lock exists"));
  renderReview();
  expect(await screen.findByText("main")).toBeInTheDocument();

  await act(async () => useExplorer.setState({ fsRevision: useExplorer.getState().fsRevision + 1 }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Could not refresh: index.lock exists");
  expect(screen.getByText("main")).toBeInTheDocument();
});

it("the commit button follows the working tree, not the scope, and says how many files it takes", async () => {
  const user = userEvent.setup();
  // Last turn touched nothing, but the working tree holds two uncommitted files.
  scoped.mockResolvedValue({ ...repo("main"), workingFiles: 2 });
  renderReview();

  const trigger = await screen.findByRole("button", { name: "Commit" });
  await vi.waitFor(() => expect(trigger).toBeEnabled());
  await user.click(trigger);
  expect(within(screen.getByRole("region", { name: "Commit changes" })).getByText("Commit 2 files")).toBeInTheDocument();
  expect(trigger).toHaveAttribute("aria-expanded", "true");
  expect(trigger).toHaveAttribute("aria-controls", screen.getByRole("region", { name: "Commit changes" }).id);
  // One filled Commit on screen: the panel's. The header's is the toggle that opened it.
  expect(trigger).toHaveAttribute("data-variant", "outline");
  expect(within(screen.getByRole("region", { name: "Commit changes" })).getByRole("button", { name: "Commit" })).toHaveAttribute("data-variant", "default");

  // Escape closes the panel and hands focus back to the header's button.
  await user.keyboard("{Escape}");
  expect(screen.queryByRole("region", { name: "Commit changes" })).toBeNull();
  expect(trigger).toHaveFocus();
  expect(trigger).toHaveAttribute("data-variant", "default");
});

it("a clean working tree disables the commit even when the scope shows committed history", async () => {
  scoped.mockResolvedValue({ ...repo("main"), files: [changed("a.step")], workingFiles: 0 });
  renderReview();
  expect(await screen.findByRole("button", { name: "Commit" })).toBeDisabled();
});

it("offers push only with a remote, and confirms a commit with its short hash", async () => {
  const user = userEvent.setup();
  scoped.mockResolvedValue({ ...repo("main"), workingFiles: 1 });
  git.commit.mockResolvedValue({ sha: "0123456789abcdef0123456789abcdef01234567" });
  const view = renderReview();

  // No remote: the trigger does not offer a push it cannot make.
  const trigger = await screen.findByRole("button", { name: "Commit" });
  await vi.waitFor(() => expect(trigger).toBeEnabled());
  await user.click(trigger);
  const panel = screen.getByRole("region", { name: "Commit changes" });
  expect(within(panel).getByText("Commit 1 file")).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Commit and push" })).toBeNull();

  await user.type(screen.getByLabelText("Commit message"), "one commit");
  await user.click(within(panel).getByRole("button", { name: "Commit" }));
  await vi.waitFor(() => expect(toast.success).toHaveBeenCalledWith("Committed 0123456"));
  expect(git.commit).toHaveBeenCalledWith(expect.objectContaining({ message: "one commit", push: false }));

  view.unmount();
  gitInfo = { hasRemote: true, hasGh: false };
  renderReview();
  const again = await screen.findByRole("button", { name: "Commit or push" });
  await vi.waitFor(() => expect(again).toBeEnabled());
  await user.click(again);
  expect(screen.getByRole("button", { name: "Commit and push" })).toBeInTheDocument();
});

it("a Last turn with no recorded mark says so, instead of showing the working tree under that name", async () => {
  scoped.mockResolvedValue({ ...repo("main"), unmarked: "turn", workingFiles: 1 });
  render(<ReviewTab project={PROJECT} scope="turn" sessionId="s1" tabId="t1" />);

  expect(await screen.findByText("No turn recorded yet")).toBeInTheDocument();
  // Written for the scope, not built around its label: no "Last turn starts…", no "All changes shows…".
  expect(screen.getByText("A turn is measured from the prompt that starts it, so there is nothing to show until the next one. The working tree's changes are under “All changes”.")).toBeInTheDocument();
  expect(screen.queryByText("No changes")).toBeNull();
  expect(screen.queryByText("a.step")).toBeNull();
});

it("a This session with no recorded mark says so too", async () => {
  scoped.mockResolvedValue({ ...repo("main"), unmarked: "session" });
  renderReview();
  expect(await screen.findByText("No session start recorded")).toBeInTheDocument();
  expect(screen.queryByText("No changes")).toBeNull();
});

it.each([
  ["turn", "the last turn"],
  ["session", "this session"],
] as const)("in a repository with no commits, %s shows the work and says, in a sentence of its own, it is measured from the start", async (scope, subject) => {
  scoped.mockResolvedValue({ ...repo("main"), unborn: true, fromStart: true, files: [changed("a.step")], insertions: 1, workingFiles: 1 });
  render(<ReviewTab project={PROJECT} scope={scope} sessionId="s1" tabId="t1" />);
  expect(await screen.findByText(`This repository has no commits yet, so ${subject} is measured from the repository's start.`)).toBeInTheDocument();
  expect(screen.getAllByText("a.step").length).toBeGreaterThan(0);
  expect(screen.queryByText("No turn recorded yet")).toBeNull();
});

it("a scoped review reads git once per refresh, not a second time for the commit button", async () => {
  scoped.mockResolvedValue({ ...repo("main"), workingFiles: 3 });
  renderReview();
  await vi.waitFor(() => expect(screen.getByRole("button", { name: "Commit" })).toBeEnabled());
  expect(scoped).toHaveBeenCalledTimes(1);

  await act(async () => useExplorer.setState({ fsRevision: useExplorer.getState().fsRevision + 1 }));
  expect(scoped).toHaveBeenCalledTimes(2);
  expect(scoped.mock.calls.every(([request]) => (request as { scope: { kind: string } }).scope.kind === "session")).toBe(true);
});

it("the header names the branch, not the session's title — the session header already does", async () => {
  useSessions.setState({ sessions: [{ id: "s1", title: "showcase: write a greeting script", cwd: "/bracket" } as never] });
  scoped.mockResolvedValue(repo("main"));
  renderReview();
  expect(await screen.findByText("main")).toBeInTheDocument();
  expect(screen.queryByText("showcase: write a greeting script")).toBeNull();
  useSessions.setState({ sessions: [] });
});

it("Request revision sits in the file's header row, beside its counts", async () => {
  scoped.mockResolvedValue({ ...repo("main"), files: [{ ...changed("hello.py"), binary: true }], workingFiles: 1 });
  renderReview();
  const revise = await screen.findByRole("button", { name: "Request revision for hello.py" });
  const toggle = within(revise.parentElement!).getByRole("button", { name: /hello\.py/, expanded: false });
  expect(toggle).toHaveTextContent("+1");
});

const fileDiff = (over: Partial<FileDiff>): FileDiff => ({
  path: "hello.py", status: "modified", insertions: 0, deletions: 0, binary: false, before: "", after: "", ...over,
});

it("an added file is its one side, not a diff against a phantom empty line", () => {
  const added = fileDiff({ status: "added", insertions: 6, before: "", after: "def main():\n    pass\n" });
  expect(singleSide(added)).toBe("added");
  expect(singleSide(fileDiff({ status: "untracked", before: "", after: "x" }))).toBe("added");
  expect(singleSide(fileDiff({ status: "deleted", before: "x\n", after: "" }))).toBe("deleted");
  expect(singleSide(fileDiff({ status: "modified", before: "a\n", after: "b\n" }))).toBeNull();
  // git's final newline is not a line of its own.
  expect(sideText("a\nb\n")).toBe("a\nb");
});

it("a diff block is sized to its content, and capped", () => {
  const seven = fileDiff({ status: "added", insertions: 7, after: "1\n2\n3\n4\n5\n6\n7\n" });
  expect(estimateHeight(seven)).toBe(7 * 20 + 12);
  const long = fileDiff({ status: "added", insertions: 400, after: "x\n".repeat(400) });
  expect(estimateHeight(long)).toBe(MAX_DIFF_HEIGHT);
  // A four-line edit in a long file is the edit plus its context, not the file.
  const edit = fileDiff({ insertions: 2, deletions: 2, before: "x\n".repeat(400), after: "y\n".repeat(400) });
  expect(estimateHeight(edit)).toBe(12 * 20 + 12);
});

it("two Review tabs open their commit panels under ids of their own", async () => {
  const user = userEvent.setup();
  scoped.mockResolvedValue({ ...repo("main"), workingFiles: 1 });
  renderReview();
  render(<ReviewTab project={PROJECT} scope="all" sessionId="s1" tabId="t2" />);
  await vi.waitFor(() => expect(screen.getAllByRole("button", { name: "Commit" })).toHaveLength(2));
  const triggers = screen.getAllByRole("button", { name: "Commit" });
  for (const trigger of triggers) {
    await vi.waitFor(() => expect(trigger).toBeEnabled());
    await user.click(trigger);
  }
  const panels = screen.getAllByRole("region", { name: "Commit changes" });
  expect(panels).toHaveLength(2);
  expect(panels[0]!.id).not.toBe(panels[1]!.id);
  expect(triggers.map((trigger) => trigger.getAttribute("aria-controls")).sort()).toEqual(panels.map((panel) => panel.id).sort());
});

it("an open diff is read again when a newer status lands, not kept from the first read", async () => {
  scoped.mockResolvedValue({ ...repo("main"), files: [changed("hello.py")], workingFiles: 1 });
  const read = vi.fn()
    .mockResolvedValueOnce(fileDiff({ before: "v0\n", after: "v1\n" }))
    .mockResolvedValueOnce(fileDiff({ before: "v0\n", after: "v2\n" }));
  git.fileDiff = read;
  renderReview();
  expect(await screen.findByTestId("review-diff")).toHaveTextContent("v1");

  // The agent writes the file again: the header's counts are re-read, and so
  // is the open diff — the counts are the same, the watcher saw the write.
  await act(async () => useExplorer.setState({
    fsRevision: useExplorer.getState().fsRevision + 1,
    changedEntries: [{ kind: "changed", path: "hello.py", directory: false }],
  }));
  await vi.waitFor(() => expect(read).toHaveBeenCalledTimes(2));
  expect(await screen.findByText("v2")).toBeInTheDocument();
});

it("a diff that could not be read says so, with a Retry that reads it again", async () => {
  const user = userEvent.setup();
  scoped.mockResolvedValue({ ...repo("main"), files: [changed("hello.py")], workingFiles: 1 });
  const read = vi.fn()
    .mockRejectedValueOnce(new Error("git diff timed out"))
    .mockResolvedValueOnce(fileDiff({ before: "v0\n", after: "v1\n" }));
  git.fileDiff = read;
  renderReview();

  expect(await screen.findByText(/git diff timed out/)).toBeInTheDocument();
  const failed = screen.getByRole("alert");
  expect(screen.queryByText("Reading the diff…")).toBeNull();
  await user.click(within(failed).getByRole("button", { name: "Retry" }));
  expect(await screen.findByTestId("review-diff")).toHaveTextContent("v1");
  expect(screen.queryByText(/git diff timed out/)).toBeNull();
  expect(read).toHaveBeenCalledTimes(2);
});

it("a read that fails after the file's stamp moved asks again on its own, without Retry", async () => {
  scoped.mockResolvedValue({ ...repo("main"), files: [changed("hello.py")], workingFiles: 1 });
  vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout", "Date"] });
  try {
    const first = deferred<FileDiff>();
    const read = vi.fn()
      .mockReturnValueOnce(first.promise)
      .mockResolvedValueOnce(fileDiff({ before: "v0\n", after: "v2\n" }));
    git.fileDiff = read;
    renderReview();
    await act(async () => {});
    expect(read).toHaveBeenCalledTimes(1);

    // The agent writes the file while its first read is out: the stamp moves, and the read in
    // flight keeps the newer stamp from asking.
    await act(async () => {
      vi.advanceTimersByTime(500);
      useExplorer.setState({
        fsRevision: useExplorer.getState().fsRevision + 1,
        changedEntries: [{ kind: "changed", path: "hello.py", directory: false }],
      });
    });
    await act(async () => { vi.advanceTimersByTime(500); });
    expect(scoped).toHaveBeenCalledTimes(2);
    expect(read).toHaveBeenCalledTimes(1);

    // The first read fails; nothing presses Retry, and no status answer follows.
    await act(async () => { first.reject(new Error("git diff timed out")); });
    await act(async () => {});
    expect(read).toHaveBeenCalledTimes(2);
    expect(screen.getByTestId("review-diff")).toHaveTextContent("v2");
    expect(screen.queryByText(/git diff timed out/)).toBeNull();
    expect(scoped).toHaveBeenCalledTimes(2);
  } finally {
    vi.useRealTimers();
  }
});

it("a newer status re-reads only the open diffs it says something new about", async () => {
  scoped
    .mockResolvedValueOnce({ ...repo("main"), files: [changed("a.py"), changed("b.py")], workingFiles: 2 })
    .mockResolvedValueOnce({ ...repo("main"), files: [changed("a.py"), { ...changed("b.py"), insertions: 4 }], workingFiles: 2 });
  const read = vi.fn(async (request: { path: string }) => fileDiff({ path: request.path, before: "", after: request.path }));
  git.fileDiff = read;
  renderReview();
  await vi.waitFor(() => expect(screen.getAllByTestId("review-diff")).toHaveLength(2));
  expect(read).toHaveBeenCalledTimes(2);
  read.mockClear();

  // A batch of writes elsewhere in the tree; git's answer changed b.py's counts only.
  await act(async () => useExplorer.setState({
    fsRevision: useExplorer.getState().fsRevision + 1,
    changedEntries: [{ kind: "changed", path: "notes/unrelated.md", directory: false }],
  }));
  await vi.waitFor(() => expect(scoped).toHaveBeenCalledTimes(2));
  await vi.waitFor(() => expect(read).toHaveBeenCalledTimes(1));
  await act(async () => {});
  expect(read).toHaveBeenCalledTimes(1);
  expect(read.mock.calls[0]![0]).toMatchObject({ path: "b.py" });
});

it("batches of writes streaming in ask git at most once per gap, and the last batch is always answered", async () => {
  scoped.mockResolvedValue({ ...repo("main"), workingFiles: 0 });
  renderReview();
  expect(await screen.findByText("main")).toBeInTheDocument();
  expect(scoped).toHaveBeenCalledTimes(1);
  vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout", "Date"] });
  try {
    const batch = () => act(() => useExplorer.setState({ fsRevision: useExplorer.getState().fsRevision + 1 }));
    batch();
    expect(scoped).toHaveBeenCalledTimes(2);
    for (let index = 0; index < 5; index += 1) {
      vi.advanceTimersByTime(80);
      batch();
    }
    expect(scoped).toHaveBeenCalledTimes(2);
    act(() => { vi.advanceTimersByTime(500); });
    expect(scoped).toHaveBeenCalledTimes(3);
    act(() => { vi.advanceTimersByTime(5_000); });
    expect(scoped).toHaveBeenCalledTimes(3);
  } finally {
    vi.useRealTimers();
  }
});

it("a file written faster than its diff can be read still shows a diff, and a newer one once it lands", async () => {
  scoped.mockResolvedValue({ ...repo("main"), files: [changed("hello.py")], workingFiles: 1 });
  vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout", "Date"] });
  try {
    // Each read of the diff takes 600 ms; the agent rewrites the file every 500 ms, so the status
    // answer — and the file's stamp — moves before any read has come back.
    let reads = 0;
    git.fileDiff = vi.fn(() => {
      const after = `v${++reads}\n`;
      return new Promise((resolve) => window.setTimeout(() => resolve(fileDiff({ before: "v0\n", after })), 600));
    });
    renderReview();
    await act(async () => {});
    for (let batch = 0; batch < 6 && !screen.queryByTestId("review-diff"); batch += 1) {
      await act(async () => {
        vi.advanceTimersByTime(500);
        useExplorer.setState({
          fsRevision: useExplorer.getState().fsRevision + 1,
          changedEntries: [{ kind: "changed", path: "hello.py", directory: false }],
        });
      });
    }
    expect(screen.getByTestId("review-diff")).toHaveTextContent("v1");
    expect(screen.queryByText("Reading the diff…")).toBeNull();
    // The writes stop: the last stamp's read lands and replaces the first.
    await act(async () => { vi.advanceTimersByTime(5_000); });
    await act(async () => { vi.advanceTimersByTime(5_000); });
    expect(screen.getByTestId("review-diff")).toHaveTextContent(`v${reads}`);
  } finally {
    vi.useRealTimers();
  }
});

it("a write the watcher reports under a project inside the repository re-reads that file's open diff", async () => {
  // The repository is /r and the project /r/app: git names the file `app/a.ts`, the watcher —
  // relative to the project — `a.ts`. The agent rewrites it with the same counts.
  scoped.mockResolvedValue({ ...repo("main"), files: [changed("app/a.ts")], workingFiles: 1, prefix: "app/" });
  const read = vi.fn()
    .mockResolvedValueOnce(fileDiff({ path: "app/a.ts", before: "v0\n", after: "v1\n" }))
    .mockResolvedValueOnce(fileDiff({ path: "app/a.ts", before: "v0\n", after: "v2\n" }));
  git.fileDiff = read;
  renderReview();
  expect(await screen.findByTestId("review-diff")).toHaveTextContent("v1");

  await act(async () => useExplorer.setState({
    fsRevision: useExplorer.getState().fsRevision + 1,
    changedEntries: [{ kind: "changed", path: "a.ts", directory: false }],
  }));
  await vi.waitFor(() => expect(read).toHaveBeenCalledTimes(2));
  expect(await screen.findByText("v2")).toBeInTheDocument();
});

it("a clean tree with commits the remote lacks offers Push, which sends them without a message", async () => {
  const user = userEvent.setup();
  gitInfo = { hasRemote: true, hasGh: false };
  git.commit.mockResolvedValue({ sha: "0123456789abcdef0123456789abcdef01234567" });
  scoped.mockResolvedValue({ ...repo("main"), ahead: 1, workingFiles: 0 });
  renderReview();

  const trigger = await screen.findByRole("button", { name: "Push" });
  await vi.waitFor(() => expect(trigger).toBeEnabled());
  await user.click(trigger);
  const panel = screen.getByRole("region", { name: "Commit changes" });
  expect(within(panel).getByText("1 commit not pushed")).toBeInTheDocument();
  await user.click(within(panel).getByRole("button", { name: "Push" }));
  await vi.waitFor(() => expect(toast.success).toHaveBeenCalledWith("Pushed 0123456"));
  expect(git.commit).toHaveBeenCalledWith(expect.objectContaining({ message: "", push: true }));
});

it("a commit whose files were committed elsewhere in the meantime says it only pushed", async () => {
  const user = userEvent.setup();
  gitInfo = { hasRemote: true, hasGh: false };
  git.commit.mockResolvedValue({ sha: "0123456789abcdef0123456789abcdef01234567", pushedOnly: true, pushed: 2 });
  scoped.mockResolvedValue({ ...repo("main"), ahead: 0, workingFiles: 1 });
  renderReview();

  const trigger = await screen.findByRole("button", { name: "Commit or push" });
  await vi.waitFor(() => expect(trigger).toBeEnabled());
  await user.click(trigger);
  const panel = screen.getByRole("region", { name: "Commit changes" });
  await user.type(within(panel).getByRole("textbox", { name: "Commit message" }), "add wrist");
  await user.click(within(panel).getByRole("button", { name: "Commit and push" }));
  await vi.waitFor(() => expect(toast.success).toHaveBeenCalledWith("Nothing new to commit; pushed 2 commits"));
});

it("offers no Push for commits ahead of an upstream when there is no remote to push to", async () => {
  gitInfo = { hasRemote: false, hasGh: false };
  scoped.mockResolvedValue({ ...repo("main"), ahead: 1, workingFiles: 0 });
  renderReview();

  const trigger = await screen.findByRole("button", { name: "Commit" });
  expect(trigger).toBeDisabled();
  expect(screen.queryByRole("button", { name: "Push" })).not.toBeInTheDocument();
});

it("Refresh says it is busy while the read is out, not only by spinning", async () => {
  const user = userEvent.setup();
  const again = deferred<GitStatus>();
  scoped.mockResolvedValueOnce(repo("main")).mockReturnValueOnce(again.promise);
  renderReview();
  await screen.findByText("main");
  const refresh = screen.getByRole("button", { name: "Refresh" });
  expect(refresh).toHaveAttribute("aria-busy", "false");

  await user.click(refresh);
  expect(refresh).toHaveAttribute("aria-busy", "true");
  expect(screen.getByRole("status")).toHaveTextContent("Refreshing…");

  await act(async () => again.resolve(repo("main")));
  expect(refresh).toHaveAttribute("aria-busy", "false");
});
