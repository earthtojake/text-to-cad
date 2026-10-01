import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { toast } from "sonner";
import { expect, it, vi } from "vitest";

import { Toaster } from "@renderer/components/ui/sonner";

vi.mock("@renderer/lib/platform", async (importOriginal) => ({ ...(await importOriginal<object>()), isMac: false }));

async function shown() {
  render(<Toaster />);
  act(() => void toast("Saved"));
  await waitFor(() => expect(document.querySelector("ol[data-sonner-toaster]")).not.toBeNull());
  return document.querySelector<HTMLElement>("ol[data-sonner-toaster]")!;
}

/**
 * Sonner's stock hotkey for "focus the toasts" is Alt+T, and Option+T types a dagger on a Mac
 * keyboard: it fired in the middle of a sentence and took the caret away. Off a Mac the chord
 * is Ctrl+Shift+T: Ctrl+Alt+T is GNOME's terminal, and AltGr arrives as Ctrl+Alt.
 */
it("does not take focus on Alt+T, which types a character, only on the chord", async () => {
  const list = await shown();

  fireEvent.keyDown(document, { key: "†", code: "KeyT", altKey: true });
  expect(list).not.toHaveFocus();

  fireEvent.keyDown(document, { key: "t", code: "KeyT", altKey: true, ctrlKey: true });
  expect(list).not.toHaveFocus();

  fireEvent.keyDown(document, { key: "T", code: "KeyT", shiftKey: true, ctrlKey: true });
  expect(list).toHaveFocus();
});

it("names the notifications region without the hotkey's key names", async () => {
  await shown();
  expect(screen.getByRole("region", { name: "Notifications" })).toBeInTheDocument();
});
