import { err, ok } from '@emdash/shared';
import { describe, expect, it, vi } from 'vitest';
import type { ProjectProvider } from '@core/features/projects/api/node/project-provider';
import { nativePathFromHost } from '@core/primitives/desktop-runtime/api';
import { filesClientScope } from '@core/services/runtime-broker/node/files';
import {
  inspectProjectConfigMigrations,
  migrateProjectConfigFromProvider as migrateProjectConfigFromProviderWithWriter,
} from './config-migration';

vi.mock('@emdash/shared/logger', () => ({
  log: {
    warn: vi.fn(),
  },
}));

const repoPath = '/repo';

function createFs(initialFiles: Record<string, string>) {
  const files = new Map(
    Object.entries(initialFiles).map(([filePath, content]) => [
      filePath.startsWith('/') ? filePath : `${repoPath}/${filePath}`,
      content,
    ])
  );
  const exists = vi.fn((filePath: string) => Promise.resolve(ok({ exists: files.has(filePath) })));
  const readText = vi.fn((filePath: string) => {
    const content = files.get(filePath);
    if (content === undefined) {
      return Promise.resolve(
        err({
          type: 'not-found' as const,
          path: filePath,
        })
      );
    }
    return Promise.resolve(
      ok({
        content,
        truncated: false,
        totalSize: Buffer.byteLength(content),
        etag: 'test-etag',
      })
    );
  });
  const writeText = vi.fn((filePath: string, content: string) => {
    files.set(filePath, content);
    return Promise.resolve(ok({ bytesWritten: Buffer.byteLength(content) }));
  });
  type AbsoluteKey = { path: Parameters<typeof nativePathFromHost>[0] };
  const scope = filesClientScope(
    {
      fs: {
        exists: ({ path }: AbsoluteKey) => exists(nativePathFromHost(path)),
        readText: ({ path }: AbsoluteKey) => readText(nativePathFromHost(path)),
        writeFile: ({ path, content }: AbsoluteKey & { content: string }) =>
          writeText(nativePathFromHost(path), content).then((result) =>
            result.success ? ok(undefined) : result
          ),
      },
    } as never,
    repoPath
  );
  return Object.assign(scope, {
    exists,
    readText,
    writeText,
    content(filePath: string) {
      return files.get(filePath) ?? files.get(`${repoPath}/${filePath}`);
    },
  });
}

function createProject(files: ReturnType<typeof createFs>, settings: Record<string, unknown> = {}) {
  const join = (...parts: string[]) => parts.join('/').replace(/\/+/g, '/');
  return {
    repoPath,
    files,
    projectConfigPath: join(repoPath, '.emdash.json'),
    resolveProjectPath: (relativePath: string) => join(repoPath, relativePath),
    configPathForDirectory: (directoryPath: string) => join(directoryPath, '.emdash.json'),
    settings,
  } as unknown as ProjectProvider;
}

async function migrateProjectConfigFromProvider(
  project: ReturnType<typeof createProject>,
  request: {
    provider: 'conductor' | 'superset' | 'paseo' | 'codex';
    destination: 'local' | 'shared';
  }
) {
  const settings = project.settings as {
    get?: () => Promise<Record<string, unknown>>;
    update?: (settings: Record<string, unknown>) => Promise<{ success: boolean }>;
    patch?: (patch: { clearShareableFields: string[] }) => Promise<{ success: boolean }>;
    patchPersonalConfig?: (patch: Record<string, unknown>) => Promise<{ success: boolean }>;
    clearPersonalFields?: (fields: string[]) => Promise<{ success: boolean }>;
  };
  return migrateProjectConfigFromProviderWithWriter(project, request, {
    patchPersonalConfig: async (patch) => {
      if (settings.patchPersonalConfig) {
        const result = await settings.patchPersonalConfig(patch);
        return result.success ? ok() : err({ type: 'error' as const });
      }
      const current = (await settings.get?.()) ?? {};
      const result = await settings.update?.({
        ...current,
        ...patch,
        ...(patch.scripts
          ? {
              scripts: {
                ...((current.scripts as Record<string, unknown> | undefined) ?? {}),
                ...patch.scripts,
              },
            }
          : {}),
      });
      return result?.success !== false ? ok() : err({ type: 'error' as const });
    },
    clearPersonalFields: async (fields) => {
      const result = settings.clearPersonalFields
        ? await settings.clearPersonalFields(fields)
        : await settings.patch?.({ clearShareableFields: fields });
      return result?.success !== false ? ok() : err({ type: 'error' as const });
    },
  });
}

