import { fireEvent, render } from "@testing-library/react";
import { expect, it, vi } from "vitest";

import { ComposerEditor } from "@renderer/features/session/composer/ComposerEditor";

const noRects = () => Object.assign([], { item: () => null }) as unknown as DOMRectList;
Range.prototype.getClientRects ??= noRects;
Range.prototype.getBoundingClientRect ??= () => new DOMRect();
(Text.prototype as unknown as { getClientRects: () => DOMRectList }).getClientRects ??= noRects;

async function mount() {
  const onChange = vi.fn();
  const onSubmit = vi.fn();
  const { container } = render(<ComposerEditor onChange={onChange} onSubmit={onSubmit} placeholder="Do anything" value="ab" />);
  const input = await vi.waitFor(() => {
    const found = container.querySelector<HTMLElement>("[data-composer-input]");
    if (!found) throw new Error("no editor yet");
    return found;
  });
  input.focus();
  return { input, onChange, onSubmit };
}

/** The shortcuts table says Enter sends and Shift+Enter breaks the line; no other Enter chord does either. */
it("Shift+Enter breaks the line", async () => {
  const { input, onSubmit } = await mount();
  fireEvent.keyDown(input, { key: "Enter", code: "Enter", shiftKey: true });
  await vi.waitFor(() => expect(input.querySelector("br:not(.ProseMirror-trailingBreak)")).not.toBeNull());
  expect(onSubmit).not.toHaveBeenCalled();
});

it.each([
  ["Cmd+Enter", { metaKey: true }],
  ["Ctrl+Enter", { ctrlKey: true }],
])("%s does not insert a line break (it is not in the shortcuts table)", async (_name, modifiers) => {
  const { input } = await mount();
  fireEvent.keyDown(input, { key: "Enter", code: "Enter", ...modifiers });
  expect(input.querySelector("br:not(.ProseMirror-trailingBreak)"), "the chord inserted a hard break").toBeNull();
});
