import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { mkdir, mkdtemp, rm, writeFile } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';
import {
  classifyCorePath,
  classifyImportSpecifier,
  isAllowedCoreModuleDependency,
} from './core-module-boundaries.js';

const repoRoot = path.resolve(import.meta.dirname, '../../..');
const coreSrcRoot = path.join(repoRoot, 'packages/core/src');
const desktopCoreSrcRoot = path.join(repoRoot, 'apps/emdash-desktop/src/core');

test('classifies core module source files', () => {
  assert.deepEqual(
    classifyCorePath(path.join(coreSrcRoot, 'runtimes/git/node/git-runtime.ts'), coreSrcRoot),
    {
      type: 'runtimes',
      moduleName: 'git',
      surface: 'node',
    }
  );
  assert.deepEqual(
    classifyCorePath(
      path.join(coreSrcRoot, 'services/fs-watch/api/index.ts').replaceAll('/', '\\'),
      coreSrcRoot
    ),
    {
      type: 'services',
      moduleName: 'fs-watch',
      surface: 'api',
    }
  );
  assert.equal(
    classifyCorePath(path.join(repoRoot, 'packages/core/src/workspace-server/index.ts')),
    undefined
  );
  assert.deepEqual(
    classifyCorePath(
      path.join(desktopCoreSrcRoot, 'features/tasks/contributions/mementos.ts'),
      desktopCoreSrcRoot
    ),
    {
      type: 'features',
      moduleName: 'tasks',
      surface: 'contributions',
    }
  );
  assert.deepEqual(
    classifyCorePath(
      path.join(desktopCoreSrcRoot, 'features/tasks/browser/stores/task-store.ts'),
      desktopCoreSrcRoot
    ),
    {
      type: 'features',
      moduleName: 'tasks',
      surface: 'browser',
    }
  );
});

test('classifies alias, package, and relative imports', () => {
  const fromFile = path.join(coreSrcRoot, 'services/agent-plugins/api/plugins/index.ts');

  assert.deepEqual(classifyImportSpecifier('#runtimes/acp/api', fromFile, coreSrcRoot), {
    type: 'runtimes',
    moduleName: 'acp',
    surface: 'api',
  });
  assert.deepEqual(
    classifyImportSpecifier('@emdash/core/primitives/path/api', fromFile, coreSrcRoot),
    {
      type: 'primitives',
      moduleName: 'path',
      surface: 'api',
    }
  );
  assert.deepEqual(
    classifyImportSpecifier('../../../host-dependencies/api', fromFile, coreSrcRoot),
    {
      type: 'services',
      moduleName: 'host-dependencies',
      surface: 'api',
    }
  );
  assert.equal(classifyImportSpecifier('@emdash/shared', fromFile, coreSrcRoot), undefined);
  assert.deepEqual(
    classifyImportSpecifier(
      '@core/primitives/mementos/api',
      path.join(desktopCoreSrcRoot, 'features/tasks/contributions/mementos.ts'),
      desktopCoreSrcRoot
    ),
    {
      type: 'primitives',
      moduleName: 'mementos',
      surface: 'api',
    }
  );
});

