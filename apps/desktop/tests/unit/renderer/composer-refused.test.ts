import { act, render, waitFor } from "@testing-library/react";
import { createElement } from "react";
import { toast } from "sonner";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { Composer } from "@renderer/features/session/Composer";
import { useAcp } from "@renderer/state/acp";
import { useComposer } from "@renderer/state/composer";
import { useProjects } from "@renderer/state/projects";
import type { PromptBlock } from "@shared/acp/types";
import { initialSessionState } from "@shared/acp/types";
import type { Project } from "@shared/types";

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn(), dismiss: vi.fn(), info: vi.fn() } }));

// The composer's editor is ProseMirror, which measures the selection; jsdom lays nothing out.
const noRects = () => Object.assign([], { item: () => null }) as unknown as DOMRectList;
Range.prototype.getClientRects ??= noRects;
Range.prototype.getBoundingClientRect ??= () => new DOMRect();
(Text.prototype as unknown as { getClientRects: () => DOMRectList }).getClientRects ??= noRects;

/**
 * A prompt holding a block the agent did not say it takes (`promptCapabilities`) is refused by
 * main before any turn begins — `refused` on the reply. That is not a failed turn: the session is
 * not in error, there is no Retry to be refused again and no Reconnect to fix nothing, and what the
 * person wrote is not spent. The box keeps it and the reason is said, the way `refuseSend` does.
 */
const SESSION = "s1";
const REASON = "Claude Code cannot take an image in a prompt. Remove the attachment to send.";
const P: Project = { id: "p", name: "p", path: "/p", createdAt: 0 };
const bridge = window.textToCad as unknown as Record<string, unknown>;
const saved = { sessions: bridge.sessions };
let prompt: ReturnType<typeof vi.fn>;

beforeEach(() => {
  vi.mocked(toast.info).mockClear();
  prompt = vi.fn(async () => ({ stopReason: "refused", refused: REASON }));
  bridge.sessions = { ...(saved.sessions as object), prompt };
  useProjects.setState({ projects: [P], activeId: P.id });
  useAcp.setState({ sessions: { [SESSION]: { ...initialSessionState(SESSION, "claude-code"), status: "idle" } }, loadErrors: {}, reconnecting: {} });
  useComposer.setState({ drafts: {}, annotations: {}, acceptedContexts: {}, referenceLabels: {}, pendingFiles: {}, draftRoots: {}, queues: {}, sending: {}, paused: {}, submitRequest: null });
});

afterEach(() => {
  bridge.sessions = saved.sessions;
});

it("keeps the draft and says why, with no error, Retry or Reconnect", async () => {
  const submit = (text: string, content: PromptBlock[], draft: Parameters<ReturnType<typeof useComposer.getState>["submit"]>[3]) =>
    useComposer.getState().submit(SESSION, text, content, draft);
  render(createElement(Composer, { sessionId: SESSION, chips: null, commands: [], status: "ready", onSubmit: submit }));
  useComposer.getState().setDraft(SESSION, "look at this bracket");
  act(() => useComposer.getState().requestSubmit(SESSION));

  await waitFor(() => expect(prompt).toHaveBeenCalledTimes(1));
  await waitFor(() => expect(useComposer.getState().drafts[SESSION]).toBe("look at this bracket"));
  expect(toast.info).toHaveBeenCalledWith(REASON);
  expect(useAcp.getState().sessions[SESSION]?.status).toBe("idle");
  expect(useAcp.getState().loadErrors[SESSION]).toBeUndefined();
  expect(useComposer.getState().paused[SESSION]).toBeUndefined();
  expect(useComposer.getState().sending[SESSION]).toBeUndefined();
});

it("puts a refused queued prompt back in the box and sends on what was queued behind it", async () => {
  const image: PromptBlock = { type: "image", data: "AAAA", mimeType: "image/png", uri: null };
  prompt.mockImplementationOnce(async () => ({ stopReason: "refused", refused: REASON }))
    .mockImplementationOnce(async () => ({ stopReason: "end_turn" }));
  const composer = useComposer.getState();
  composer.enqueue(SESSION, "look", [{ type: "text", text: "look" }, image], { text: "look", annotations: [] });
  composer.enqueue(SESSION, "then this", [{ type: "text", text: "then this" }]);
  await composer.drain(SESSION);

  await waitFor(() => expect(prompt).toHaveBeenCalledTimes(2));
  expect(toast.info).toHaveBeenCalledWith(REASON);
  expect(useComposer.getState().drafts[SESSION]).toBe("look");
  expect(useComposer.getState().queues[SESSION]).toEqual([]);
  expect(useComposer.getState().paused[SESSION]).toBeUndefined();
  expect(useAcp.getState().loadErrors[SESSION]).toBeUndefined();
});

it("hands the box's attachments over with the draft, for a refusal that comes back after the box has gone", async () => {
  URL.createObjectURL ??= () => "blob:composer-refused";
  URL.revokeObjectURL ??= () => {};
  const onSubmit = vi.fn(async () => undefined);
  const photo = new File(["png"], "bracket.png", { type: "image/png" });
  const view = render(createElement(Composer, { sessionId: SESSION, chips: null, commands: [], status: "ready", onSubmit }));
  act(() => useComposer.getState().attachFile(SESSION, photo));
  await waitFor(() => expect(view.getByText("bracket.png")).toBeInTheDocument());
  useComposer.getState().setDraft(SESSION, "look at this");
  act(() => useComposer.getState().requestSubmit(SESSION));

  await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
  expect(onSubmit).toHaveBeenCalledWith("look at this", expect.anything(), expect.objectContaining({ text: "look at this", files: [photo] }));
});

