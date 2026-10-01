import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { Welcome } from "@renderer/features/onboarding/Welcome";
import { useAgents } from "@renderer/state/agents";
import { useOnboarding } from "@renderer/state/onboarding";
import { useProjects } from "@renderer/state/projects";
import { useSessions } from "@renderer/state/sessions";
import { useSettings } from "@renderer/state/settings";
import { defaultSettings, type Project } from "@shared/types";
import type { AgentStatus } from "@shared/agents";

const agent = (overrides: Partial<AgentStatus>) =>
  ({
    id: "claude-code",
    name: "Claude Code",
    icon: null,
    installed: false,
    launchWithoutBinary: false,
    auth: "unknown",
    authMethods: [],
    ...overrides,
  }) as unknown as AgentStatus;

async function toAgentStep() {
  const user = userEvent.setup();
  render(<Welcome />);
  await user.click(screen.getByRole("button", { name: /Continue/ }));
  return user;
}

beforeEach(() => {
  useOnboarding.setState({ step: 0 });
  useAgents.setState({ agents: [], ready: false, loadError: null, jobs: {} });
});

describe("the welcome", () => {
  it("moves focus to each new step's heading, not to the page, on Continue", async () => {
    const user = await toAgentStep();
    // Continue is disabled while detection runs; focus is on the step's heading.
    expect(document.activeElement).not.toBe(document.body);
    expect(screen.getByRole("heading", { name: "Connect an agent" })).toHaveFocus();
    act(() => useAgents.setState({ ready: true }));
    await user.click(await screen.findByRole("button", { name: /Continue/ }));
    // No Continue on the last step: the button went with the step.
    expect(screen.queryByRole("button", { name: /Continue/ })).toBeNull();
    expect(document.activeElement).not.toBe(document.body);
    expect(document.activeElement?.tagName).toBe("H1");
  });

  it("names the panes as they are and the viewer's Annotate action", () => {
    render(<Welcome />);
    expect(screen.getByText("Session in the middle.")).toBeInTheDocument();
    expect(screen.getByText("Select a face or edge and Annotate it.")).toBeInTheDocument();
    expect(screen.queryByText(/Chat on the left/)).toBeNull();
  });

  it("reserves the title bar and the traffic lights' corner like Settings", () => {
    const { container } = render(<Welcome />);
    const strip = container.querySelector<HTMLElement>("[data-onboarding-titlebar]")!;
    expect(strip.style.height).toBe("var(--titlebar-height)");
    expect(strip.style.paddingLeft).toBe("var(--titlebar-inset)");
  });

  it("says it is looking while detection has not answered, with Continue held until it does", async () => {
    await toAgentStep();
    expect(screen.getByText("Looking for agents on this machine…")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^Continue$/ })).toBeDisabled();
    expect(screen.queryByRole("button", { name: /without an agent/ })).toBeNull();

    useAgents.setState({ agents: [agent({})], ready: true });
    expect(await screen.findByRole("button", { name: /Continue without an agent/ })).toBeEnabled();
  });

  it("offers an enabled Continue without an agent when detection answered with an empty table", async () => {
    await toAgentStep();
    expect(screen.getByRole("button", { name: /^Continue$/ })).toBeDisabled();
    // Detection's answer arrives on `agents.status`; an empty one is still an answer.
    useAgents.getState().receive([]);
    expect(await screen.findByRole("button", { name: /Continue without an agent/ })).toBeEnabled();
  });

  it("stops waiting when the agent list cannot be read, and says so rather than showing no agents", async () => {
    const logged = vi.spyOn(console, "error").mockImplementation(() => {});
    vi.mocked(window.textToCad.agents.list).mockRejectedValueOnce(new Error("ipc down"));
    await useAgents.getState().load();
    expect(useAgents.getState()).toMatchObject({ ready: true, loadError: "ipc down" });
    expect(logged).toHaveBeenCalledWith(expect.stringContaining("Could not read the agent list"), expect.any(Error));
    logged.mockRestore();

    await toAgentStep();
    expect(screen.getByRole("alert")).toHaveTextContent("Could not read the agent list: ipc down");
    expect(screen.getByRole("button", { name: /Continue without an agent/ })).toBeEnabled();

    // A list that arrives afterwards is the answer, and the failure goes.
    useAgents.getState().receive([agent({})]);
    expect(await screen.findByRole("button", { name: /Install/ })).toBeInTheDocument();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("keeps waiting on an empty first list: that is the probe still running, not an answer", async () => {
    vi.mocked(window.textToCad.agents.list).mockResolvedValueOnce([]);
    await useAgents.getState().load();
    expect(useAgents.getState().ready).toBe(false);
  });

  it("pins the block's top rather than centring it, so steps do not jump", () => {
    const { container } = render(<Welcome />);
    const body = container.querySelector<HTMLElement>("[data-onboarding-body]")!;
    expect(body.className).not.toMatch(/\bitems-center\b/);
    expect(body.className).toMatch(/\bpt-\[/);
  });

  it("offers Continue without an agent when none is ready, and plain Continue once one is", async () => {
    useAgents.setState({ agents: [agent({})], ready: true });
    await toAgentStep();
    expect(screen.queryByText("Looking for agents on this machine…")).toBeNull();
    expect(screen.getByRole("button", { name: /Install/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Continue without an agent/ })).toBeInTheDocument();

    useAgents.setState({ agents: [agent({ installed: true, auth: "authenticated" })] });
    expect(await screen.findByRole("button", { name: /^Continue$/ })).toBeInTheDocument();
  });

  // A warm launch answers agents.list at once with the last launch's rows (`probing`): their
  // "not installed" and "signed out" are provisional, and Continue must not announce them.
  it("holds Continue on Checking… while the last launch's rows are being confirmed, and offers no Install for them", async () => {
    useAgents.setState({
      agents: [agent({ probing: true }), agent({ id: "codex", name: "Codex", installed: true, auth: "unauthenticated", probing: true })],
      ready: true,
    });
    await toAgentStep();
    expect(screen.queryByRole("button", { name: /Continue without an agent/ })).toBeNull();
    expect(screen.getByRole("button", { name: "Checking…" })).toBeDisabled();
    expect(screen.queryByRole("button", { name: /Install/ })).toBeNull();

    useAgents.getState().receive([agent({}), agent({ id: "codex", name: "Codex", installed: true, auth: "unauthenticated" })]);
    expect(await screen.findByRole("button", { name: /Continue without an agent/ })).toBeEnabled();
    expect(screen.getByRole("button", { name: /Install/ })).toBeInTheDocument();
  });

  it("says Not signed in only when detection found the agent signed out", async () => {
    useAgents.setState({
      agents: [agent({ installed: true, auth: "unknown" }), agent({ id: "codex", name: "Codex", installed: true, auth: "unauthenticated" })],
      ready: true,
    });
    await toAgentStep();
    expect(screen.getByText("Installed")).toBeInTheDocument();
    expect(screen.getAllByText("Not signed in")).toHaveLength(1);
  });
});

describe("the welcome's start step", () => {
  const patch = vi.fn(async () => undefined);
  let resolveSample: (project: Project) => void = () => {};
  let rejectSample: (error: Error) => void = () => {};

  beforeEach(() => {
    patch.mockClear();
    useProjects.setState({ activeId: "/mine", draft: null });
    useSessions.setState({ activeId: "s1" });
    useSettings.setState({ settings: { ...defaultSettings(), onboardingCompleted: false }, patch } as never);
    useAgents.setState({ agents: [agent({ installed: true, auth: "authenticated" })], ready: true });
    (window.textToCad as unknown as { onboarding: unknown }).onboarding = {
      status: vi.fn(async () => ({ enabled: true })),
      createSample: vi.fn(
        () =>
          new Promise<Project>((resolve, reject) => {
            resolveSample = resolve;
            rejectSample = reject;
          }),
      ),
    };
  });

  async function toStartStep() {
    const user = userEvent.setup();
    render(<Welcome />);
    await user.click(screen.getByRole("button", { name: /Continue/ }));
    await user.click(screen.getByRole("button", { name: /^Continue$/ }));
    return user;
  }

  // Back cancels it: the welcome is not finished, and the sample is not
  // selected behind it — the folder and the session the person had stay.
  it("neither finishes the welcome nor selects the sample when the person went Back while it was copying", async () => {
    const user = await toStartStep();
    await user.click(screen.getByRole("button", { name: /Try the sample/ }));
    await user.click(screen.getByRole("button", { name: "Back" }));
    await act(async () => resolveSample({ id: "/s", name: "text-to-cad Sample", path: "/s", createdAt: 0 }));
    expect(patch).not.toHaveBeenCalledWith({ onboardingCompleted: true });
    expect(useProjects.getState()).toMatchObject({ activeId: "/mine", draft: null });
    expect(useSessions.getState().activeId).toBe("s1");
  });

  it("selects the sample and finishes the welcome when it is ready and the person stayed", async () => {
    const user = await toStartStep();
    await user.click(screen.getByRole("button", { name: /Try the sample/ }));
    await act(async () => resolveSample({ id: "/s", name: "text-to-cad Sample", path: "/s", createdAt: 0 }));
    expect(patch).toHaveBeenCalledWith({ onboardingCompleted: true });
    expect(useProjects.getState()).toMatchObject({ activeId: "/s", draft: { path: "/s" } });
    expect(useSessions.getState().activeId).toBeNull();
  });

  it("announces a failed copy", async () => {
    const user = await toStartStep();
    await user.click(screen.getByRole("button", { name: /Try the sample/ }));
    await act(async () => rejectSample(new Error("The disk is full.")));
    expect(screen.getByRole("alert")).toHaveTextContent("The disk is full.");
  });
});