test('allows only the core module dependency graph', () => {
  const runtimeGit = { type: 'runtimes', moduleName: 'git' };
  const runtimeFiles = { type: 'runtimes', moduleName: 'files' };
  const serviceExec = { type: 'services', moduleName: 'exec' };
  const servicePty = { type: 'services', moduleName: 'pty' };
  const serviceRuntimeBroker = { type: 'services', moduleName: 'runtime-broker' };
  const serviceAppDb = { type: 'services', moduleName: 'app-db', surface: 'node' };
  const serviceOperations = { type: 'services', moduleName: 'operations', surface: 'node' };
  const serviceHostDependenciesApi = {
    type: 'services',
    moduleName: 'host-dependencies',
    surface: 'api',
  };
  const serviceHostDependenciesNode = {
    type: 'services',
    moduleName: 'host-dependencies',
    surface: 'node',
  };
  const primitivePath = { type: 'primitives', moduleName: 'path' };
  const primitiveHost = { type: 'primitives', moduleName: 'host' };
  const featureTasks = { type: 'features', moduleName: 'tasks' };
  const featureProjects = { type: 'features', moduleName: 'projects' };
  const featureTasksBrowser = { ...featureTasks, surface: 'browser' };
  const featureTasksApi = { ...featureTasks, surface: 'api' };
  const featureTasksNode = { ...featureTasks, surface: 'node' };
  const featureProjectsBrowser = { ...featureProjects, surface: 'browser' };
  const featureProjectsApi = { ...featureProjects, surface: 'api' };
  const featureProjectsNode = { ...featureProjects, surface: 'node' };
  const runtimeGitApi = { ...runtimeGit, surface: 'api' };
  const runtimeGitNode = { ...runtimeGit, surface: 'node' };

  assert.equal(isAllowedCoreModuleDependency(runtimeGit, runtimeGit), true);
  assert.equal(isAllowedCoreModuleDependency(runtimeGit, runtimeFiles), false);
  assert.equal(isAllowedCoreModuleDependency(runtimeGit, serviceExec), true);
  assert.equal(isAllowedCoreModuleDependency(runtimeGit, primitivePath), true);
  assert.equal(isAllowedCoreModuleDependency(serviceExec, primitivePath), true);
  assert.equal(isAllowedCoreModuleDependency(serviceExec, servicePty), false);
  assert.equal(isAllowedCoreModuleDependency(serviceExec, serviceAppDb), true);
  assert.equal(isAllowedCoreModuleDependency(featureTasksNode, serviceOperations), true);
  assert.equal(isAllowedCoreModuleDependency(serviceExec, runtimeGit), false);
  assert.equal(isAllowedCoreModuleDependency(serviceRuntimeBroker, runtimeGitApi), true);
  assert.equal(isAllowedCoreModuleDependency(serviceRuntimeBroker, runtimeGitNode), false);
  assert.equal(
    isAllowedCoreModuleDependency(serviceRuntimeBroker, serviceHostDependenciesApi),
    true
  );
  assert.equal(
    isAllowedCoreModuleDependency(serviceRuntimeBroker, serviceHostDependenciesNode),
    false
  );
  assert.equal(isAllowedCoreModuleDependency(serviceRuntimeBroker, serviceExec), false);
  const serviceSessionLifecycle = { type: 'services', moduleName: 'session-lifecycle' };
  const serviceSessionIntents = { type: 'services', moduleName: 'session-intents', surface: 'api' };
  const serviceConversationReports = {
    type: 'services',
    moduleName: 'conversation-reports',
    surface: 'node',
  };
  assert.equal(isAllowedCoreModuleDependency(serviceSessionLifecycle, serviceSessionIntents), true);
  assert.equal(
    isAllowedCoreModuleDependency(serviceSessionLifecycle, serviceConversationReports),
    true
  );
  assert.equal(isAllowedCoreModuleDependency(serviceSessionLifecycle, primitivePath), true);
  assert.equal(isAllowedCoreModuleDependency(serviceSessionLifecycle, serviceExec), false);
  assert.equal(isAllowedCoreModuleDependency(serviceExec, serviceSessionIntents), false);
  assert.equal(isAllowedCoreModuleDependency(primitivePath, primitiveHost), true);
  assert.equal(isAllowedCoreModuleDependency(primitivePath, serviceExec), false);
  assert.equal(isAllowedCoreModuleDependency(primitivePath, runtimeGit), false);
  assert.equal(isAllowedCoreModuleDependency(featureTasks, primitivePath), true);
  assert.equal(isAllowedCoreModuleDependency(featureTasks, featureTasks), true);
  assert.equal(isAllowedCoreModuleDependency(featureTasks, featureProjects), false);
  assert.equal(isAllowedCoreModuleDependency(featureTasksBrowser, featureProjectsBrowser), false);
  assert.equal(isAllowedCoreModuleDependency(featureTasksBrowser, featureProjectsApi), true);
  assert.equal(isAllowedCoreModuleDependency(featureTasksBrowser, featureProjectsNode), false);
  assert.equal(isAllowedCoreModuleDependency(featureTasksBrowser, runtimeGitApi), true);
  assert.equal(isAllowedCoreModuleDependency(featureTasksBrowser, runtimeGitNode), false);
  assert.equal(isAllowedCoreModuleDependency(featureTasksApi, runtimeGitApi), true);
  assert.equal(
    isAllowedCoreModuleDependency(featureTasksNode, {
      ...serviceExec,
      surface: 'api',
    }),
    true
  );
  assert.equal(
    isAllowedCoreModuleDependency(featureTasksNode, {
      ...serviceExec,
      surface: 'node',
    }),
    true
  );
  assert.equal(isAllowedCoreModuleDependency(featureTasksNode, serviceExec), false);
  assert.equal(isAllowedCoreModuleDependency(featureTasksBrowser, serviceExec), false);
  assert.equal(isAllowedCoreModuleDependency(featureTasksNode, featureProjectsNode), false);
});

