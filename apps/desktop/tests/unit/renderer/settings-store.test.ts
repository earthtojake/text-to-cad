/**
 * The settings store's write path: a refused write is rolled back and said so,
 * and a reply older than the newest write does not undo it.
 */
import { beforeEach, expect, it, vi } from "vitest";
import { toast } from "sonner";

import { resetForTests, useSettings } from "@renderer/state/settings";
import { defaultSettings, type Settings } from "@shared/types";

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn(), dismiss: vi.fn(), info: vi.fn() } }));

beforeEach(() => {
  vi.clearAllMocks();
  resetForTests();
  useSettings.setState({ settings: defaultSettings(), ready: true });
});

it("puts the old value back and toasts when main refuses the write", async () => {
  vi.mocked(window.textToCad.settings.set).mockRejectedValue(new Error("disk is full"));
  await useSettings.getState().patch({ launchAtLogin: true });
  expect(useSettings.getState().settings?.launchAtLogin).toBe(false);
  expect(toast.error).toHaveBeenCalledWith(expect.any(String), { description: "disk is full" });
});

it("keeps a newer optimistic write when an older reply lands, and builds the next layout write from it", async () => {
  const replies: ((settings: Settings) => void)[] = [];
  vi.mocked(window.textToCad.settings.set).mockImplementation(
    () => new Promise<Settings>((resolve) => replies.push(resolve)),
  );
  const answer = (index: number, settings: Settings) => replies[index]?.(settings);
  const store = useSettings.getState();
  const a = store.patch({ theme: "dark" });
  const b = store.setLayout({ sidebarCollapsed: true });

  // Main answers A with the world as it was when A was applied: no collapse yet.
  answer(0, { ...defaultSettings(), theme: "dark" });
  await a;
  expect(useSettings.getState().settings?.layout.sidebarCollapsed).toBe(true);

  const c = useSettings.getState().setLayout({ sidebarWidth: 300 });
  expect(vi.mocked(window.textToCad.settings.set).mock.calls[2]?.[0]).toEqual({
    layout: { sidebarWidth: 300, sidebarCollapsed: true },
  });

  const final = { ...defaultSettings(), theme: "dark" as const, layout: { sidebarWidth: 300, sidebarCollapsed: true } };
  answer(1, { ...final, layout: { ...final.layout, sidebarWidth: defaultSettings().layout.sidebarWidth } });
  answer(2, final);
  await Promise.all([b, c]);
  expect(useSettings.getState().settings).toEqual(final);
});
