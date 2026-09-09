export const TERMINAL_DRAWER_DRAG_TYPE = 'task-terminal-drawer-terminal';

export interface TerminalDrawerDragData {
  type: typeof TERMINAL_DRAWER_DRAG_TYPE;
  terminalId: string;
  label: string;
}

export function isTerminalDrawerDragData(value: unknown): value is TerminalDrawerDragData {
  if (!value || typeof value !== 'object') return false;
  const data = value as Partial<TerminalDrawerDragData>;
  return (
    data.type === TERMINAL_DRAWER_DRAG_TYPE &&
    typeof data.terminalId === 'string' &&
    typeof data.label === 'string'
  );
}
