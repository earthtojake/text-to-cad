import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { NewSession } from "@renderer/features/session/NewSession";
import { useAcp } from "@renderer/state/acp";
import { useAgents } from "@renderer/state/agents";
import { useAgentOptions } from "@renderer/state/agent-options";
import { useComposer } from "@renderer/state/composer";
import { useProjects } from "@renderer/state/projects";
import { useSessions } from "@renderer/state/sessions";
import { useUi } from "@renderer/state/ui";
import { toast } from "sonner";
import { initialSessionState } from "@shared/acp/types";
import type { AgentStatus } from "@shared/agents";

// The composer and its chips are their own suites; here the box is a button
// that sends what the draft holds (a stock prompt when it is empty) the way the
// real composer does: taken whole on submit, put back when the start rejects —
// and a submit asked for from outside (`requestSubmit`) is the same send.
vi.mock("@renderer/features/session/Composer", async () => {
  const { useEffect } = await import("react");
  const { useComposer } = await import("@renderer/state/composer");
  return {
    Composer: ({ onSubmit, chips, trailing, newDraftKey, placeholder, refuseSend }: {
      onSubmit: (text: string, content: unknown[], draft: unknown) => Promise<void> | void;
      chips?: React.ReactNode; trailing?: React.ReactNode; newDraftKey: string; placeholder?: string; refuseSend?: string;
    }) => {
      const send = () => {
        const store = useComposer.getState();
        const text = store.drafts[newDraftKey]?.trim() || "make a cube";
        // The box's attachments go with the draft, the way the real composer hands them over.
        const files = store.takeFiles(newDraftKey);
        const taken = { ...store.takeDraft(newDraftKey), ...(files.length ? { files } : {}) };
        void Promise.resolve(onSubmit(text, [{ type: "text", text }], taken)).catch(() => useComposer.getState().restoreDraft(newDraftKey, taken));
      };
      const request = useComposer((state) => state.submitRequest?.key === newDraftKey ? state.submitRequest.nonce : null);
      useEffect(() => { if (request !== null) send(); }, [request]);
      return (
        <>
          <input aria-label="Prompt" placeholder={placeholder} readOnly />
          <button aria-description={refuseSend} aria-disabled={refuseSend ? "true" : undefined} onClick={refuseSend ? undefined : send} type="button">Send</button>
          {chips}
          {trailing}
        </>
      );
    },
  };
});
vi.mock("sonner", () => ({ toast: Object.assign(vi.fn(), { error: vi.fn() }) }));
// A chip is its name and the reason it is not offered, if it has one.
vi.mock("@renderer/features/session/ComposerChips", () => {
  const chip = (name: string) => ({ disabledReason }: { disabledReason?: string }) => (
    <button aria-description={disabledReason} aria-disabled={disabledReason ? "true" : undefined} type="button">{name}</button>
  );
  return { EffortChip: chip("Effort"), GitModeChip: () => null, ModeChip: chip("Mode"), ModelChip: chip("Model"), ProjectChip: () => null };
});
const options = vi.hoisted(() => ({ mode: null as unknown }));
vi.mock("@renderer/lib/git-mode", () => ({
  resolveGitMode: () => "checkout",
  useProjectGitInfo: () => null,
}));
vi.mock("@renderer/state/agent-options", async () => {
  const { create } = await import("zustand");
  return {
    useAgentOptions: create(() => ({ probe: vi.fn(), setDefaults: vi.fn(), setEffort: vi.fn() })),
    useProviderModels: () => [],
    useProviderEffort: () => null,
    useProviderMode: () => options.mode,
  };
});

const PROJECT = { id: "p1", name: "bracket", path: "/bracket", createdAt: 0 };
const AGENT = {
  id: "claude",
  name: "Claude Code",
  installed: true,
  launchWithoutBinary: true,
  // Detection could not tell (the keychain case): a send goes out, and it is the start that finds
  // the sign-in missing. An agent detected signed out is the no-agent card's, which refuses the send.
  auth: "unknown",
  authMethods: [{ type: "cli-login", label: "Sign in" }],
} as unknown as AgentStatus;

