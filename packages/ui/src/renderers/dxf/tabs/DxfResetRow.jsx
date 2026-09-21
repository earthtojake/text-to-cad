import { RotateCcw } from "lucide-react";
import { Button } from "@hardcore/ui/primitives/button";
import { FILE_SHEET_COMPACT_BUTTON_CLASSES, FileSheetControlRow } from "../../kit/inspector/FileSheet.js";

/** The tab-footer Reset (settings-ui.md: outline + RotateCcw, full row, one per tab). */
export function DxfResetRow({ label, onReset }) {
  if (!onReset) return null;
  return (
    <FileSheetControlRow label={null}>
      <Button
        type="button"
        variant="outline"
        size="sm"
        className={`${FILE_SHEET_COMPACT_BUTTON_CLASSES} w-full justify-center`}
        onClick={() => onReset()}
        aria-label={label}
        title="Reset"
      >
        <RotateCcw className="h-3.5 w-3.5" strokeWidth={2} aria-hidden="true" />
        <span>Reset</span>
      </Button>
    </FileSheetControlRow>
  );
}
