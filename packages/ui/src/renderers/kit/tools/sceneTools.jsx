import { useRef, useState } from "react";
import { sceneFramingBounds } from "@text-to-cad/core/lib/viewer/sceneContract.js";
import { boundsInUnits } from "@text-to-cad/core/lib/viewer/sceneUnits.js";
import { useModelTools } from "./model-effects/ModelTools.jsx";
import { useMeasureSession } from "./measure/useMeasureSession.js";
import { MeasurementsBar } from "./measure/measurementChips.jsx";
import { measureSelectHandlers } from "./measure/measureSelection.js";
import { MeasureIcon, SCENE_MEASURE_TOOL, SceneMeasureOverlay } from "./measure/SceneMeasure.jsx";
import { TOOL_SHORTCUTS } from "./toolShortcuts.js";
import { useI18n } from "@text-to-cad/ui/i18n";

// The tools a scene the kit draws offers, in two halves around the shell: what Quick Edit must know
// before the shell is made (the tool in hand, Measure's session), and the strip, the row under it
// and the layer over the view, made from the shell. Which of them a file has is its renderer's:
// Select is the renderer's own, Pencil and Shapes the shell's, Measure where the file says its unit, and the
// model effects where its view's features offer them (`model-effects/ModelTools.jsx`).

/**
 * The first half: the tool in hand (never saved; a file opens in its default), and Measure's session
 * where the file can be measured.
 *
 * @param {{ toolModes: ReturnType<typeof import("./toolModes.js").createToolModes>, previewing: boolean,
 *   fileKey: string, revision: string, measurable: boolean, resource: object }} options
 */
export function useSceneToolState({ toolModes, previewing, fileKey, revision, measurable, resource }) {
  const [mode, set] = useState(toolModes.defaultMode);
  const measure = useMeasureSession({ fileKey, revision, picking: measurable && !previewing && mode === SCENE_MEASURE_TOOL });
  return { tool: { mode, set }, measure, measuring: measurable && !previewing && mode === SCENE_MEASURE_TOOL };
}

/**
 * The second half: the strip's tools after Select (Pencil, Shapes, Measure, the model effects), the tool in
 * hand's row under the strip, Measure's layer over the view, and Select's press and hover on a
 * measurement.
 *
 * @param {{ shell: ReturnType<typeof import("../shell/useRendererShell.js").useRendererShell>, scene: object | null,
 *   features: import("@text-to-cad/core/common/viewSettings.js").ViewFeatures,
 *   state: ReturnType<typeof useSceneToolState>, measurable: boolean, clearParts?: () => void }} options
 *   `features`: the view's, as the shell was given them: a model effect is offered where they list it.
 */
export function useSceneTools({ shell, scene, features, state, measurable, clearParts = () => {} }) {
  const { t } = useI18n();
  const { measure, measuring } = state;
  // A measurement taken, deleted or cleared is a step of the view's one history, with the ink's.
  measure.history.current = shell.frame.history;
  const { view, store } = shell.viewSettings;
  // Clip's slider maps in the box the camera frames, in the file's unit, as `clip.at` is.
  const bounds = scene ? boundsInUnits(sceneFramingBounds(scene), scene.units) : null;
  const effects = useModelTools({ view, features, store, mesh: bounds ? { bounds } : null, disabled: shell.idle });
  const tools = [
    ...shell.tools.drawing.map(tool => ({ ...tool, disabled: shell.idle })),
    measurable ? shell.tools.own({ id: SCENE_MEASURE_TOOL, label: t("tool.measure"), shortcut: TOOL_SHORTCUTS.measure, icon: <MeasureIcon className="size-3.5" aria-hidden="true" />,
      // A mesh has no vertices, edges or faces to filter: two points on its surface, so no menu.
      onSelect: () => { if (shell.toolMode !== SCENE_MEASURE_TOOL) shell.selectTool(SCENE_MEASURE_TOOL); } }) : null,
    ...effects.tools
  ].filter(Boolean);
  // Measure's row under the strip: its measurements, as chips, while there are any.
  const subToolbar = measuring ? <MeasurementsBar measure={measure} /> : null;
  const runtime = useRef(null);
  const overlay = viewport => {
    runtime.current = viewport.runtimeRef;
    return measurable ? <SceneMeasureOverlay viewport={viewport} scene={scene} measure={measure} picking={measuring} preview={shell.previewing} /> : null;
  };
  const select = measureSelectHandlers(measure, () => runtime.current?.current, clearParts, { picks: measurable });
  return { tools, subToolbar, overlay, onSelectPress: select.press, onSelectHover: select.hover };
}
