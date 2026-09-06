import { fileTreeScope } from '@core/features/editor/contributions/scopes';
import { settingsScope } from '@core/features/settings/contributions/scopes';
import { taskListScope, taskViewScope } from '@core/features/tasks/contributions/scopes';
import {
  defineWindowScope,
  editorScope,
  modalScope,
  paneScope,
  terminalInputScope,
  terminalSearchScope,
} from '@core/features/workbench/contributions/scopes';
import { COMMAND_CATALOG } from '../shared/command-catalog';

export const windowScope = defineWindowScope([]);

export const SCOPE_CATALOG = [
  windowScope,
  taskViewScope,
  fileTreeScope,
  modalScope,
  settingsScope,
  paneScope,
  editorScope,
  terminalInputScope,
  terminalSearchScope,
  taskListScope,
] as const;

const catalogCommands = new Set(COMMAND_CATALOG.defs);
for (const scope of SCOPE_CATALOG) {
  const unknownCommands = scope.commands.filter((command) => !catalogCommands.has(command));
  if (unknownCommands.length > 0) {
    throw new Error(
      `View scope ${scope.id} declares commands outside COMMAND_CATALOG: ${unknownCommands
        .map((command) => command.id)
        .join(', ')}`
    );
  }
}

export type ViewScopeId = (typeof SCOPE_CATALOG)[number]['id'];