describe('config migration', () => {
  it('detects importable Conductor settings', async () => {
    const fs = createFs({
      'conductor.json': JSON.stringify({
        scripts: {
          setup: 'pnpm install',
          run: 'pnpm dev',
          archive: 'pnpm cleanup',
        },
        runScriptMode: 'nonconcurrent',
        enterpriseDataPrivacy: true,
      }),
      '.worktreeinclude': `
        # local env
        .env
        .env.local
        !*.example
      `,
    });

    await expect(inspectProjectConfigMigrations(createProject(fs))).resolves.toEqual([
      {
        provider: 'conductor',
        label: 'Conductor',
        files: ['conductor.json', '.worktreeinclude'],
        fields: ['scripts.setup', 'scripts.run', 'scripts.teardown', 'preservePatterns'],
        unsupportedFields: ['runScriptMode', 'enterpriseDataPrivacy'],
      },
    ]);
  });

  it('writes Conductor settings into .emdash.json', async () => {
    const fs = createFs({
      'conductor.json': JSON.stringify({
        scripts: {
          setup: 'pnpm install',
          run: 'pnpm dev',
          archive: 'pnpm cleanup',
        },
      }),
      '.worktreeinclude': '.env\n.env.local\n',
    });
    const patch = vi.fn().mockResolvedValue({ success: true });

    const result = await migrateProjectConfigFromProvider(createProject(fs, { patch }), {
      provider: 'conductor',
      destination: 'shared',
    });

    expect(result.success).toBe(true);
    expect(JSON.parse(fs.content('.emdash.json') ?? '{}')).toEqual({
      scripts: {
        setup: 'pnpm install',
        run: 'pnpm dev',
        teardown: 'pnpm cleanup',
      },
      preservePatterns: ['.env', '.env.local'],
    });
    expect(patch).toHaveBeenCalledWith({
      clearShareableFields: [
        'scripts.setup',
        'scripts.run',
        'scripts.teardown',
        'preservePatterns',
      ],
    });
  });

  it('does not import Conductor files to copy when .worktreeinclude is missing', async () => {
    const fs = createFs({
      'conductor.json': JSON.stringify({
        scripts: {
          setup: 'pnpm install',
        },
      }),
    });

    await expect(inspectProjectConfigMigrations(createProject(fs))).resolves.toEqual([
      {
        provider: 'conductor',
        label: 'Conductor',
        files: ['conductor.json'],
        fields: ['scripts.setup'],
        unsupportedFields: [],
      },
    ]);

    const patch = vi.fn().mockResolvedValue({ success: true });
    const result = await migrateProjectConfigFromProvider(createProject(fs, { patch }), {
      provider: 'conductor',
      destination: 'shared',
    });

    expect(result.success).toBe(true);
    expect(JSON.parse(fs.content('.emdash.json') ?? '{}')).toEqual({
      scripts: {
        setup: 'pnpm install',
      },
    });
    expect(patch).toHaveBeenCalledWith({
      clearShareableFields: ['scripts.setup'],
    });
  });

  it('imports Conductor settings into local project settings', async () => {
    const fs = createFs({
      'conductor.json': JSON.stringify({
        scripts: {
          run: 'pnpm dev',
        },
      }),
      '.worktreeinclude': '.env\n.env.local\n',
    });
    const patchPersonalConfig = vi.fn().mockResolvedValue({ success: true });

    const result = await migrateProjectConfigFromProvider(
      createProject(fs, {
        patchPersonalConfig,
      }),
      { provider: 'conductor', destination: 'local' }
    );

    expect(result.success).toBe(true);
    expect(fs.writeText).not.toHaveBeenCalled();
    expect(patchPersonalConfig).toHaveBeenCalledWith({
      scripts: {
        run: 'pnpm dev',
      },
      preservePatterns: ['.env', '.env.local'],
    });
  });

  it('detects importable Superset settings', async () => {
    const fs = createFs({
      '.superset/config.json': JSON.stringify({
        setup: ['bun install', 'cp "$SUPERSET_ROOT_PATH/.env" .env'],
        run: ['./.superset/run.sh'],
        teardown: ['docker-compose down'],
      }),
    });

    await expect(inspectProjectConfigMigrations(createProject(fs))).resolves.toEqual([
      {
        provider: 'superset',
        label: 'Superset',
        files: ['.superset/config.json'],
        fields: ['scripts.setup', 'scripts.run', 'scripts.teardown'],
        unsupportedFields: [],
      },
    ]);
  });

  it('writes Superset settings into .emdash.json', async () => {
    const fs = createFs({
      '.superset/config.json': JSON.stringify({
        setup: ['bun install', 'cp "$SUPERSET_ROOT_PATH/.env" .env'],
        run: ['./.superset/run.sh'],
        teardown: ['docker-compose down'],
      }),
    });
    const patch = vi.fn().mockResolvedValue({ success: true });

    const result = await migrateProjectConfigFromProvider(createProject(fs, { patch }), {
      provider: 'superset',
      destination: 'shared',
    });

    expect(result.success).toBe(true);
    expect(JSON.parse(fs.content('.emdash.json') ?? '{}')).toEqual({
      scripts: {
        setup: 'bun install\ncp "$SUPERSET_ROOT_PATH/.env" .env',
        run: './.superset/run.sh',
        teardown: 'docker-compose down',
      },
    });
    expect(patch).toHaveBeenCalledWith({
      clearShareableFields: ['scripts.setup', 'scripts.run', 'scripts.teardown'],
    });
  });

  it('imports Superset settings into local project settings', async () => {
    const fs = createFs({
      '.superset/config.json': JSON.stringify({
        run: ['./.superset/run.sh'],
      }),
    });
    const update = vi.fn().mockResolvedValue({ success: true });

    const result = await migrateProjectConfigFromProvider(
      createProject(fs, {
        get: vi.fn().mockResolvedValue({
          scripts: {
            setup: 'bun install',
          },
        }),
        update,
      }),
      { provider: 'superset', destination: 'local' }
    );

    expect(result.success).toBe(true);
    expect(fs.writeText).not.toHaveBeenCalled();
    expect(update).toHaveBeenCalledWith({
      scripts: {
        setup: 'bun install',
        run: './.superset/run.sh',
      },
    });
  });

  it('does not import Superset before and after script extensions', async () => {
    const fs = createFs({
      '.superset/config.json': JSON.stringify({
        setup: {
          before: ["echo 'running pre-setup'"],
          after: ['./.superset/my-post-setup.sh'],
        },
        teardown: {
          after: ['./.superset/my-cleanup.sh'],
        },
      }),
    });

    await expect(inspectProjectConfigMigrations(createProject(fs))).resolves.toEqual([]);
    await expect(
      migrateProjectConfigFromProvider(createProject(fs), {
        provider: 'superset',
        destination: 'shared',
      })
    ).resolves.toEqual({
      success: false,
      error: {
        type: 'write-config-failed',
        message: 'No supported Superset settings were found.',
      },
    });
  });

  it('detects importable Paseo settings', async () => {
    const fs = createFs({
      'paseo.json': JSON.stringify({
        worktree: {
          setup: ['npm ci', 'cp "$PASEO_SOURCE_CHECKOUT_PATH/.env" .env', 'npm run db:migrate'],
          teardown: 'npm run db:drop || true',
          terminals: [{ name: 'logs', command: 'tail -f dev.log' }],
        },
        scripts: {
          test: { command: 'npm test' },
          web: { command: 'npm run dev -- --port $PASEO_PORT', type: 'service', port: 3000 },
        },
      }),
    });

    await expect(inspectProjectConfigMigrations(createProject(fs))).resolves.toEqual([
      {
        provider: 'paseo',
        label: 'Paseo',
        files: ['paseo.json'],
        fields: ['scripts.setup', 'scripts.teardown'],
        unsupportedFields: [
          'scripts.test.command',
          'scripts.web.command',
          'scripts.web.type',
          'scripts.web.port',
          'worktree.terminals',
        ],
      },
    ]);
  });

  it('writes Paseo settings into .emdash.json', async () => {
    const fs = createFs({
      'paseo.json': JSON.stringify({
        worktree: {
          setup: 'npm ci',
          teardown: ['rm -rf .cache'],
        },
        scripts: {
          web: { command: 'npm run dev', type: 'service', port: 3000 },
          lint: { command: 'npm run lint' },
        },
      }),
    });
    const patch = vi.fn().mockResolvedValue({ success: true });

    const result = await migrateProjectConfigFromProvider(createProject(fs, { patch }), {
      provider: 'paseo',
      destination: 'shared',
    });

    expect(result.success).toBe(true);
    expect(JSON.parse(fs.content('.emdash.json') ?? '{}')).toEqual({
      scripts: {
        setup: 'npm ci',
        teardown: 'rm -rf .cache',
      },
    });
    expect(patch).toHaveBeenCalledWith({
      clearShareableFields: ['scripts.setup', 'scripts.teardown'],
    });
  });

  it('imports Paseo settings into local project settings', async () => {
    const fs = createFs({
      'paseo.json': JSON.stringify({
        worktree: {
          setup: 'npm ci',
        },
        scripts: {
          web: { command: 'npm run dev', type: 'service' },
        },
      }),
    });
    const update = vi.fn().mockResolvedValue({ success: true });

    const result = await migrateProjectConfigFromProvider(
      createProject(fs, {
        get: vi.fn().mockResolvedValue({
          scripts: {
            teardown: 'docker compose down',
          },
        }),
        update,
      }),
      { provider: 'paseo', destination: 'local' }
    );

    expect(result.success).toBe(true);
    expect(fs.writeText).not.toHaveBeenCalled();
    expect(update).toHaveBeenCalledWith({
      scripts: {
        setup: 'npm ci',
        teardown: 'docker compose down',
      },
    });
  });

  it('does not import when only Paseo scripts are configured', async () => {
    const fs = createFs({
      'paseo.json': JSON.stringify({
        scripts: {
          test: { command: 'npm test' },
          web: { command: 'npm run dev', type: 'service' },
        },
      }),
    });

    await expect(inspectProjectConfigMigrations(createProject(fs))).resolves.toEqual([]);
    await expect(
      migrateProjectConfigFromProvider(createProject(fs), {
        provider: 'paseo',
        destination: 'shared',
      })
    ).resolves.toEqual({
      success: false,
      error: {
        type: 'write-config-failed',
        message: 'No supported Paseo settings were found.',
      },
    });
  });

  it('detects importable Codex local environment settings', async () => {
    const fs = createFs({
      '.codex/environments/environment.toml': `
        version = 1
        name = "emdash"

        [setup]
        script = """
        npm install
        npm run build
        """

        [cleanup]
        script = "docker compose down"

        [[actions]]
        name = "Run"
        icon = "run"
        command = "npm run dev"
      `,
    });

    await expect(inspectProjectConfigMigrations(createProject(fs))).resolves.toEqual([
      {
        provider: 'codex',
        label: 'Codex',
        files: ['.codex/environments/environment.toml'],
        fields: ['scripts.setup', 'scripts.teardown'],
        unsupportedFields: ['actions.Run.command', 'actions.Run.icon'],
      },
    ]);
  });

  it('writes Codex local environment settings into .emdash.json', async () => {
    const fs = createFs({
      '.codex/environments/environment.toml': `
        [setup]
        script = "npm ci"

        [cleanup]
        script = "rm -rf .cache"

        [[actions]]
        name = "Test"
        command = "npm test"
      `,
    });
    const patch = vi.fn().mockResolvedValue({ success: true });

    const result = await migrateProjectConfigFromProvider(createProject(fs, { patch }), {
      provider: 'codex',
      destination: 'shared',
    });

    expect(result.success).toBe(true);
    expect(JSON.parse(fs.content('.emdash.json') ?? '{}')).toEqual({
      scripts: {
        setup: 'npm ci',
        teardown: 'rm -rf .cache',
      },
    });
    expect(patch).toHaveBeenCalledWith({
      clearShareableFields: ['scripts.setup', 'scripts.teardown'],
    });
  });

  it('imports Codex local environment settings into local project settings', async () => {
    const fs = createFs({
      '.codex/environments/environment.toml': `
        [setup]
        script = "npm ci"
      `,
    });
    const update = vi.fn().mockResolvedValue({ success: true });

    const result = await migrateProjectConfigFromProvider(
      createProject(fs, {
        get: vi.fn().mockResolvedValue({
          scripts: {
            teardown: 'docker compose down',
          },
        }),
        update,
      }),
      { provider: 'codex', destination: 'local' }
    );

    expect(result.success).toBe(true);
    expect(fs.writeText).not.toHaveBeenCalled();
    expect(update).toHaveBeenCalledWith({
      scripts: {
        setup: 'npm ci',
        teardown: 'docker compose down',
      },
    });
  });

  it('does not import when only Codex actions are configured', async () => {
    const fs = createFs({
      '.codex/environments/environment.toml': `
        [[actions]]
        name = "Run"
        icon = "run"
        command = "npm run dev"
      `,
    });

    await expect(inspectProjectConfigMigrations(createProject(fs))).resolves.toEqual([]);
    await expect(
      migrateProjectConfigFromProvider(createProject(fs), {
        provider: 'codex',
        destination: 'shared',
      })
    ).resolves.toEqual({
      success: false,
      error: {
        type: 'write-config-failed',
        message: 'No supported Codex settings were found.',
      },
    });
  });

  it('returns an error when no supported Conductor settings exist', async () => {
    const fs = createFs({
      'conductor.json': JSON.stringify({
        runScriptMode: 'concurrent',
      }),
      '.worktreeinclude': '',
    });

    await expect(
      migrateProjectConfigFromProvider(createProject(fs), {
        provider: 'conductor',
        destination: 'shared',
      })
    ).resolves.toEqual({
      success: false,
      error: {
        type: 'write-config-failed',
        message: 'No supported Conductor settings were found.',
      },
    });
  });

  it('does not import when .emdash.json already exists', async () => {
    const fs = createFs({
      'conductor.json': JSON.stringify({
        scripts: {
          run: 'pnpm dev',
        },
      }),
      '.emdash.json': JSON.stringify({ scripts: { run: 'pnpm dev' } }),
    });

    const result = await migrateProjectConfigFromProvider(createProject(fs), {
      provider: 'conductor',
      destination: 'shared',
    });

    expect(result.success).toBe(false);
    expect(result).toEqual({
      success: false,
      error: {
        type: 'write-config-failed',
        message: '.emdash.json already exists.',
      },
    });
    expect(fs.writeText).not.toHaveBeenCalled();
  });

  it('returns an error for unknown providers', async () => {
    const fs = createFs({});

    await expect(
      migrateProjectConfigFromProvider(createProject(fs), {
        provider: 'unknown' as never,
        destination: 'shared',
      })
    ).resolves.toEqual({
      success: false,
      error: {
        type: 'write-config-failed',
        message: 'Unsupported config provider.',
      },
    });
  });
});
