import { Redo2, Trash2, Undo2 } from "lucide-react";
import ToolbarShell, { TOOLBAR_MENU_ROW_CLASS } from "./ToolbarShell.js";
import SelectionFilterMenu from "./SelectionFilterMenu.jsx";

export default function DrawingToolbar({
  className,
  drawingToolOptions,
  drawingTool,
  handleSelectDrawingTool,
  handleUndoDrawing,
  handleRedoDrawing,
  handleClearDrawings,
  canUndoDrawing,
  canRedoDrawing,
  drawingStrokes,
  onClose
}) {
  const currentTool = drawingToolOptions.find(option => option.id === drawingTool);
  return (
    <ToolbarShell className={className} title="Draw" onClose={onClose} closeLabel="Finish drawing">
      <div className="py-1">
        <p className="px-2 py-1 text-micro text-muted-foreground">Tool</p>
        <SelectionFilterMenu fullWidth options={drawingToolOptions} value={drawingTool}
          onChange={handleSelectDrawingTool} menuLabel="Drawing tool" hint="" triggerIcon={currentTool?.Icon} />
      </div>
      <div className="-mx-1 my-1 h-px shrink-0 bg-border" />
      <button type="button" className={TOOLBAR_MENU_ROW_CLASS} onClick={handleUndoDrawing} disabled={!canUndoDrawing}>
        <Undo2 className="size-3.5 text-muted-foreground" aria-hidden="true" />Undo
      </button>
      <button type="button" className={TOOLBAR_MENU_ROW_CLASS} onClick={handleRedoDrawing} disabled={!canRedoDrawing}>
        <Redo2 className="size-3.5 text-muted-foreground" aria-hidden="true" />Redo
      </button>
      <button type="button" className={TOOLBAR_MENU_ROW_CLASS} onClick={handleClearDrawings} disabled={!drawingStrokes.length}>
        <Trash2 className="size-3.5 text-muted-foreground" aria-hidden="true" />Clear all
      </button>
    </ToolbarShell>
  );
}
