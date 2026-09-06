import { join } from 'node:path';
import { createFileSessionIntentStore } from '@emdash/core/services/session-intents/node';
import { app } from 'electron';

export type SessionIntentFilePaths = {
  acp: string;
  tuiAgents: string;
};

export function sessionIntentFilePaths(): SessionIntentFilePaths {
  const userData = app?.getPath?.('userData') ?? process.cwd();
  return {
    acp: join(userData, 'acp-session-intents.json'),
    tuiAgents: join(userData, 'tui-session-intents.json'),
  };
}

export function createDesktopSessionIntentStores() {
  const paths = sessionIntentFilePaths();
  return {
    acp: createFileSessionIntentStore({ path: paths.acp, scope: 'acp' }),
    tuiAgents: createFileSessionIntentStore({
      path: paths.tuiAgents,
      scope: 'tui-agents',
    }),
  };
}