it("puts the draft back and says why when main refuses a direct send before any turn", async () => {
  // Closed, nothing queued: the prompt goes straight out (the reconnect is main's `ensureLive`), and
  // main refuses it before a turn event — the agent is not installed, its folder is gone. The
  // transcript never saw it, so the box has to keep it and the reason has to be shown somewhere.
  useAcp.setState({ sessions: { [SESSION]: { ...initialSessionState(SESSION, "claude-code"), status: "closed" } } });
  prompt.mockImplementation(async () => { throw new Error("Claude Code is not installed"); });
  const submit = (text: string, content: PromptBlock[], draft: Parameters<ReturnType<typeof useComposer.getState>["submit"]>[3]) =>
    useComposer.getState().submit(SESSION, text, content, draft);
  render(createElement(Composer, { sessionId: SESSION, chips: null, commands: [], status: "ready", onSubmit: submit }));
  useComposer.getState().setDraft(SESSION, "make the bracket thicker");
  act(() => useComposer.getState().requestSubmit(SESSION));

  await waitFor(() => expect(prompt).toHaveBeenCalledTimes(1));
  await waitFor(() => expect(useComposer.getState().drafts[SESSION]).toBe("make the bracket thicker"));
  expect(useAcp.getState().loadErrors[SESSION]).toBe("Claude Code is not installed");
  expect(useComposer.getState().sending[SESSION]).toBeUndefined();
});

it("puts refused queued prompts back in the order they were queued, a Retry's with no draft included", async () => {
  const composer = useComposer.getState();
  composer.enqueue(SESSION, "first", [{ type: "text", text: "first" }], { text: "first", annotations: [] });
  composer.enqueue(SESSION, "second", [{ type: "text", text: "second" }], { text: "second", annotations: [] });
  // The transcript's Retry, queued behind a running turn: the prompt it resends, with no draft.
  composer.enqueue(SESSION, "again", [{ type: "text", text: "again" }]);
  await composer.drain(SESSION);

  await waitFor(() => expect(prompt).toHaveBeenCalledTimes(3));
  await waitFor(() => expect(useComposer.getState().drafts[SESSION]).toBe("first\n\nsecond\n\nagain"));
  expect(useComposer.getState().queues[SESSION]).toEqual([]);
});

const submitFromBox = (text: string, content: PromptBlock[], draft: Parameters<ReturnType<typeof useComposer.getState>["submit"]>[3]) =>
  useComposer.getState().submit(SESSION, text, content, draft);

it("empties the attachment strip when the message is accepted, not when its turn ends", async () => {
  URL.createObjectURL ??= () => "blob:composer-attachments";
  URL.revokeObjectURL ??= () => {};
  // The turn never ends in this test: `prompt` is a reply that arrives at the end of the turn.
  prompt.mockImplementation(() => new Promise(() => {}));
  const photo = new File(["png"], "bracket.png", { type: "image/png" });
  const view = render(createElement(Composer, { sessionId: SESSION, chips: null, commands: [], status: "ready", onSubmit: submitFromBox }));
  act(() => useComposer.getState().attachFile(SESSION, photo));
  await waitFor(() => expect(view.getByText("bracket.png")).toBeInTheDocument());
  useComposer.getState().setDraft(SESSION, "look at this");
  act(() => useComposer.getState().requestSubmit(SESSION));

  await waitFor(() => expect(prompt).toHaveBeenCalledTimes(1));
  await waitFor(() => expect(view.queryByText("bracket.png")).toBeNull());

  // A message typed meanwhile is queued behind the turn and carries no file.
  useComposer.getState().setDraft(SESSION, "and thicker");
  act(() => useComposer.getState().requestSubmit(SESSION));
  await waitFor(() => expect(useComposer.getState().queues[SESSION]).toHaveLength(1));
  const queued = useComposer.getState().queues[SESSION]![0]!;
  expect(queued.content.map((block) => block.type)).toEqual(["text"]);
  expect(queued.draft?.files).toBeUndefined();
});

it("puts the attachments back in the strip when the message it emptied it for is refused", async () => {
  URL.createObjectURL ??= () => "blob:composer-attachments";
  URL.revokeObjectURL ??= () => {};
  const photo = new File(["png"], "bracket.png", { type: "image/png" });
  const view = render(createElement(Composer, { sessionId: SESSION, chips: null, commands: [], status: "ready", onSubmit: submitFromBox }));
  act(() => useComposer.getState().attachFile(SESSION, photo));
  await waitFor(() => expect(view.getByText("bracket.png")).toBeInTheDocument());
  useComposer.getState().setDraft(SESSION, "look at this");
  act(() => useComposer.getState().requestSubmit(SESSION));

  // `prompt` answers `refused` (the default in `beforeEach`): the text and the photo come back.
  await waitFor(() => expect(useComposer.getState().drafts[SESSION]).toBe("look at this"));
  await waitFor(() => expect(view.getByText("bracket.png")).toBeInTheDocument());
});
