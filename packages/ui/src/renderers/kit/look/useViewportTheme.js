import { useCallback, useMemo } from "react";
import { normalizeViewportBackground, resolveViewportTheme } from "@cad/core/lib/viewportTheme.js";

/**
 * The viewport's theme, live: what the model area is drawn in, apart from the app's chrome
 * (`@cad/core/lib/viewportTheme.js`). The person's Background (the tab's settings,
 * `viewportBackground`: Light by default, or Dark), whatever the app's light or dark. A stored value
 * of the old Follow theme ("theme") reads as Light.
 *
 * `{ background, scheme, canvas, gradient, setBackground }`: a view draws its scene in `scheme`, on
 * `canvas` (a 3D view's background `gradient`, top to bottom, where there is one), and hands
 * `ViewFrame` the theme so what it draws over the picture (labels, chips, the cube, the corner's
 * bare buttons) takes it too; `setBackground` is Display's Background.
 *
 * @param {{ viewportBackground?: string } | null | undefined} preferences  The tab's settings.
 * @param {((patch: object) => void) | null | undefined} onPreferenceChange
 */
export function useViewportTheme(preferences, onPreferenceChange = null) {
  const background = normalizeViewportBackground(preferences?.viewportBackground);
  const setBackground = useCallback(value => onPreferenceChange?.({ viewportBackground: normalizeViewportBackground(value) }), [onPreferenceChange]);
  return useMemo(() => ({ ...resolveViewportTheme(background), setBackground }), [background, setBackground]);
}

/** Display's Background, as its card's group takes it (`DisplaySettings.jsx`): the choice and its change. */
export function viewportBackgroundControl(viewport) {
  return viewport?.setBackground ? { value: viewport.background, onChange: viewport.setBackground } : null;
}