test('oxlint visitor reports imports, re-exports, and dynamic imports', async () => {
  const tempRoot = await mkdtemp(path.join(os.tmpdir(), 'emdash-core-boundaries-'));
  try {
    const fixtureCoreRoot = path.join(tempRoot, 'packages/core/src');
    const serviceDir = path.join(fixtureCoreRoot, 'services/example/api');
    const primitiveDir = path.join(fixtureCoreRoot, 'primitives/example/api');
    const featureDir = path.join(fixtureCoreRoot, 'features/tasks/browser');
    await mkdir(serviceDir, { recursive: true });
    await mkdir(primitiveDir, { recursive: true });
    await mkdir(featureDir, { recursive: true });
    await writeFile(
      path.join(tempRoot, '.oxlintrc.json'),
      JSON.stringify(
        {
          plugins: ['eslint', 'typescript'],
          jsPlugins: [path.join(repoRoot, 'tooling/oxlint/index.js')],
          env: { node: true, es2020: true },
          rules: {
            'emdash/core-module-boundaries': ['error', { coreSrcRoot: fixtureCoreRoot }],
          },
        },
        null,
        2
      )
    );
    await writeFile(path.join(primitiveDir, 'valid.ts'), 'export const ok = 1;\n');
    await writeFile(
      path.join(serviceDir, 'invalid.ts'),
      [
        "import { x } from '#runtimes/git/api';",
        "export { y } from '#runtimes/files/api';",
        "await import('#runtimes/acp/api');",
      ].join('\n'),
      'utf8'
    );

    const result = await runOxlint(
      path.join(tempRoot, '.oxlintrc.json'),
      path.join(fixtureCoreRoot, 'services/example/api/invalid.ts')
    );
    assert.notEqual(result.code, 0);
    assert.match(result.output, /emdash\(core-module-boundaries\)/);
    assert.match(result.output, /services\/example must not import runtimes\/git/);
    assert.match(result.output, /services\/example must not import runtimes\/files/);
    assert.match(result.output, /services\/example must not import runtimes\/acp/);

    const crossSlicePath = path.join(featureDir, 'invalid.ts');
    await writeFile(
      crossSlicePath,
      "import { project } from '@core/features/projects/browser/project';\n"
    );
    const crossSliceResult = await runOxlint(path.join(tempRoot, '.oxlintrc.json'), crossSlicePath);
    assert.notEqual(crossSliceResult.code, 0);
    assert.match(crossSliceResult.output, /features\/tasks must not import features\/projects/);

    const validResult = await runOxlint(
      path.join(tempRoot, '.oxlintrc.json'),
      path.join(primitiveDir, 'valid.ts')
    );
    assert.equal(validResult.code, 0, validResult.output);
  } finally {
    await rm(tempRoot, { recursive: true, force: true });
  }
});

test('a missing crossSlice allowlist key is valid and means no exceptions', async () => {
  const tempRoot = await mkdtemp(path.join(os.tmpdir(), 'emdash-core-boundaries-allowlist-'));
  try {
    const fixtureCoreRoot = path.join(tempRoot, 'packages/core/src');
    const featureDir = path.join(fixtureCoreRoot, 'features/tasks/browser');
    await mkdir(featureDir, { recursive: true });
    const violatingPath = path.join(featureDir, 'invalid.ts');
    await writeFile(
      violatingPath,
      "import { project } from '@core/features/projects/browser/project';\n"
    );
    const allowlistPath = path.join(tempRoot, 'allowlists.json');
    const configPath = path.join(tempRoot, '.oxlintrc.json');
    await writeFile(
      configPath,
      JSON.stringify(
        {
          plugins: ['eslint', 'typescript'],
          jsPlugins: [path.join(repoRoot, 'tooling/oxlint/index.js')],
          env: { node: true, es2020: true },
          rules: {
            'emdash/core-module-boundaries': [
              'error',
              { coreSrcRoot: fixtureCoreRoot, allowlistPath, repoRoot: tempRoot },
            ],
          },
        },
        null,
        2
      )
    );

    await writeFile(
      allowlistPath,
      JSON.stringify({ crossSlice: [path.relative(tempRoot, violatingPath)] })
    );
    const allowlisted = await runOxlint(configPath, violatingPath);
    assert.equal(allowlisted.code, 0, allowlisted.output);

    await writeFile(allowlistPath, JSON.stringify({ coreToHost: [] }));
    const strict = await runOxlint(configPath, violatingPath);
    assert.notEqual(strict.code, 0);
    assert.match(strict.output, /features\/tasks must not import features\/projects/);
  } finally {
    await rm(tempRoot, { recursive: true, force: true });
  }
});

function runOxlint(config, file) {
  return new Promise((resolve, reject) => {
    const child = spawn('pnpm', ['exec', 'oxlint', '--config', config, file], {
      cwd: repoRoot,
      stdio: ['ignore', 'pipe', 'pipe'],
    });
    let output = '';
    child.stdout.on('data', (chunk) => {
      output += chunk;
    });
    child.stderr.on('data', (chunk) => {
      output += chunk;
    });
    child.on('error', reject);
    child.on('close', (code) => resolve({ code, output }));
  });
}
