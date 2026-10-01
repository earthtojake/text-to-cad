import { act, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { SessionView } from "@renderer/features/session/SessionView";
import { useAcp } from "@renderer/state/acp";
import { useComposer } from "@renderer/state/composer";
import { useProjects } from "@renderer/state/projects";
import { initialSessionState } from "@shared/acp/types";
import type { Project, Session } from "@shared/types";

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn(), dismiss: vi.fn(), info: vi.fn() } }));
vi.mock("@renderer/features/session/SessionHeader", () => ({ SessionHeader: () => null }));
vi.mock("@renderer/features/session/Transcript", () => ({ Transcript: () => <div data-transcript /> }));
vi.mock("@renderer/features/session/ContextMeter", () => ({ ContextMeter: () => null }));

// The composer's editor is ProseMirror, which measures the selection; jsdom lays nothing out.
const noRects = () => Object.assign([], { item: () => null }) as unknown as DOMRectList;
Range.prototype.getClientRects ??= noRects;
Range.prototype.getBoundingClientRect ??= () => new DOMRect();
(Text.prototype as unknown as { getClientRects: () => DOMRectList }).getClientRects ??= noRects;

const P: Project = { id: "p1", name: "p", path: "/p", createdAt: 0 };
const SESSION = { id: "s1", projectId: "p1", agentId: "claude", cwd: "/p", gitMode: "checkout", title: "New session", status: "idle" } as unknown as Session;

beforeEach(() => {
  useProjects.setState({ projects: [P], activeId: P.id });
  useAcp.setState({
    sessions: { s1: { ...initialSessionState("s1", "claude"), status: "idle" } },
    loading: {},
    reconnecting: {},
    loadErrors: {},
    ensureLoaded: vi.fn(async () => undefined),
  } as never);
  useComposer.setState({ drafts: {}, queues: {}, sending: {}, paused: {}, submitRequest: null });
});

describe("a prompt sent with no turn started yet", () => {
  // The box shows the spinner (`submitted`) and its button is disabled, but Enter still sends: the
  // submit is `type="button"` while SessionView hands Composer an `onStop`, so the editor's and the
  // vendored textarea's `button[type="submit"]` disabled check finds nothing to refuse, and the store
  // queues the text behind the prompt in flight. Drop `onStop` or retype the button and this fails.
  it("queues the next Enter's text behind it rather than ignoring it", async () => {
    useComposer.setState({ sending: { s1: 1 } });
    render(<SessionView session={SESSION} />);
    useComposer.getState().setDraft("s1", "and a second thing");
    act(() => useComposer.getState().requestSubmit("s1"));
    await vi.waitFor(() => expect(useComposer.getState().queues.s1).toHaveLength(1));
  });
});

describe("the queued prompts' remove buttons", () => {
  const queued = (id: string, text: string) => ({ id, text, content: [{ type: "text" as const, text }] });

  // Each row once wore the same name, so a screen reader's button list read "Remove from queue" twice
  // with nothing to tell the rows apart; the prompt's own words now ride in the name.
  it("are named for their prompt, so two rows are not the same button", () => {
    useComposer.setState({ queues: { s1: [queued("a", "add a fillet"), queued("b", "export the STEP")] } });
    const { getByRole } = render(<SessionView session={SESSION} />);
    getByRole("button", { name: "Remove from queue: add a fillet" });
    getByRole("button", { name: "Remove from queue: export the STEP" });
  });

  // jsdom lays nothing out, so the class string is the check: the button rests at opacity-0 until the
  // row is hovered, and a keyboard person tabbing onto it would be focused on something invisible.
  it("show themselves when they take keyboard focus", () => {
    useComposer.setState({ queues: { s1: [queued("a", "add a fillet")] } });
    const { getByRole } = render(<SessionView session={SESSION} />);
    expect(getByRole("button", { name: /^Remove from queue/ }).className).toContain("focus-visible:opacity-100");
  });
});

describe("the composer's accessible name", () => {
  // It was the placeholder, so it read "Do anything" at rest and "Send another message — it goes next"
  // the moment a turn started: the same box announced as two different controls.
  it("is the same while a turn runs as when idle", () => {
    const { rerender } = render(<SessionView session={SESSION} />);
    expect(screen.getByRole("textbox", { name: "Prompt" })).toBeInTheDocument();
    act(() => useAcp.setState({ sessions: { s1: { ...initialSessionState("s1", "claude"), status: "running" } } }));
    rerender(<SessionView session={SESSION} />);
    expect(screen.getByRole("textbox", { name: "Prompt" })).toHaveAttribute("placeholder", "Send another message — it goes next");
  });
});
