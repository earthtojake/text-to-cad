import { act, render, waitFor } from "@testing-library/react";
import { createElement } from "react";
import { beforeEach, expect, it, vi } from "vitest";

import { Composer } from "@renderer/features/session/Composer";
import { newSessionKey, useComposer } from "@renderer/state/composer";
import { useProjects } from "@renderer/state/projects";
import type { Project } from "@shared/types";

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn(), dismiss: vi.fn(), info: vi.fn() } }));

// The composer's editor is ProseMirror, which measures the selection; jsdom lays nothing out.
const noRects = () => Object.assign([], { item: () => null }) as unknown as DOMRectList;
Range.prototype.getClientRects ??= noRects;
Range.prototype.getBoundingClientRect ??= () => new DOMRect();
(Text.prototype as unknown as { getClientRects: () => DOMRectList }).getClientRects ??= noRects;

/**
 * A send asked for from outside (New session's Try again) is handled once, by the composer that
 * was on screen when it was asked. The request is keyed by the project's new-session draft, so a
 * composer for that key mounting again later — New session for another project and back, or a
 * remount after the retry — must not read it as a fresh request and send whatever the box holds.
 */
const A: Project = { id: "a", name: "a", path: "/a", createdAt: 0 };
const B: Project = { id: "b", name: "b", path: "/b", createdAt: 0 };

beforeEach(() => {
  useComposer.setState({ drafts: {}, annotations: {}, acceptedContexts: {}, referenceLabels: {}, pendingFiles: {}, draftRoots: {}, queues: {}, sending: {}, submitRequest: null });
  useProjects.setState({ projects: [A, B], activeId: A.id });
});

const mount = (project: Project, onSubmit: () => Promise<void>) =>
  render(createElement(Composer, { sessionId: null, newDraftKey: newSessionKey(project.id), chips: null, commands: [], status: "ready", onSubmit }));

it("sends once for a request; a remount of the same key does not send again", async () => {
  const onSubmit = vi.fn(async () => undefined);
  useComposer.getState().setDraft(newSessionKey(A.id), "make a cube");
  const first = mount(A, onSubmit);
  act(() => useComposer.getState().requestSubmit(newSessionKey(A.id)));
  await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
  expect(useComposer.getState().submitRequest, "the request is consumed").toBeNull();
  first.unmount();

  useComposer.getState().setDraft(newSessionKey(A.id), "something typed later");
  mount(A, onSubmit);
  await act(async () => { await Promise.resolve(); });
  expect(onSubmit).toHaveBeenCalledTimes(1);
});

it("New session for A, then B, then A again does not send A's draft", async () => {
  // NewSession stays mounted across projects: the same composer gets a new draft key.
  const onSubmit = vi.fn(async () => undefined);
  const props = (project: Project) => ({ sessionId: null, newDraftKey: newSessionKey(project.id), chips: null, commands: [], status: "ready" as const, onSubmit });
  useComposer.getState().setDraft(newSessionKey(A.id), "make a cube");
  const view = render(createElement(Composer, props(A)));
  act(() => useComposer.getState().requestSubmit(newSessionKey(A.id)));
  await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
  view.rerender(createElement(Composer, props(B)));
  await act(async () => { await Promise.resolve(); });
  useComposer.getState().setDraft(newSessionKey(A.id), "left in the box");
  view.rerender(createElement(Composer, props(A)));
  await act(async () => { await new Promise(resolve => setTimeout(resolve, 20)); });
  expect(onSubmit).toHaveBeenCalledTimes(1);
});

it("a request left over from before the composer mounted is not sent", async () => {
  const onSubmit = vi.fn(async () => undefined);
  // Forced: an unhandled request still in the store when the composer arrives.
  useComposer.setState({ submitRequest: { key: newSessionKey(A.id), nonce: 999_999 } });
  useComposer.getState().setDraft(newSessionKey(A.id), "left in the box");
  mount(A, onSubmit);
  await act(async () => { await Promise.resolve(); });
  expect(onSubmit).not.toHaveBeenCalled();
});

it("a send the caller refuses says why and leaves the draft in the box", async () => {
  const { toast } = await import("sonner");
  const onSubmit = vi.fn(async () => undefined);
  useComposer.getState().setDraft(newSessionKey(A.id), "make a cube");
  const view = render(createElement(Composer, { sessionId: null, newDraftKey: newSessionKey(A.id), chips: null, commands: [], status: "ready", onSubmit, refuseSend: "No agent ready — sign in to one first" }));
  const send = view.getByRole("button", { name: "Submit" });
  expect(send).toHaveAttribute("aria-disabled", "true");
  expect(send).toHaveAccessibleDescription("No agent ready — sign in to one first");
  act(() => useComposer.getState().requestSubmit(newSessionKey(A.id)));
  await waitFor(() => expect(toast.info).toHaveBeenCalledWith("No agent ready — sign in to one first"));
  expect(onSubmit).not.toHaveBeenCalled();
  expect(useComposer.getState().drafts[newSessionKey(A.id)]).toBe("make a cube");
});
