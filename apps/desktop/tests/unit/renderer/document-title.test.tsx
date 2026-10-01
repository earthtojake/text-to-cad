import { render } from "@testing-library/react";
import { act } from "react";
import { beforeEach, expect, it, vi } from "vitest";

import { App } from "@renderer/app/App";
import { useOnboarding } from "@renderer/state/onboarding";
import { useSessions } from "@renderer/state/sessions";
import { useSettings } from "@renderer/state/settings";
import { useUi } from "@renderer/state/ui";
import { defaultSettings, type Session } from "@shared/types";

/** The window's title says where you are: nothing set it before, so every route was "text-to-cad". */
// Counts Shell's renders: App renders it unmemoised, so every App render is one of these.
let renders = 0;
vi.mock("@renderer/app/Shell", () => ({ Shell: () => { renders += 1; return null; } }));
vi.mock("@renderer/app/CommandPalette", () => ({ CommandPalette: () => null }));
vi.mock("@renderer/features/onboarding/Welcome", () => ({ Welcome: () => null }));
vi.mock("@renderer/features/settings/SettingsRoute", () => ({ SettingsRoute: () => null }));
vi.mock("@renderer/components/ui/sonner", () => ({ Toaster: () => null }));
vi.mock("@renderer/state/bridge", () => ({ hydrate: vi.fn(async () => undefined), subscribeToMain: () => () => undefined }));

const BRACKET = { id: "s1", projectId: "p", agentId: "codex", cwd: "/p", title: "Bracket", status: "idle", archived: false } as unknown as Session;

beforeEach(() => {
  document.title = "text-to-cad";
  useUi.setState({ route: "app" });
  useOnboarding.setState({ enabled: false });
  useSessions.setState({ sessions: [], activeId: null });
  useSettings.setState({ settings: { ...defaultSettings(), onboardingCompleted: true }, ready: true } as never);
});

it("names the settings route", () => {
  useUi.setState({ route: "settings" });
  render(<App />);
  expect(document.title).toBe("text-to-cad — Settings");
});

it("names the welcome", () => {
  useOnboarding.setState({ enabled: true });
  useSettings.setState({ settings: { ...defaultSettings(), onboardingCompleted: false }, ready: true } as never);
  render(<App />);
  expect(document.title).toBe("text-to-cad — Welcome");
});

it("names the active session, and is plain with none", () => {
  render(<App />);
  expect(document.title).toBe("text-to-cad");
  act(() => useSessions.setState({ sessions: [BRACKET], activeId: "s1" }));
  expect(document.title).toBe("text-to-cad — Bracket");
  act(() => useSessions.setState({ activeId: null }));
  expect(document.title).toBe("text-to-cad");
});

it("does not re-render the window when the active session changes but its title does not", () => {
  renders = 0;
  act(() => useSessions.setState({ sessions: [BRACKET], activeId: "s1" }));
  render(<App />);
  const before = renders;
  expect(before).toBeGreaterThan(0);
  act(() => useSessions.setState({ sessions: [{ ...BRACKET, status: "running" }] }));
  expect(renders).toBe(before);
});
