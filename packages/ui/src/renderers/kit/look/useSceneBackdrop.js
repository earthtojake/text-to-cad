import { useMemo } from "react";
import { resolveSceneSettings } from "@text-to-cad/core/common/sceneSettings.js";
import { sceneBackdropEdgeColor } from "./chromeBackdrop.js";
import { useChromeBackdropColor } from "./useChromeBackdropColor.js";

/**
 * The viewport's own solid colour for a colour scheme — what an empty stage and a model with no
 * Display settings of its own are drawn on — and the default scene it comes from. It is the scene
 * theme's background, resolved exactly as the viewport resolves it, so a page drawn on it (the
 * host's home) and the viewport it opens into are one colour, in light and in dark.
 *
 * @param {"light" | "dark"} colorScheme
 * @returns {{ backdrop: string, scene: ReturnType<typeof resolveSceneSettings> }}
 */
export function useSceneBackdrop(colorScheme) {
  const prefersDark = colorScheme === "dark";
  const chromeBackdropColor = useChromeBackdropColor(prefersDark);
  const scene = useMemo(() => resolveSceneSettings({ appearance: prefersDark ? "dark" : "light", prefersDark }), [prefersDark]);
  return { backdrop: sceneBackdropEdgeColor(scene.theme.background, chromeBackdropColor), scene };
}
