import { mkdtemp, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';
import { z } from 'zod';
import { parseConfig } from './index';

const testConfigSchema = z.object({
  mode: z.enum(['stdio', 'socket']).default('stdio'),
  socketPath: z.string().optional(),
  appVersion: z.string().default('0.0.0'),
});

describe('parseConfig', () => {
  it('validates schema defaults when no sources are present', () => {
    const config = expectParsed(
      parseConfig({
        schema: testConfigSchema,
        argv: [],
        env: {},
      })
    );

    expect(config).toEqual({
      mode: 'stdio',
      appVersion: '0.0.0',
    });
  });

  it('layers defaults, env files, env, and args in precedence order', async () => {
    const envFile = await writeTempEnvFile(`
EMDASH_TEST_APP_VERSION=from-file
EMDASH_TEST_SOCKET_PATH=/tmp/from-file.sock
`);

    const config = expectParsed(
      parseConfig({
        schema: testConfigSchema,
        argv: ['--socket-path', '/tmp/from-args.sock'],
        env: {
          EMDASH_TEST_APP_VERSION: 'from-env',
        },
        envFiles: [envFile],
        envPrefix: 'EMDASH_TEST_',
        defaults: {
          appVersion: 'from-defaults',
        },
        args: {
          options: {
            'socket-path': {
              type: 'string',
              key: 'socketPath',
              whenPresent: { mode: 'socket' },
            },
          },
        },
      })
    );

    expect(config).toEqual({
      mode: 'socket',
      socketPath: '/tmp/from-args.sock',
      appVersion: 'from-env',
    });
  });

  it('supports optional-value string flags', () => {
    const config = expectParsed(
      parseConfig({
        schema: testConfigSchema,
        argv: ['--socket'],
        env: {},
        args: {
          options: {
            socket: {
              type: 'string',
              key: 'socketPath',
              optionalValue: true,
              whenPresent: { mode: 'socket' },
            },
          },
        },
      })
    );

    expect(config).toEqual({
      mode: 'socket',
      appVersion: '0.0.0',
    });
  });

  it('reports options from the same exclusive group', () => {
    const result = parseConfig({
      schema: testConfigSchema,
      argv: ['--stdio', '--socket'],
      env: {},
      args: {
        options: {
          stdio: { type: 'boolean', key: false, whenPresent: { mode: 'stdio' }, group: 'serve' },
          socket: { type: 'string', optionalValue: true, group: 'serve' },
        },
      },
    });

    expect(result).toMatchObject({
      success: false,
      error: {
        type: 'args',
        message: 'Use either --stdio or --socket, not both',
      },
    });
  });

  it('ignores missing env files', () => {
    const config = expectParsed(
      parseConfig({
        schema: testConfigSchema,
        argv: [],
        env: {},
        envFiles: ['/path/to/missing/.env'],
      })
    );

    expect(config.mode).toBe('stdio');
  });
});

async function writeTempEnvFile(contents: string): Promise<string> {
  const dir = await mkdtemp(join(tmpdir(), 'emdash-config-'));
  const path = join(dir, '.env');
  await writeFile(path, contents);
  return path;
}

function expectParsed<T, E>(result: { success: true; data: T } | { success: false; error: E }): T {
  if (!result.success) throw new Error(`Expected config to parse: ${String(result.error)}`);
  return result.data;
}
