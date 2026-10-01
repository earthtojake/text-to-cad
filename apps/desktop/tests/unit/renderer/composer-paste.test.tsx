import { describe, expect, it, vi } from "vitest";
import { render } from "@testing-library/react";
import { toast } from "sonner";

import { ComposerEditor } from "@renderer/features/session/composer/ComposerEditor";
import { attachmentRefusal, MAX_INLINE_TEXT_BYTES } from "@renderer/features/session/composer/attachments";

vi.mock("sonner", () => ({ toast: { error: vi.fn(), info: vi.fn(), success: vi.fn() } }));

/** A paste as ProseMirror reads one: the event, with the clipboard's plain text on it. */
function paste(target: Element, text: string) {
  const event = new Event("paste", { bubbles: true, cancelable: true });
  Object.defineProperty(event, "clipboardData", {
    value: { items: [], files: [], types: ["text/plain"], getData: (type: string) => (type === "text/plain" ? text : "") },
  });
  target.dispatchEvent(event);
}

describe("pasting into the composer", () => {
  /**
   * A text file past 256 KB is refused as an attachment; the same text
   * pasted is the same prompt, so it is refused the same way rather than
   * becoming a quarter-megabyte draft.
   */
  it("refuses text larger than an attached text file may be", async () => {
    const onChange = vi.fn();
    const { container } = render(<ComposerEditor onChange={onChange} onSubmit={() => {}} placeholder="Do anything" value="" />);
    const input = await vi.waitFor(() => {
      const found = container.querySelector("[data-composer-input]");
      if (!found) throw new Error("no editor yet");
      return found;
    });

    onChange.mockClear();
    paste(input, "x".repeat(MAX_INLINE_TEXT_BYTES + 1));
    expect(onChange).not.toHaveBeenCalled();
    expect(toast.error).toHaveBeenCalledWith(attachmentRefusal.pasteTooLarge());

    paste(input, "a short note");
    expect(onChange).toHaveBeenLastCalledWith("a short note");
  });
});
