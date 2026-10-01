import { act, fireEvent, render, waitFor } from "@testing-library/react";
import { createElement } from "react";
import { beforeEach, expect, it, vi } from "vitest";

import { Composer } from "@renderer/features/session/Composer";
import { forgetRememberedFiles, rememberedFileCount } from "@renderer/features/session/composer/attachments";
import { useComposer } from "@renderer/state/composer";
import { useProjects } from "@renderer/state/projects";
import type { PromptBlock } from "@shared/acp/types";

/**
 * The files behind the composer's attachments (`composer/attachments.ts`) belong to the attachment
 * they were added as — not to a file name. Chromium names every pasted image `image.png`, so a
 * registry keyed by name hands one session's paste to another's send.
 */

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn(), dismiss: vi.fn(), info: vi.fn() } }));

const noRects = () => Object.assign([], { item: () => null }) as unknown as DOMRectList;
Range.prototype.getClientRects ??= noRects;
Range.prototype.getBoundingClientRect ??= () => new DOMRect();
(Text.prototype as unknown as { getClientRects: () => DOMRectList }).getClientRects ??= noRects;

// A blob URL per attachment, as Chromium mints them; jsdom has none, and the fetch of one fails as
// it does on `file://`, so the bytes come from the registry.
let minted = 0;
URL.createObjectURL = () => `blob:composer-test/${++minted}`;
URL.revokeObjectURL = () => {};

beforeEach(() => {
  forgetRememberedFiles();
  useComposer.setState({ drafts: {}, annotations: {}, acceptedContexts: {}, referenceLabels: {}, pendingFiles: {}, draftRoots: {}, queues: {}, sending: {} });
  useProjects.setState({ projects: [{ id: "p", name: "p", path: "/p", createdAt: 0 }], activeId: "p" });
});

type Submit = (text: string, content: PromptBlock[]) => Promise<void>;

function composer(draftKey: string, onSubmit: Submit = vi.fn(async () => undefined)) {
  const view = render(createElement(Composer, { sessionId: null, newDraftKey: draftKey, chips: null, commands: [], status: "ready", onSubmit }));
  const input = view.container.querySelector<HTMLInputElement>("[data-attach-input]")!;
  return {
    ...view,
    onSubmit: onSubmit as ReturnType<typeof vi.fn>,
    pick: async (...files: File[]) => {
      Object.defineProperty(input, "files", { configurable: true, value: files });
      await act(async () => fireEvent.change(input));
      await waitFor(() => expect(view.container.querySelectorAll("[data-composer] [title='image.png']").length).toBeGreaterThan(0));
    },
    remove: () => act(async () => fireEvent.click(view.container.querySelector("[aria-label='Remove']")!)),
    send: () => act(async () => fireEvent.submit(view.container.querySelector("form")!)),
  };
}

const pasted = (text: string) => new File([text], "image.png", { type: "image/png" });
const sentImages = (onSubmit: ReturnType<typeof vi.fn>, call: number) =>
  (onSubmit.mock.calls[call]![1] as PromptBlock[]).filter((block) => block.type === "image").map((block) => atob((block as { data: string }).data));

it("an image pasted in one session and not sent is not what another session's same-named paste sends", async () => {
  const a = composer("a");
  await a.pick(pasted("from A"));
  const b = composer("b");
  await b.pick(pasted("from B"));
  await b.send();
  await waitFor(() => expect(b.onSubmit).toHaveBeenCalledTimes(1));
  expect(sentImages(b.onSubmit, 0)).toEqual(["from B"]);
});

it("an attachment removed from the box is not sent in place of a same-named one added after it", async () => {
  const view = composer("a");
  await view.pick(pasted("removed"));
  await view.remove();
  await view.pick(pasted("kept"));
  await view.send();
  await waitFor(() => expect(view.onSubmit).toHaveBeenCalledTimes(1));
  expect(sentImages(view.onSubmit, 0)).toEqual(["kept"]);
});

it("a send that is rejected keeps the files, so the retry sends them", async () => {
  const onSubmit = vi.fn<Submit>().mockRejectedValueOnce(new Error("no")).mockResolvedValue(undefined);
  const view = composer("a", onSubmit);
  await view.pick(pasted("retried"));
  await view.send();
  await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
  // The refusal puts the file back once the rejection lands; a retry sent before
  // that would carry nothing, so wait for the chip the way a person sees it.
  await waitFor(() => expect(view.container.querySelector("[aria-label='Remove']")).not.toBeNull());
  await view.send();
  await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(2));
  expect(sentImages(onSubmit, 1)).toEqual(["retried"]);
});

it("holds a file only while its attachment is in a box: sent, removed or unmounted, it is let go", async () => {
  const sent = composer("sent");
  await sent.pick(pasted("sent"));
  await sent.send();
  await waitFor(() => expect(sent.onSubmit).toHaveBeenCalledTimes(1));
  const removed = composer("removed");
  await removed.pick(pasted("removed"));
  await removed.remove();
  const closed = composer("closed");
  await closed.pick(pasted("closed"));
  closed.unmount();
  await waitFor(() => expect(rememberedFileCount()).toBe(0));
});