const realSubmit = useComposer.getState().submit;
const create = vi.fn();
const submit = vi.fn(async () => undefined);
const openSettings = vi.fn();

beforeEach(() => {
  create.mockReset();
  submit.mockReset();
  openSettings.mockReset();
  useUi.setState({ openSettings } as never);
  useAgentOptions.setState({ probe: vi.fn(async () => undefined) } as never);
  useAgents.setState({ agents: [AGENT], jobs: {}, ready: true, loadError: null });
  options.mode = null;
  useAcp.setState({ create } as never);
  useComposer.setState({ submit, drafts: {}, annotations: {}, submitRequest: null } as never);
});

describe("a start that needs a sign-in", () => {
  it("sends the same prompt again from Try again", async () => {
    const user = userEvent.setup();
    create.mockRejectedValueOnce(new Error("Authentication required")).mockResolvedValueOnce("s1");
    render(<NewSession project={PROJECT} />);

    await user.click(screen.getByRole("button", { name: "Send" }));
    await user.click(await screen.findByRole("button", { name: "Try again" }));

    expect(create).toHaveBeenCalledTimes(2);
    expect(submit).toHaveBeenCalledWith("s1", "make a cube", [{ type: "text", text: "make a cube" }], expect.anything());
    expect(screen.queryByRole("button", { name: "Try again" })).toBeNull();
  });

  it("leaves the draft to the composer on a failed start, and clears it once Try again has sent it", async () => {
    const user = userEvent.setup();
    const key = "__new__:p1";
    // What the composer restored after the failed start: text and annotation apart.
    useComposer.setState({
      drafts: { [key]: "make a cube" },
      annotations: { [key]: [{ id: "a1", text: "hollow it", references: [] }] },
    });
    create.mockRejectedValueOnce(new Error("Authentication required")).mockResolvedValueOnce("s1");
    render(<NewSession project={PROJECT} />);

    await user.click(screen.getByRole("button", { name: "Send" }));
    await screen.findByRole("button", { name: "Try again" });
    expect(useComposer.getState().drafts[key], "not overwritten with the flattened prompt").toBe("make a cube");
    expect(useComposer.getState().annotations[key]).toHaveLength(1);

    await user.click(screen.getByRole("button", { name: "Try again" }));
    expect(submit).toHaveBeenCalledWith("s1", "make a cube", [{ type: "text", text: "make a cube" }], expect.anything());
    expect(useComposer.getState().drafts[key]).toBe("");
    expect(useComposer.getState().annotations[key]).toBeUndefined();
  });

  it("starts again by itself when a login that began after the failure exits 0", async () => {
    const user = userEvent.setup();
    // A login that finished before this failure is not this failure's sign-in.
    useAgents.setState({ jobs: { old: { agentId: "claude", kind: "login", output: "", exitCode: 0 } } });
    create.mockRejectedValueOnce(new Error("Authentication required")).mockResolvedValueOnce("s1");
    render(<NewSession project={PROJECT} />);

    await user.click(screen.getByRole("button", { name: "Send" }));
    await screen.findByRole("button", { name: "Try again" });
    expect(create).toHaveBeenCalledTimes(1);

    act(() => useAgents.getState().receiveOutput({ jobId: "j1", agentId: "claude", kind: "login", data: "ok", exitCode: null }));
    expect(create).toHaveBeenCalledTimes(1);
    await act(async () => useAgents.getState().receiveOutput({ jobId: "j1", agentId: "claude", kind: "login", data: "", exitCode: 0 }));

    expect(create).toHaveBeenCalledTimes(2);
    expect(submit).toHaveBeenCalledWith("s1", "make a cube", [{ type: "text", text: "make a cube" }], expect.anything());
  });

  it("Try again sends what the box holds now, not what failed", async () => {
    const user = userEvent.setup();
    const key = "__new__:p1";
    useComposer.setState({ drafts: { [key]: "make a cube" } });
    create.mockRejectedValueOnce(new Error("Authentication required")).mockResolvedValueOnce("s1");
    render(<NewSession project={PROJECT} />);

    await user.click(screen.getByRole("button", { name: "Send" }));
    await screen.findByRole("button", { name: "Try again" });
    // The person edits the restored draft before retrying.
    act(() => useComposer.getState().setDraft(key, "make a sphere"));
    await user.click(screen.getByRole("button", { name: "Try again" }));

    expect(submit).toHaveBeenCalledWith("s1", "make a sphere", [{ type: "text", text: "make a sphere" }], expect.anything());
    expect(submit).not.toHaveBeenCalledWith("s1", "make a cube", expect.anything(), expect.anything());
  });

  it("does not start again by itself after a login when the draft was edited since the failure", async () => {
    const user = userEvent.setup();
    const key = "__new__:p1";
    useComposer.setState({ drafts: { [key]: "make a cube" } });
    create.mockRejectedValueOnce(new Error("Authentication required")).mockResolvedValueOnce("s1");
    render(<NewSession project={PROJECT} />);

    await user.click(screen.getByRole("button", { name: "Send" }));
    await screen.findByRole("button", { name: "Try again" });
    act(() => {
      useComposer.getState().setDraft(key, "make a cube, but hollow");
      useComposer.setState({ annotations: { [key]: [{ id: "a2", text: "this face", references: [] }] } });
    });
    await act(async () => useAgents.getState().receiveOutput({ jobId: "j1", agentId: "claude", kind: "login", data: "", exitCode: 0 }));

    expect(create).toHaveBeenCalledTimes(1);
    expect(useComposer.getState().drafts[key], "the edit is kept").toBe("make a cube, but hollow");
    expect(useComposer.getState().annotations[key]).toHaveLength(1);
  });

  it("does not start again when the login fails", async () => {
    const user = userEvent.setup();
    create.mockRejectedValueOnce(new Error("Authentication required"));
    render(<NewSession project={PROJECT} />);

    await user.click(screen.getByRole("button", { name: "Send" }));
    await screen.findByRole("button", { name: "Try again" });
    await act(async () => useAgents.getState().receiveOutput({ jobId: "j1", agentId: "claude", kind: "login", data: "", exitCode: 1 }));

    expect(create).toHaveBeenCalledTimes(1);
  });
});

