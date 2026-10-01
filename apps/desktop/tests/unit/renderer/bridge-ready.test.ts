import { afterEach, expect, it, vi } from "vitest";

import { subscribeToMain } from "@renderer/state/bridge";
import { useUi } from "@renderer/state/ui";

/**
 * A command the menu sent to a window it opened is held in main until the page
 * is listening (`takeQueuedCommands` in src/main/menu.ts): the page asks for
 * it once its `ui.command` listener is attached, and runs it like a pushed one.
 */

const bridge = window.textToCad as unknown as Record<string, unknown>;
const saved = { on: bridge.on, ui: bridge.ui };
let detach = () => {};

afterEach(() => {
  detach();
  Object.assign(bridge, saved);
  useUi.getState().closeSettings();
});

it("asks main for the commands held for it after attaching its listener, and runs them", async () => {
  const order: string[] = [];
  bridge.on = vi.fn((channel: string) => { order.push(`on ${channel}`); return () => {}; });
  bridge.ui = { ready: vi.fn(async () => { order.push("ready"); return [{ command: "open-settings" }]; }) };
  detach = subscribeToMain();
  await vi.waitFor(() => expect(useUi.getState().route).toBe("settings"));
  expect(order.indexOf("ready")).toBeGreaterThan(order.indexOf("on ui.command"));
});
