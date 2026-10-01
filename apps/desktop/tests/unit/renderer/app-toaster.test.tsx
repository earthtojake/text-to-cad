import { render } from "@testing-library/react";
import { expect, it, vi } from "vitest";

import { App } from "@renderer/app/App";

// The one element under test is the toaster; the routes around it are their own suites.
const toaster = vi.hoisted(() => ({ props: null as Record<string, unknown> | null }));
vi.mock("@renderer/components/ui/sonner", () => ({
  Toaster: (props: Record<string, unknown>) => {
    toaster.props = props;
    return null;
  },
}));
vi.mock("@renderer/app/Shell", () => ({ Shell: () => null }));
vi.mock("@renderer/app/CommandPalette", () => ({ CommandPalette: () => null }));
vi.mock("@renderer/features/onboarding/Welcome", () => ({ Welcome: () => null }));
vi.mock("@renderer/features/settings/SettingsRoute", () => ({ SettingsRoute: () => null }));
vi.mock("@renderer/state/bridge", () => ({ hydrate: vi.fn(async () => undefined), subscribeToMain: () => () => undefined }));

it("puts toasts at the top right, under the title strip, clear of the composer at the bottom", () => {
  render(<App />);
  expect(toaster.props?.position).toBe("top-right");
  expect(toaster.props?.offset).toEqual({ top: "calc(var(--titlebar-height) + 8px)", right: 16 });
});