describe("a machine with no agent ready", () => {
  // Both offered agents launch without their CLI, so `useInstalledAgents`
  // counts them whatever is on the machine; the card is for when detection
  // found every one of them signed out.
  const claude = { ...AGENT, id: "claude-code", name: "Claude Code", installed: true, launchWithoutBinary: true, auth: "unauthenticated" } as unknown as AgentStatus;
  const codex = { ...AGENT, id: "codex", name: "Codex", installed: true, launchWithoutBinary: true, auth: "unauthenticated" } as unknown as AgentStatus;

  it("says so before anything is typed, with each agent's sign-in and Settings › Agents", async () => {
    const user = userEvent.setup();
    const login = vi.fn(async () => "job1");
    useAgents.setState({ agents: [claude, codex], ready: true, login } as never);
    render(<NewSession project={PROJECT} />);

    expect(screen.getByText("No agent ready")).toBeInTheDocument();
    expect(screen.getByText(/Sign in to Claude Code or Codex, or install one/)).toBeInTheDocument();
    expect(screen.getAllByText("Not signed in")).toHaveLength(2);
    await user.click(screen.getAllByRole("button", { name: "Sign in" })[0]!);
    expect(login).toHaveBeenCalledWith("claude-code");
    await user.click(screen.getByRole("button", { name: "Settings › Agents" }));
    expect(openSettings).toHaveBeenCalledWith("agents");
    expect(create).not.toHaveBeenCalled();
  });

  it("lists the agent one sign-in away before one that needs installing", () => {
    const gone = { ...claude, installed: false, launchWithoutBinary: false, auth: "unknown" } as AgentStatus;
    useAgents.setState({ agents: [gone, codex], ready: true });
    render(<NewSession project={PROJECT} />);

    const rows = [...document.querySelectorAll("[data-agent-setup] [data-onboarding-agent]")].map((row) => row.getAttribute("data-onboarding-agent"));
    expect(rows).toEqual(["codex", "claude-code"]);
    expect(screen.getByRole("button", { name: "Install" })).toBeInTheDocument();
  });

  it("is not shown once an agent is ready, even one that runs without its CLI", () => {
    useAgents.setState({ agents: [{ ...claude, installed: false, auth: "authenticated" } as AgentStatus, codex], ready: true });
    render(<NewSession project={PROJECT} />);
    expect(screen.queryByText("No agent ready")).toBeNull();
  });

  it("is not shown for an agent whose sign-in detection cannot tell", () => {
    const copilot = { ...AGENT, id: "copilot", name: "Copilot", installed: true, launchWithoutBinary: false, auth: "unknown" } as unknown as AgentStatus;
    useAgents.setState({ agents: [claude, codex, copilot], ready: true });
    render(<NewSession project={PROJECT} />);
    expect(screen.queryByText("No agent ready")).toBeNull();
  });

  it("does not claim it while detection has not answered", () => {
    useAgents.setState({ agents: [], ready: false });
    render(<NewSession project={PROJECT} />);
    expect(screen.queryByText("No agent ready")).toBeNull();
  });

  it("does not offer the chips or the send while no agent is ready, and says why", () => {
    options.mode = { currentModeId: "auto", modes: [{ id: "auto", name: "Auto" }] };
    useAgents.setState({ agents: [claude, codex], ready: true });
    render(<NewSession project={PROJECT} />);
    for (const name of ["Mode", "Send"]) {
      const control = screen.getByRole("button", { name });
      expect(control, name).toHaveAttribute("aria-disabled", "true");
      expect(control, name).toHaveAccessibleDescription(/No agent ready/);
    }
  });

  it("says the agent list could not be read, with the read again, rather than asking for a sign-in", async () => {
    const user = userEvent.setup();
    const load = vi.fn(async () => undefined);
    useAgents.setState({ agents: [], ready: true, loadError: "agents.list timed out", load } as never);
    render(<NewSession project={PROJECT} />);
    expect(screen.queryByText("No agent ready")).toBeNull();
    expect(screen.getByText("Could not check for agents")).toBeInTheDocument();
    expect(screen.getByText(/agents\.list timed out/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Try again" }));
    expect(load).toHaveBeenCalled();
  });

  it("shows a failing Try again trying, then the error it came back with", async () => {
    const user = userEvent.setup();
    let answer!: () => void;
    const load = vi.fn(
      () =>
        new Promise<void>((resolve) => {
          answer = () => {
            useAgents.setState({ loadError: "spawn /bin/zsh EACCES" });
            resolve();
          };
        }),
    );
    useAgents.setState({ agents: [], ready: true, loadError: "agents.list timed out", load } as never);
    render(<NewSession project={PROJECT} />);

    await user.click(screen.getByRole("button", { name: "Try again" }));
    expect(screen.getByRole("button", { name: "Trying again…" })).toBeDisabled();

    await act(async () => answer());
    expect(screen.getByText(/spawn \/bin\/zsh EACCES/)).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("Tried again, and it failed again.");
    expect(screen.getByRole("button", { name: "Try again" })).toBeEnabled();
  });

  it("does not carry a failed Try again over to the sign-in card the read turns into", async () => {
    const user = userEvent.setup();
    const load = vi.fn(async () => {
      useAgents.setState({ agents: [claude, codex], loadError: null });
    });
    useAgents.setState({ agents: [], ready: true, loadError: "agents.list timed out", load } as never);
    render(<NewSession project={PROJECT} />);

    await user.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByText("No agent ready")).toBeInTheDocument();
    expect(screen.queryByText("Tried again, and it failed again.")).toBeNull();
  });

  it("offers Settings › Agents beside Dismiss when the start fails for another reason", async () => {
    const user = userEvent.setup();
    useAgents.setState({ agents: [{ ...AGENT, auth: "authenticated" } as AgentStatus] });
    create.mockRejectedValueOnce(new Error("Claude Code is not installed"));
    render(<NewSession project={PROJECT} />);

    await user.click(screen.getByRole("button", { name: "Send" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Claude Code is not installed");
    expect(screen.getByRole("button", { name: "Dismiss" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /Open Settings › Agents/ }));
    expect(openSettings).toHaveBeenCalledWith("agents");
  });
});

describe("the model chip", () => {
  it("says the models are loading while the agents are probed, and goes once they answer", async () => {
    let answer!: () => void;
    useAgentOptions.setState({ probe: vi.fn(() => new Promise<void>((resolve) => (answer = resolve))) } as never);
    render(<NewSession project={PROJECT} />);

    expect(screen.getByRole("button", { name: /Loading models/ })).toBeDisabled();
    // All three slots hold their place, so the row does not jump when they land.
    expect(document.querySelector("[data-chip=mode-loading]")).not.toBeNull();
    expect(document.querySelector("[data-chip=effort-loading]")).not.toBeNull();
    await act(async () => answer());
    expect(screen.queryByRole("button", { name: /Loading models/ })).toBeNull();
    expect(document.querySelector("[data-chip=mode-loading]")).toBeNull();
    expect(document.querySelector("[data-chip=effort-loading]")).toBeNull();
  });

  it("holds the chips' places while detection has not answered yet", () => {
    useAgents.setState({ ready: false });
    render(<NewSession project={PROJECT} />);
    expect(screen.getByRole("button", { name: /Loading models/ })).toBeDisabled();
    expect(document.querySelector("[data-chip=mode-loading]")).not.toBeNull();
  });

  it("hints at CAD in the box, on this screen only", () => {
    render(<NewSession project={PROJECT} />);
    expect(screen.getByPlaceholderText("Describe a part to build…")).toBeInTheDocument();
  });
});

describe("a first prompt the agent refuses", () => {
  const bridge = window.textToCad as unknown as Record<string, unknown>;
  const saved = bridge.sessions;
  afterEach(() => {
    bridge.sessions = saved;
  });

  it("lands in the new session's box with its attachment, not spent", async () => {
    const user = userEvent.setup();
    const key = "__new__:p1";
    const photo = new File(["png"], "bracket.png", { type: "image/png" });
    const refused = "Claude Code cannot take an image in a prompt. Remove the attachment to send.";
    bridge.sessions = { ...(saved as object), prompt: vi.fn(async () => ({ stopReason: "refused", refused })) };
    // The session just made connects, idle, when it is asked back.
    const ensureLoaded = vi.fn(async (id: string) =>
      useAcp.setState((state) => ({ sessions: { ...state.sessions, [id]: { ...initialSessionState(id, "claude"), status: "idle" } } })));
    useAcp.setState({ create, ensureLoaded, sessions: {}, loading: {} } as never);
    useComposer.setState({ submit: realSubmit, drafts: { [key]: "look at this" }, pendingFiles: { [key]: [photo] }, queues: {}, sending: {}, paused: {} } as never);
    create.mockResolvedValueOnce("s1");
    render(<NewSession project={PROJECT} />);

    await user.click(screen.getByRole("button", { name: "Send" }));

    await waitFor(() => expect(useComposer.getState().drafts.s1).toBe("look at this"));
    expect(useComposer.getState().pendingFiles.s1).toEqual([photo]);
  });
});

describe("a create that outlasts the screen that asked for it", () => {
  const deferred = <T,>() => {
    let resolve!: (value: T) => void;
    let reject!: (reason: unknown) => void;
    const promise = new Promise<T>((res, rej) => ((resolve = res), (reject = rej)));
    return { promise, resolve, reject };
  };

  it("says a failed create where the person is: a toast whose Try again brings the draft back", async () => {
    const user = userEvent.setup();
    const pending = deferred<string>();
    create.mockReturnValueOnce(pending.promise);
    useComposer.setState({ drafts: { "__new__:p1": "make a cube" } });
    const screenView = render(<NewSession project={PROJECT} />);
    await user.click(screen.getByRole("button", { name: "Send" }));
    // The person clicks the connecting row: the pane is that session, this screen is gone.
    screenView.unmount();
    useSessions.setState({ activeId: "provisional" });
    vi.mocked(toast.error).mockClear();

    await act(async () => pending.reject(new Error("agent would not start")));
    expect(toast.error).toHaveBeenCalledWith("agent would not start", expect.objectContaining({ action: expect.objectContaining({ label: "Try again" }) }));
    expect(useComposer.getState().drafts["__new__:p1"], "the draft is back in the box").toBe("make a cube");

    // The row is gone (`sessions.receive` nulls the active id); the person is on another project.
    useSessions.setState({ activeId: "other" });
    const { action } = vi.mocked(toast.error).mock.calls[0]![1] as unknown as { action: { onClick: () => void } };
    act(() => action.onClick());
    expect(useSessions.getState().activeId).toBeNull();
    expect(useProjects.getState().activeId).toBe("p1");
  });

  it("keeps its card in place while the screen is still there", async () => {
    const user = userEvent.setup();
    create.mockRejectedValueOnce(new Error("agent would not start"));
    render(<NewSession project={PROJECT} />);
    vi.mocked(toast.error).mockClear();
    await user.click(screen.getByRole("button", { name: "Send" }));
    expect(await screen.findByText("agent would not start")).toBeInTheDocument();
    expect(toast.error).not.toHaveBeenCalled();
  });

  it("does not pull the person back from the thread they moved to", async () => {
    const user = userEvent.setup();
    const pending = deferred<string>();
    create.mockReturnValueOnce(pending.promise);
    render(<NewSession project={PROJECT} />);
    await user.click(screen.getByRole("button", { name: "Send" }));
    act(() => useSessions.getState().setActive("B"));
    await act(async () => pending.resolve("s1"));
    expect(useSessions.getState().activeId).toBe("B");
  });

  it("shows no card and no toast for a create the person deleted while it started", async () => {
    const user = userEvent.setup();
    const pending = deferred<string>();
    create.mockReturnValueOnce(pending.promise);
    render(<NewSession project={PROJECT} />);
    vi.mocked(toast.error).mockClear();
    await user.click(screen.getByRole("button", { name: "Send" }));
    await act(async () => pending.reject(new Error("Error invoking remote method 'text-to-cad:sessions.create': Error: This session was deleted while it was starting.")));
    expect(screen.queryByText(/deleted while it was starting/)).toBeNull();
    expect(toast.error).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Send" })).toBeEnabled();
  });

  it("does not pull the person off another project's new-session screen", async () => {
    const user = userEvent.setup();
    const pending = deferred<string>();
    create.mockReturnValueOnce(pending.promise);
    useSessions.setState({ activeId: null, sessions: [] });
    const screenView = render(<NewSession project={PROJECT} />);
    await user.click(screen.getByRole("button", { name: "Send" }));
    // Project B's new-session screen: no thread is active, and this screen is gone.
    screenView.unmount();
    act(() => useProjects.getState().setActive("B"));
    await act(async () => pending.resolve("s1"));
    expect(useSessions.getState().activeId).toBeNull();
  });

  it("sends nothing to a thread archived while it was created, and keeps the draft in its box", async () => {
    const user = userEvent.setup();
    const pending = deferred<string>();
    create.mockReturnValueOnce(pending.promise);
    useComposer.setState({ drafts: { "__new__:p1": "make a cube" } });
    useSessions.setState({ activeId: null, sessions: [] });
    render(<NewSession project={PROJECT} />);
    await user.click(screen.getByRole("button", { name: "Send" }));
    // The sidebar archived the connecting row; the index now says so.
    useSessions.setState({ sessions: [{ id: "s1", projectId: "p1", archived: true }] } as never);
    await act(async () => pending.resolve("s1"));
    expect(submit).not.toHaveBeenCalled();
    expect(useComposer.getState().drafts.s1).toBe("make a cube");
    expect(useSessions.getState().activeId).toBeNull();
    useSessions.setState({ sessions: [] });
  });

  it("selects the new session when the person is still on it, or on nothing", async () => {
    const user = userEvent.setup();
    create.mockResolvedValueOnce("s1");
    useSessions.setState({ activeId: null });
    render(<NewSession project={PROJECT} />);
    await user.click(screen.getByRole("button", { name: "Send" }));
    await waitFor(() => expect(useSessions.getState().activeId).toBe("s1"));
  });
});
