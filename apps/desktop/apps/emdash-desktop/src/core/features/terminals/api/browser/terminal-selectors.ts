import { terminalRegistry } from '@core/features/terminals/api/browser/stores/terminal-registry';

export function getTerminalsForTask(taskId: string) {
  return terminalRegistry.get(taskId);
}
