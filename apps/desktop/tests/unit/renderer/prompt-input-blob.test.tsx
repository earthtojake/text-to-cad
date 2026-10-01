import { act, render, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { Composer } from "@renderer/features/session/Composer";
import { useComposer } from "@renderer/state/composer";
import { useProjects } from "@renderer/state/projects";

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn(), dismiss: vi.fn(), info: vi.fn() } }));

// The composer's editor is ProseMirror, which measures the selection; jsdom lays nothing out.
const noRects = () => Object.assign([], { item: () => null }) as unknown as DOMRectList;
Range.prototype.getClientRects ??= noRects;
Range.prototype.getBoundingClientRect ??= () => new DOMRect();
(Text.prototype as unknown as { getClientRects: () => DOMRectList }).getClientRects ??= noRects;

/**
 * The stock AI Elements form fetched each attachment's `blob:` URL on submit to make a data URL
 * of it. The renderer's CSP refuses that fetch (`connect-src`), so every send with an attachment
 * logged a CSP violation and got nothing for it: the bytes come from the File behind the
 * attachment (`composer/attachments.ts`). No fetch is made.
 */
const fetch = vi.fn(async () => new Response("png"));

beforeEach(() => {
  fetch.mockClear();
  vi.stubGlobal("fetch", fetch);
  URL.createObjectURL ??= () => "blob:prompt-input";
  URL.revokeObjectURL ??= () => {};
  useProjects.setState({ projects: [{ id: "p", name: "p", path: "/p", createdAt: 0 }], activeId: "p" });
  useComposer.setState({ drafts: {}, annotations: {}, pendingFiles: {}, queues: {}, sending: {}, paused: {}, submitRequest: null });
});

afterEach(() => {
  vi.unstubAllGlobals();
});

it("sends an attachment without fetching its blob: URL", async () => {
  const onSubmit = vi.fn(async () => undefined);
  const view = render(<Composer chips={null} commands={[]} onSubmit={onSubmit} sessionId="s1" status="ready" />);
  act(() => useComposer.getState().attachFile("s1", new File(["png"], "bracket.png", { type: "image/png" })));
  await waitFor(() => expect(view.getByText("bracket.png")).toBeInTheDocument());
  act(() => useComposer.getState().requestSubmit("s1"));

  await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
  expect(fetch).not.toHaveBeenCalled();
});
