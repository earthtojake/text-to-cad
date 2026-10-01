import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";

import type { Project } from "@shared/types";

/**
 * xterm draws to a canvas jsdom does not have; the tab's lifecycle is what is
 * under test. `write` answers a cursor position query the way xterm does —
 * synchronously, through `onData`, while it parses — so the tab's handling of
 * those answers can be seen.
 */
const terminals = vi.hoisted(() => [] as Array<{
  options: { fontFamily?: string };
  focused: number;
  keys: (event: KeyboardEvent) => boolean;
}>);
vi.mock("@xterm/xterm", () => ({
  Terminal: class {
    cols = 80;
    rows = 24;
    focused = 0;
    keys: (event: KeyboardEvent) => boolean = () => true;
    private listener: (data: string) => void = () => {};
    constructor(public options: { fontFamily?: string }) {
      terminals.push(this);
    }
    onSelectionChange() {}
    loadAddon() {}
    open() {}
    write(data: string, done?: () => void) {
      if (data.includes("\x1b[6n")) this.listener("\x1b[1;1R");
      done?.();
    }
    onData(listener: (data: string) => void) {
      this.listener = listener;
    }
    attachCustomKeyEventHandler(handler: (event: KeyboardEvent) => boolean) {
      this.keys = handler;
    }
    focus() {
      this.focused += 1;
    }
    clear() {}
    getSelection() { return ""; }
    dispose() {}
  },
}));
vi.mock("@xterm/addon-fit", () => ({ FitAddon: class { fit() {} } }));
vi.mock("@xterm/addon-web-links", () => ({ WebLinksAddon: class {} }));
vi.mock("@xterm/xterm/css/xterm.css", () => ({}));

import { focusTabBody } from "@renderer/features/explorer/focus";
import { TerminalTab } from "@renderer/features/explorer/TerminalTab";
import { useExplorer } from "@renderer/state/explorer";

const project: Project = { id: "terminal-project", name: "Project", path: "/tmp/terminal-project", createdAt: 0 };
const terminal = () => window.textToCad.terminal as unknown as Record<string, ReturnType<typeof vi.fn>>;
const info = (exitCode: number | null) => ({ id: "pty-old", cwd: project.path, shell: "/bin/zsh", cols: 80, rows: 24, exitCode });

let update: ReturnType<typeof vi.fn>;
beforeEach(() => {
  terminals.length = 0;
  document.documentElement.style.removeProperty("--font-mono");
  update = vi.fn();
  useExplorer.setState({ update } as never);
  terminal().kill = vi.fn(async () => {});
  terminal().resize = vi.fn(async () => {});
});

function renderTab(ptyId: string | null = "pty-old", agent = false, tabId = "tab") {
  return render(<TerminalTab tabId={tabId} sessionId="session" project={project} ptyId={ptyId} cwd={project.path} readOnly={false} agent={agent} />);
}

it("kills the exited pty before restarting, so its scrollback is not kept for a tab that moved on", async () => {
  terminal().attach = vi.fn(async () => ({ info: info(0), scrollback: "done\n", seq: 1 }));
  renderTab();
  fireEvent.click(await screen.findByRole("button", { name: "restart" }));
  expect(terminal().kill).toHaveBeenCalledWith({ id: "pty-old", sessionId: "session" });
  expect(update).toHaveBeenCalledWith("tab", { ptyId: null });
});

it("respawns an agent-opened tab as the agent's, and a person's without that", async () => {
  const create = vi.fn(async (_input: { agent?: boolean }) => info(null));
  terminal().create = create;
  terminal().attach = vi.fn(async () => null);
  renderTab(null, true).unmount();
  expect(create).toHaveBeenCalledWith(expect.objectContaining({ agent: true }));
  create.mockClear();
  renderTab(null, false, "other-tab");
  await waitFor(() => expect(create).toHaveBeenCalled());
  expect(create.mock.calls[0]![0]).not.toHaveProperty("agent");
});

it("marks its host as a terminal body, which the strip's chords read to leave Ctrl+W to the shell", async () => {
  terminal().attach = vi.fn(async () => ({ info: info(null), scrollback: "", seq: 0 }));
  const { container } = renderTab();
  await waitFor(() => expect(terminals).toHaveLength(1));
  expect(container.querySelector("[data-terminal-body]")).not.toBeNull();
});

it("spawns one shell for a tab whose body unmounts and mounts again while create is in flight", () => {
  let spawned: (value: ReturnType<typeof info>) => void = () => {};
  const create = vi.fn(() => new Promise<ReturnType<typeof info>>((resolve) => { spawned = resolve; }));
  terminal().create = create;
  terminal().attach = vi.fn(async () => null);
  renderTab(null, false, "raced-tab").unmount();
  renderTab(null, false, "raced-tab");
  expect(create).toHaveBeenCalledTimes(1);
  spawned(info(null));
});

