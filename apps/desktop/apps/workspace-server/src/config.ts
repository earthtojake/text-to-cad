import { type Result } from '@emdash/shared';
import { formatConfigError, parseConfig, type ConfigError } from '@emdash/shared/config';
import { z } from 'zod';

const WORKSPACE_SERVER_ENV_PREFIX = 'EMDASH_WS_';
const DEFAULT_ENV_FILES = ['.env'];
const workspaceServerCommands = ['serve', 'start', 'stop', 'status'] as const;

export type WorkspaceServerCommand = (typeof workspaceServerCommands)[number];

export type WorkspaceServerConfig = {
  command: WorkspaceServerCommand;
  appVersion: string;
  serve: { kind: 'stdio' } | { kind: 'socket'; path: string | undefined };
};

export const workspaceServerRawConfigSchema = z
  .object({
    command: z.enum(workspaceServerCommands).default('serve'),
    mode: z.enum(['stdio', 'socket']).optional(),
    socketPath: z.string().trim().min(1, 'Socket path cannot be empty').optional(),
    appVersion: z.string().trim().min(1, 'App version cannot be empty').default('0.0.0'),
  })
  .transform((config): WorkspaceServerConfig => {
    const mode = config.mode ?? (config.socketPath === undefined ? 'stdio' : 'socket');

    return {
      command: config.command,
      appVersion: config.appVersion,
      serve:
        mode === 'socket'
          ? ({
              kind: 'socket',
              path: config.socketPath,
            } satisfies WorkspaceServerConfig['serve'])
          : ({ kind: 'stdio' } satisfies WorkspaceServerConfig['serve']),
    };
  });

export type WorkspaceServerConfigError = ConfigError;

export function loadWorkspaceServerConfig(
  argv = process.argv.slice(2),
  env: NodeJS.ProcessEnv = process.env,
  envFiles: readonly string[] = DEFAULT_ENV_FILES
): Result<WorkspaceServerConfig, WorkspaceServerConfigError> {
  const command = parseCommand(argv);
  if (!command.success) return command;

  const parsed = parseConfig({
    schema: workspaceServerRawConfigSchema,
    argv: command.data.argv,
    env,
    envFiles,
    envPrefix: WORKSPACE_SERVER_ENV_PREFIX,
    defaults: {
      command: command.data.command,
      mode: command.data.command === 'serve' ? undefined : 'socket',
      appVersion: nonEmpty(env['npm_package_version']),
    },
    args: {
      options: {
        stdio: {
          type: 'boolean',
          key: false,
          whenPresent: { mode: 'stdio' },
          group: 'serve',
        },
        socket: {
          type: 'string',
          key: 'socketPath',
          optionalValue: true,
          whenPresent: { mode: 'socket' },
          group: 'serve',
        },
        'socket-path': {
          type: 'string',
          key: 'socketPath',
          whenPresent: { mode: 'socket' },
          group: 'serve',
        },
      },
    },
  });

  if (!parsed.success) return parsed;
  if (parsed.data.command !== 'serve' && parsed.data.serve.kind !== 'socket') {
    return {
      success: false,
      error: {
        type: 'args',
        message: `${parsed.data.command} only supports socket mode`,
      },
    };
  }

  return parsed;
}

export function formatWorkspaceServerConfigError(error: WorkspaceServerConfigError): string {
  return formatConfigError(error).replace('Invalid config', 'Invalid workspace-server config');
}

function nonEmpty(value: string | undefined): string | undefined {
  return value === undefined || value.length === 0 ? undefined : value;
}

function parseCommand(
  argv: string[]
): Result<{ command: WorkspaceServerCommand; argv: string[] }, WorkspaceServerConfigError> {
  const [first, ...rest] = argv;
  if (first === undefined || first.startsWith('--')) {
    return { success: true, data: { command: 'serve', argv } };
  }
  if (isWorkspaceServerCommand(first)) {
    return { success: true, data: { command: first, argv: rest } };
  }
  return {
    success: false,
    error: {
      type: 'args',
      message: `Unknown command '${first}'`,
    },
  };
}

function isWorkspaceServerCommand(value: string): value is WorkspaceServerCommand {
  return (workspaceServerCommands as readonly string[]).includes(value);
}
