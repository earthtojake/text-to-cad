import { render } from "@testing-library/react";
import { createElement, type ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { App } from "@renderer/app/App";
import { Shimmer } from "@renderer/components/ai-elements/shimmer";
import { useSettings } from "@renderer/state/settings";
import { defaultSettings } from "@shared/types";

const sources = import.meta.glob("../../../src/renderer/**/*.{ts,tsx}", { query: "?raw", import: "default", eager: true }) as Record<string, string>;

/**
 * "Reduce motion" (Settings › Appearance) has to reach the JS animations too: the `.reduce-motion`
 * class in globals.css only slows CSS ones, and the shimmer's infinite sweep is motion's.
 */
const seen = vi.hoisted(() => ({
  config: [] as Array<string | undefined>,
  shimmer: [] as Array<Record<string, unknown>>,
}));

vi.mock("motion/react", async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown> & { MotionConfig: never }>();
  return {
    ...actual,
    // The real provider, recorded; the real hook reads it.
    MotionConfig: (props: { reducedMotion?: string; children: ReactNode }) => {
      seen.config.push(props.reducedMotion);
      return createElement(actual.MotionConfig, props as never);
    },
    motion: {
      create: (element: string) => (props: Record<string, unknown>) => {
        seen.shimmer.push(props);
        return createElement(element);
      },
    },
  };
});
vi.mock("@renderer/app/Shell", () => ({ Shell: () => null }));
vi.mock("@renderer/app/CommandPalette", () => ({ CommandPalette: () => null }));
vi.mock("@renderer/features/onboarding/Welcome", () => ({ Welcome: () => null }));
vi.mock("@renderer/features/settings/SettingsRoute", () => ({ SettingsRoute: () => null }));
vi.mock("@renderer/components/ui/sonner", () => ({ Toaster: () => null }));
vi.mock("@renderer/state/bridge", () => ({ hydrate: vi.fn(async () => undefined), subscribeToMain: () => () => undefined }));

afterEach(() => {
  seen.config.length = 0;
  seen.shimmer.length = 0;
});

describe("reduced motion reaches motion/react", () => {
  it("App wraps the window in a MotionConfig driven by the setting, the OS as fallback", () => {
    useSettings.setState({ settings: { ...defaultSettings(), reduceMotion: true } });
    render(<App />);
    expect(seen.config.at(-1)).toBe("always");

    seen.config.length = 0;
    useSettings.setState({ settings: { ...defaultSettings(), reduceMotion: false } });
    render(<App />);
    expect(seen.config.at(-1)).toBe("user");
  });

  it("the shimmer starts no animation under reducedMotion=always, and sweeps otherwise", async () => {
    const { MotionConfig } = await import("motion/react");
    render(
      <MotionConfig reducedMotion="always">
        <Shimmer>Thinking</Shimmer>
      </MotionConfig>,
    );
    expect(seen.shimmer.at(-1)?.animate).toBeUndefined();
    expect(seen.shimmer.at(-1)?.transition).toBeUndefined();

    render(
      <MotionConfig reducedMotion="never">
        <Shimmer>Thinking</Shimmer>
      </MotionConfig>,
    );
    expect(seen.shimmer.at(-1)?.animate).toEqual({ backgroundPosition: "0% center" });
    expect((seen.shimmer.at(-1)?.transition as { repeat: number }).repeat).toBe(Number.POSITIVE_INFINITY);
  });

  it("only shimmer.tsx imports motion/react, and App is the one place that configures it", () => {
    const importers = Object.entries(sources)
      .filter(([, source]) => /from "motion\/react"/.test(source))
      .map(([path]) => path.replace(/^.*\/src\/renderer\//, ""));
    // A new importer animates under App's MotionConfig only if it reads the config too: add it here
    // after checking that it does (`useReducedMotionConfig`), not before.
    expect(importers.sort()).toEqual(["app/App.tsx", "components/ai-elements/shimmer.tsx"]);
  });
});
