import { z } from 'zod';
import { defineViewScope } from '@core/primitives/view-scopes/api';
import { EDITOR_FILE_TREE_COMMAND_DEFS } from './commands';

export const fileTreeScope = defineViewScope({
  id: 'editor.fileTree',
  params: z.object({
    workspaceId: z.string().min(1),
  }),
  commands: EDITOR_FILE_TREE_COMMAND_DEFS,
  activation: 'focus',
  key: ({ workspaceId }) => workspaceId,
});