it("labels a terminal the agent opened, and only that one", async () => {
  terminal().attach = vi.fn(async () => ({ info: info(null), scrollback: "", seq: 0 }));
  const { unmount } = renderTab("pty-old", true);
  expect(await screen.findByText("agent")).toBeInTheDocument();
  unmount();
  renderTab("pty-old", false);
  await waitFor(() => expect(terminals).toHaveLength(2));
  expect(screen.queryByText("agent")).toBeNull();
});

it("releases the old pty id on Try again too", async () => {
  terminal().attach = vi.fn(async () => null);
  renderTab();
  fireEvent.click(await screen.findByRole("button", { name: "Try again" }));
  expect(terminal().kill).toHaveBeenCalledWith({ id: "pty-old", sessionId: "session" });
  expect(update).toHaveBeenCalledWith("tab", { ptyId: null });
});

it("does not send the answer to a query replayed from scrollback, and still answers a live one", async () => {
  terminal().attach = vi.fn(async () => ({ info: info(null), scrollback: "$ \x1b[6n", seq: 1 }));
  terminal().write = vi.fn(async () => {});
  let live: (event: { id: string; data: string; seq: number }) => void = () => {};
  const on = window.textToCad.on as unknown as ReturnType<typeof vi.fn>;
  on.mockImplementation((channel: string, listener: typeof live) => {
    if (channel === "terminal.data") live = listener;
    return () => {};
  });
  renderTab();
  await waitFor(() => expect(terminal().attach).toHaveBeenCalled());
  await Promise.resolve();
  expect(terminal().write).not.toHaveBeenCalled();

  live({ id: "pty-old", data: "\x1b[6n", seq: 2 });
  expect(terminal().write).toHaveBeenCalledWith({ id: "pty-old", sessionId: "session", data: "\x1b[1;1R" });
});

it("draws in the Code font from Settings, and follows it when it changes", async () => {
  terminal().attach = vi.fn(async () => ({ info: info(null), scrollback: "", seq: 0 }));
  document.documentElement.style.setProperty("--font-mono", '"JetBrains Mono", monospace');
  renderTab();
  expect(terminals[0]!.options.fontFamily).toBe('"JetBrains Mono", monospace');
  document.documentElement.style.setProperty("--font-mono", "Menlo, monospace");
  await waitFor(() => expect(terminals[0]!.options.fontFamily).toBe("Menlo, monospace"));
});

it("takes focus when the person opened or picked the tab, not on every mount (a session switch, Back)", async () => {
  terminal().attach = vi.fn(async () => ({ info: info(null), scrollback: "", seq: 0 }));
  const first = renderTab();
  expect(terminals[0]!.focused).toBe(0);
  first.unmount();

  // Asked for, as the shortcuts, the `+` menu and a click on the tab do.
  focusTabBody("tab");
  const second = renderTab();
  expect(terminals[1]!.focused).toBe(1);
  second.unmount();
  // Claimed once: the next remount of the same tab is not the person asking again.
  renderTab();
  expect(terminals[2]!.focused).toBe(0);
});

it("lets Tab leave the terminal after Ctrl+Shift+M, and says so", async () => {
  terminal().attach = vi.fn(async () => ({ info: info(null), scrollback: "", seq: 0 }));
  renderTab();
  const key = (init: KeyboardEventInit) => terminals[0]!.keys(new KeyboardEvent("keydown", init));
  // Off: Tab is the shell's (completion).
  expect(key({ key: "Tab" })).toBe(true);
  expect(key({ key: "M", ctrlKey: true, shiftKey: true })).toBe(false);
  expect(await screen.findByRole("status")).toHaveTextContent("Tab moves focus");
  // On: xterm leaves Tab and Shift+Tab alone, so the browser moves focus.
  expect(key({ key: "Tab" })).toBe(false);
  expect(key({ key: "Tab", shiftKey: true })).toBe(false);
  key({ key: "M", ctrlKey: true, shiftKey: true });
  expect(key({ key: "Tab" })).toBe(true);
  await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent(""));
});

it("leaves paste to xterm: Cmd+V is passed over and the clipboard is not also written to the shell", async () => {
  terminal().attach = vi.fn(async () => ({ info: info(null), scrollback: "", seq: 0 }));
  terminal().write = vi.fn(async () => {});
  const readText = vi.fn(async () => "echo A\n");
  Object.defineProperty(navigator, "clipboard", { value: { readText, writeText: vi.fn(async () => {}) }, configurable: true });
  renderTab();
  await waitFor(() => expect(terminal().attach).toHaveBeenCalled());
  await Promise.resolve();
  // xterm's own paste listener sees the native event and brackets it; a second,
  // manual write here would run the command twice.
  expect(terminals[0]!.keys(new KeyboardEvent("keydown", { key: "v", metaKey: true }))).toBe(false);
  await Promise.resolve();
  await Promise.resolve();
  expect(readText).not.toHaveBeenCalled();
  expect(terminal().write).not.toHaveBeenCalled();
});
