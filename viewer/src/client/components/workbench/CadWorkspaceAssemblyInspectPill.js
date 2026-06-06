import { ChevronLeft, X } from "lucide-react";
import { Button } from "../ui/button";

export default function CadWorkspaceAssemblyInspectPill({
  previewMode,
  inspectedAssemblyPart,
  canGoBack = false,
  toolbarHeight,
  onExit
}) {
  const partLabel = String(
    inspectedAssemblyPart?.name ||
    inspectedAssemblyPart?.label ||
    inspectedAssemblyPart?.id ||
    ""
  ).trim();

  if (previewMode || !partLabel) {
    return null;
  }

  return (
    <div
      className="pointer-events-none absolute inset-x-0 z-20 flex justify-center px-4"
      style={{ top: `${toolbarHeight + 14}px` }}
    >
      <Button
        type="button"
        variant="outline"
        size="sm"
        className="cad-glass-popover pointer-events-auto max-w-[min(32rem,calc(100vw-6rem))] rounded-full px-3 py-1.5 text-[12px] font-medium text-popover-foreground shadow-sm"
        onClick={onExit}
        aria-label={canGoBack ? `Back to parent assembly from ${partLabel}` : `Exit focus for ${partLabel}`}
        title={canGoBack ? `Back to parent assembly from ${partLabel}` : `Exit focus for ${partLabel}`}
      >
        <span className="inline-flex h-5 w-5 items-center justify-center rounded-full bg-[var(--ui-panel-muted)] text-[var(--ui-text-faint)]">
          {canGoBack ? (
            <ChevronLeft className="h-3 w-3" strokeWidth={2.1} aria-hidden="true" />
          ) : (
            <X className="h-3 w-3" strokeWidth={2.1} aria-hidden="true" />
          )}
        </span>
        <span className="truncate">{partLabel}</span>
      </Button>
    </div>
  );
}
