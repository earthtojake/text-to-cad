import { RotateCcw } from "lucide-react";
import { Button } from "@hardcore/ui/primitives/button";
import { FILE_SHEET_COMPACT_BUTTON_CLASSES } from "./FileSheet.js";
import PoseControlsSection, { poseControlsHaveContent } from "./PoseControlsSection.js";
import { FILE_SHEET_SECTION_IDS } from "../../workbench/fileSheetSections.js";

// Motion is Position. Animation is the Animate tool and its playbar, not an
// Inspector section, so a file with routines and no joints has no Motion tab.
// One host command still resets all motion, including pending playback and pose frames.
export function buildMotionControlsTab({ poseRuntime = null, animationRuntime = null, poseProps = {} } = {}) {
  const hasPosition = poseControlsHaveContent(poseRuntime, poseProps);
  if (!hasPosition) return null;
  const onReset = poseRuntime?.onResetMotion || animationRuntime?.resetModel || poseRuntime?.onResetParameters;
  return {
    id: FILE_SHEET_SECTION_IDS.MOTION,
    title: "Motion",
    content: (
      <div>
        <PoseControlsSection {...poseProps} runtime={poseRuntime} />
        <MotionResetButton onReset={onReset} />
      </div>
    ),
  };
}

export function MotionResetButton({ onReset }) {
  if (!onReset) return null;
  return <div className="px-2 py-2">
    <Button variant="outline" size="sm" className={`${FILE_SHEET_COMPACT_BUTTON_CLASSES} w-full justify-center`}
      onClick={onReset} title="Reset animation and position">
      <RotateCcw className="h-3.5 w-3.5" aria-hidden="true" />Reset
    </Button>
  </div>;
}
