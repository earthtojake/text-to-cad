import type { Terminal } from '@xterm/xterm';

// xterm's proposed API and internal fields are not in the public TypeScript
// types. Both code paths are necessary: the proposed `dimensions` API works in
// xterm 5.x, while xterm 6.x exposes cell metrics only via `_core`.
interface XtermCellDimensions {
  css: { cell: { width: number; height: number } };
}

interface XtermInternals {
  dimensions?: XtermCellDimensions;
  _core?: {
    _renderService?: { dimensions?: XtermCellDimensions };
    renderService?: { dimensions?: XtermCellDimensions };
  };
}

export function getCellMetrics(terminal: Terminal): { width: number; height: number } | null {
  const t = terminal as unknown as XtermInternals;
  const dims = t.dimensions;
  if (dims && dims.css.cell.width !== 0 && dims.css.cell.height !== 0) {
    return { width: dims.css.cell.width, height: dims.css.cell.height };
  }

  const coreDims = t._core?._renderService?.dimensions ?? t._core?.renderService?.dimensions;
  if (coreDims?.css?.cell?.width && coreDims.css.cell.height) {
    return { width: coreDims.css.cell.width, height: coreDims.css.cell.height };
  }
  return null;
}
