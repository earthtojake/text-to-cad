import type { TerminalDrawerActiveItem } from '@core/features/tasks/contributions/mementos';

export function resolveTerminalPanelActiveItem({
  requestedActiveItem,
  activeTerminalId,
  terminalIds,
  scriptIds,
}: {
  requestedActiveItem: TerminalDrawerActiveItem | undefined;
  activeTerminalId: string | undefined;
  terminalIds: readonly string[];
  scriptIds: readonly string[];
}): TerminalDrawerActiveItem {
  if (requestedActiveItem?.kind === 'terminal' && terminalIds.includes(requestedActiveItem.id)) {
    return requestedActiveItem;
  }

  if (requestedActiveItem?.kind === 'script' && scriptIds.includes(requestedActiveItem.id)) {
    return requestedActiveItem;
  }

  if (activeTerminalId && terminalIds.includes(activeTerminalId)) {
    return { kind: 'terminal', id: activeTerminalId };
  }

  const firstScriptId = scriptIds[0];
  if (firstScriptId) {
    return { kind: 'script', id: firstScriptId };
  }

  return { kind: 'terminal', id: terminalIds[0] ?? '' };
}
