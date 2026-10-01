import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { TooltipProvider } from "@text-to-cad/ui/primitives/tooltip";
import { PermissionCard } from "@renderer/features/session/parts/PermissionCard";
import { SessionView } from "@renderer/features/session/SessionView";
import { useAcp } from "@renderer/state/acp";
import { useComposer } from "@renderer/state/composer";
import { useProjects } from "@renderer/state/projects";
import { initialSessionState } from "@shared/acp/types";
import type { PermissionRequestPart } from "@shared/acp/types";
import type { Project, Session } from "@shared/types";

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn(), dismiss: vi.fn(), info: vi.fn() } }));
vi.mock("@renderer/features/session/SessionHeader", () => ({ SessionHeader: () => null }));
vi.mock("@renderer/features/session/ContextMeter", () => ({ ContextMeter: () => null }));
const PART: PermissionRequestPart = {
  type: "permission_request",
  requestId: "perm-1",
  toolCallId: "cmd-1",
  title: "Run ls?",
  description: null,
  options: [{ optionId: "allow-once", name: "Allow", kind: "allow_once", description: null }],
  outcome: { state: "pending" },
};
// The real composer beside a real card: the card is what the transcript draws, the box is the point.
vi.mock("@renderer/features/session/Transcript", () => ({ Transcript: () => <PermissionCard part={PART} sessionId="s1" /> }));

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
    sessions: { s1: { ...initialSessionState("s1", "claude"), status: "running" } },
    loading: {},
    reconnecting: {},
    loadErrors: {},
    ensureLoaded: vi.fn(async () => undefined),
  } as never);
  useComposer.setState({ drafts: {}, queues: {}, sending: {}, paused: {}, submitRequest: null, focusRequest: null });
});

describe("answering a permission card", () => {
  // The answered card is replaced by its folded line, and the button that was pressed went with it:
  // focus fell to the page and the next key reached nothing. It goes to the composer's box instead.
  it("hands focus to the composer, not the page", async () => {
    const user = userEvent.setup();
    (window.textToCad.sessions as unknown as { respondPermission: unknown }).respondPermission = vi.fn(async () => undefined);
    render(<TooltipProvider><SessionView session={SESSION} /></TooltipProvider>);
    await user.click(screen.getByRole("button", { name: "Allow" }));
    await vi.waitFor(() => expect(document.activeElement).toBe(screen.getByRole("textbox")));
  });
});
