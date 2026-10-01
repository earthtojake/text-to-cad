/**
 * An install or sign-in is a pty job in main, and the store holds the truth
 * about it: a drawer or an agent row that is closed and opened again, or
 * unmounted and remounted, has to find the job still running rather than
 * offer to start a second one.
 */
import { act, fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { TooltipProvider } from "@renderer/components/ui/tooltip";
import { AgentDrawer } from "@renderer/features/settings/AgentDrawer";
import { AgentsPage } from "@renderer/features/settings/pages/AgentsPage";
import { useAgents } from "@renderer/state/agents";
import { useSettings } from "@renderer/state/settings";
import { defaultSettings } from "@shared/types";
import type { AgentStatus } from "@shared/agents";

const codex = {
  id: "codex",
  name: "Codex",
  description: "",
  websiteUrl: "https://example.com",
  docsUrl: "https://example.com",
  icon: null,
  installed: false,
  launchWithoutBinary: false,
  binaryPath: null,
  version: null,
  auth: "unknown",
  authMethods: [],
  capabilities: {},
  install: { macos: [{ label: "npm", command: "npm i -g codex" }], windows: [], linux: [] },
  launch: { command: "codex", args: [], env: {} },
  skillRoots: "native",
} as unknown as AgentStatus;

beforeEach(() => {
  useSettings.setState({ settings: defaultSettings(), ready: true });
  useAgents.setState({ agents: [codex], ready: true, loadError: null, jobs: {} });
});

describe("a job that outlives the component that started it", () => {
  it("the drawer, opened while the agent's install is running, shows it running with its log", () => {
    useAgents.setState({ jobs: { j1: { agentId: "codex", kind: "install", output: "fetching…\n", exitCode: null } } });
    render(
      <TooltipProvider>
        <AgentDrawer agent={codex} onOpenChange={() => {}} open platform="macos" />
      </TooltipProvider>,
    );
    expect(screen.getByRole("button", { name: "Install" })).toBeDisabled();
    expect(screen.getByText("fetching…")).toBeInTheDocument();
  });
});

describe("a job that has printed nothing yet", () => {
  it("is still found running by a drawer remounted before the first chunk", async () => {
    vi.mocked(window.textToCad.agents.install).mockResolvedValue({ jobId: "j1" });
    const drawer = (
      <TooltipProvider>
        <AgentDrawer agent={codex} onOpenChange={() => {}} open platform="macos" />
      </TooltipProvider>
    );
    const first = render(drawer);
    fireEvent.click(screen.getByRole("button", { name: "Install" }));
    await screen.findByText("Waiting for output…");
    first.unmount();
    render(drawer);
    expect(screen.getByRole("button", { name: "Install" })).toBeDisabled();
    expect(screen.getByText("Waiting for output…")).toBeInTheDocument();
  });
});

describe("a job that ended badly", () => {
  const drawer = (agent: AgentStatus) => (
    <TooltipProvider>
      <AgentDrawer agent={agent} onOpenChange={() => {}} open platform="macos" />
    </TooltipProvider>
  );

  it("is labelled with its exit code, and still is when the drawer is opened again", () => {
    useAgents.getState().receiveOutput({ jobId: "j1", agentId: "codex", kind: "install", data: "EACCES\n", exitCode: 1 });
    render(drawer(codex));
    expect(screen.getByText("Install failed (exit 1)")).toBeInTheDocument();
    expect(screen.getByText("EACCES")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Install" })).toBeEnabled();
  });

  it("names a failed sign-in as one", () => {
    const installed = { ...codex, installed: true, auth: "unauthenticated", authMethods: [{ type: "cli-login", label: "Sign in with Codex" }] } as unknown as AgentStatus;
    useAgents.getState().receiveOutput({ jobId: "j2", agentId: "codex", kind: "login", data: "", exitCode: 2 });
    render(drawer(installed));
    expect(screen.getByText("Sign in failed (exit 2)")).toBeInTheDocument();
  });

  it("says nothing of an install that failed once the agent is installed", () => {
    useAgents.getState().receiveOutput({ jobId: "j1", agentId: "codex", kind: "install", data: "EACCES\n", exitCode: 1 });
    render(drawer({ ...codex, installed: true, binaryPath: "/bin/codex" } as AgentStatus));
    expect(screen.queryByText(/Install failed/)).toBeNull();
  });

  it("says nothing of a sign-in that failed once the agent is signed in", () => {
    const signedIn = { ...codex, installed: true, auth: "authenticated", authMethods: [{ type: "cli-login", label: "Sign in with Codex" }] } as unknown as AgentStatus;
    useAgents.getState().receiveOutput({ jobId: "j2", agentId: "codex", kind: "login", data: "", exitCode: 2 });
    render(drawer(signedIn));
    expect(screen.queryByText(/Sign in failed/)).toBeNull();
  });

  it("does not bring back the failed run this mount started after a later run succeeded", async () => {
    vi.mocked(window.textToCad.agents.install).mockResolvedValue({ jobId: "j1" });
    render(drawer(codex));
    fireEvent.click(screen.getByRole("button", { name: "Install" }));
    await screen.findByText("Waiting for output…");
    act(() => useAgents.getState().receiveOutput({ jobId: "j1", agentId: "codex", kind: "install", data: "EACCES\n", exitCode: 1 }));
    expect(screen.getByText("Install failed (exit 1)")).toBeInTheDocument();
    // Another mount (the welcome card) ran it again, and that run worked.
    act(() => useAgents.getState().receiveOutput({ jobId: "j2", agentId: "codex", kind: "install", data: "ok\n", exitCode: 0 }));
    expect(screen.queryByText(/Install failed/)).toBeNull();
  });

  it("says nothing of a job that exited cleanly", () => {
    useAgents.getState().receiveOutput({ jobId: "j3", agentId: "codex", kind: "install", data: "done\n", exitCode: 0 });
    render(drawer(codex));
    expect(screen.queryByText(/failed/)).toBeNull();
  });
});

describe("a job main refuses to start", () => {
  const drawer = (
    <TooltipProvider>
      <AgentDrawer agent={codex} onOpenChange={() => {}} open platform="macos" />
    </TooltipProvider>
  );

  it("says so under Install, without an empty log", async () => {
    vi.mocked(window.textToCad.agents.install).mockRejectedValueOnce(new Error("spawn EACCES"));
    render(drawer);
    fireEvent.click(screen.getByRole("button", { name: "Install" }));
    expect(await screen.findByText("Install could not start: spawn EACCES")).toBeInTheDocument();
    expect(screen.queryByText("Waiting for output…")).toBeNull();
    expect(screen.getByRole("button", { name: "Install" })).toBeEnabled();
  });

  it("says so under Sign in, and clears on the next try", async () => {
    const installed = { ...codex, installed: true, auth: "unauthenticated", authMethods: [{ type: "cli-login", label: "Sign in with Codex" }] } as unknown as AgentStatus;
    vi.mocked(window.textToCad.agents.login).mockRejectedValueOnce(new Error("no pty"));
    render(
      <TooltipProvider>
        <AgentDrawer agent={installed} onOpenChange={() => {}} open platform="macos" />
      </TooltipProvider>,
    );
    fireEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByText("Sign in could not start: no pty")).toBeInTheDocument();
    vi.mocked(window.textToCad.agents.login).mockResolvedValueOnce({ jobId: "j9" });
    fireEvent.click(screen.getByRole("button", { name: "Sign in" }));
    await screen.findByText("Waiting for output…");
    expect(screen.queryByText(/could not start/)).toBeNull();
  });
});

describe("the Agents page's Refresh", () => {
  it("draws a refresh main refuses as the agent-list alert", async () => {
    vi.mocked(window.textToCad.agents.refresh).mockRejectedValueOnce(new Error("probe crashed"));
    render(
      <TooltipProvider>
        <AgentsPage />
      </TooltipProvider>,
    );
    fireEvent.click(screen.getByRole("button", { name: "Refresh" }));
    expect(await screen.findByText("probe crashed")).toBeInTheDocument();
    expect(screen.getByText("Could not read the agent list")).toBeInTheDocument();
  });
});

describe("a row the last launch left", () => {
  it("offers no Install in the drawer until the probe has confirmed the agent is missing", () => {
    render(
      <TooltipProvider>
        <AgentDrawer agent={{ ...codex, probing: true }} onOpenChange={() => {}} open platform="macos" />
      </TooltipProvider>,
    );
    expect(screen.queryByRole("button", { name: "Install" })).toBeNull();
  });
});

describe("the Agents page's status dot", () => {
  it("is not green beside 'checking sign-in…' for a row the last launch left signed out", async () => {
    const row = { ...codex, installed: true, auth: "unauthenticated", probing: true } as AgentStatus;
    vi.mocked(window.textToCad.agents.list).mockResolvedValue([row]);
    useAgents.setState({ agents: [row], ready: true, loadError: null });
    render(
      <TooltipProvider>
        <AgentsPage />
      </TooltipProvider>,
    );
    const line = await screen.findByText(/checking sign-in…/);
    const dot = line.closest("[data-agent-row]")!.querySelector("span.rounded-full")!;
    expect(dot).not.toHaveClass("bg-emerald-500");
    expect(dot).toHaveClass("bg-muted-foreground/50");
  });
});
