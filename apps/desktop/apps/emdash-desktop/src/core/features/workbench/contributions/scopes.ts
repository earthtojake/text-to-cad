import { z } from 'zod';
import type { CommandDef } from '@core/primitives/commands/api';
import { defineViewScope } from '@core/primitives/view-scopes/api';
import {
  closeModalCommand,
  closeTerminalSearchCommand,
  confirmCommand,
  findInTerminalCommand,
  PANE_COMMAND_DEFS,
  saveAllEditorsCommand,
  saveEditorCommand,
  WINDOW_COMMAND_DEFS,
} from './commands';

/**
 * The manifest composition root supplies commands owned by other slices. This
 * keeps feature contribution modules from importing each other.
 */
export function defineWindowScope<const TAdditional extends readonly CommandDef[]>(
  additionalCommands: TAdditional
) {
  return defineViewScope({
    id: 'window',
    params: z.object({}),
    commands: [...WINDOW_COMMAND_DEFS, ...additionalCommands] as const,
    activation: 'logical',
  });
}

export const modalScope = defineViewScope({
  id: 'modal',
  params: z.object({}),
  commands: [closeModalCommand, confirmCommand] as const,
  activation: 'focus',
  traits: ['capturing'],
});

export const paneScope = defineViewScope({
  id: 'workbench.pane',
  params: z.object({ paneId: z.string() }),
  commands: PANE_COMMAND_DEFS,
  activation: 'focus',
  key: ({ paneId }) => paneId,
});

export const editorScope = defineViewScope({
  id: 'workbench.editor',
  params: z.object({ paneId: z.string() }),
  commands: [saveEditorCommand, saveAllEditorsCommand] as const,
  activation: 'focus',
  traits: ['text-input', 'editor'],
  key: ({ paneId }) => paneId,
});

export const terminalInputScope = defineViewScope({
  id: 'workbench.terminal',
  params: z.object({ sessionId: z.string() }),
  commands: [findInTerminalCommand] as const,
  activation: 'focus',
  traits: ['text-input', 'terminal'],
  key: ({ sessionId }) => sessionId,
});

export const terminalSearchScope = defineViewScope({
  id: 'workbench.terminalSearch',
  params: z.object({ sessionId: z.string() }),
  commands: [findInTerminalCommand, closeTerminalSearchCommand] as const,
  activation: 'focus',
  traits: ['text-input'],
  key: ({ sessionId }) => sessionId,
});
