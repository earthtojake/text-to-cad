import { Redo2, Trash2, Undo2 } from "lucide-react";
import { cn } from "@hardcore/ui/utils";
import { ScrollArea } from "@hardcore/ui/primitives/scroll-area";
import { TooltipProvider } from "@hardcore/ui/primitives/tooltip";
import ToolbarShell from "./ToolbarShell.js";
import { ToolbarButton } from "./ToolbarButton.js";

export default function DrawingToolbar({
  className,
  layout = "wrap",
  drawingToolOptions,
  drawingTool,
  handleSelectDrawingTool,
  handleUndoDrawing,
  handleRedoDrawing,
  handleClearDrawings,
  canUndoDrawing,
  canRedoDrawing,
  drawingStrokes
}) {
  const historyUndo = handleUndoDrawing;
  const historyRedo = handleRedoDrawing;
  const clearAction = handleClearDrawings;
  const canUndo = canUndoDrawing;
  const canRedo = canRedoDrawing;
  const actionCount = drawingStrokes.length;
  const scrollLayout = layout === "scroll";
  const toolbarButtons = (
    <div
      className={cn(
        "flex gap-1",
        scrollLayout ? "w-max min-w-full flex-nowrap" : "flex-wrap"
      )}
    >
      {drawingToolOptions.map(({ id, label, Icon }) => {
        const active = drawingTool === id;
        return (
          <ToolbarButton
            key={id}
            label={label}
            active={active}
            aria-pressed={active}
            onClick={() => handleSelectDrawingTool(id)}
          >
            <Icon className="size-3.5" strokeWidth={2} aria-hidden="true" />
          </ToolbarButton>
        );
      })}

      <ToolbarButton
        label="Undo"
        onClick={historyUndo}
        disabled={!canUndo}
      >
        <Undo2 className="size-3.5" strokeWidth={2} aria-hidden="true" />
      </ToolbarButton>

      <ToolbarButton
        label="Redo"
        onClick={historyRedo}
        disabled={!canRedo}
      >
        <Redo2 className="size-3.5" strokeWidth={2} aria-hidden="true" />
      </ToolbarButton>

      <ToolbarButton
        label="Clear all"
        onClick={clearAction}
        disabled={!actionCount}
      >
        <Trash2 className="size-3.5" strokeWidth={2} aria-hidden="true" />
      </ToolbarButton>
    </div>
  );

  return (
    <ToolbarShell className={cn("p-1.5", className)}>
      <TooltipProvider delayDuration={250}>
        {scrollLayout ? (
          <ScrollArea
            className="min-w-0 max-w-full"
            type="auto"
            scrollbars="horizontal"
          >
            {toolbarButtons}
          </ScrollArea>
        ) : toolbarButtons}
      </TooltipProvider>
    </ToolbarShell>
  );
}
