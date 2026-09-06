import assert from 'node:assert/strict';
import { test } from 'node:test';
import { collectBoundaryViolations, findStaleAllowlistEntries } from './allowlist-ratchet.mjs';

function diagnostic(code, filename) {
  return { code, filename, message: 'x', severity: 'error' };
}

test('collectBoundaryViolations buckets core-host-boundaries by file location', () => {
  const violations = collectBoundaryViolations([
    diagnostic('emdash(core-host-boundaries)', 'apps/emdash-desktop/src/core/features/a/view.tsx'),
    diagnostic('emdash(core-host-boundaries)', 'apps/emdash-desktop/src/main/core/app/service.ts'),
  ]);

  assert.deepEqual(
    [...violations.coreToHost],
    ['apps/emdash-desktop/src/core/features/a/view.tsx']
  );
  assert.deepEqual(
    [...violations.mainCoreToFeatures],
    ['apps/emdash-desktop/src/main/core/app/service.ts']
  );
  assert.equal(violations.crossSlice.size, 0);
});

test('collectBoundaryViolations buckets core-module-boundaries as crossSlice', () => {
  const violations = collectBoundaryViolations([
    diagnostic(
      'emdash(core-module-boundaries)',
      'apps/emdash-desktop/src/core/services/x/node/service.ts'
    ),
  ]);

  assert.deepEqual(
    [...violations.crossSlice],
    ['apps/emdash-desktop/src/core/services/x/node/service.ts']
  );
});

test('collectBoundaryViolations buckets no-tsx-in-api as tsxInApi', () => {
  const violations = collectBoundaryViolations([
    diagnostic(
      'emdash(no-tsx-in-api)',
      'apps/emdash-desktop/src/core/features/a/api/browser/view.tsx'
    ),
  ]);

  assert.deepEqual(
    [...violations.tsxInApi],
    ['apps/emdash-desktop/src/core/features/a/api/browser/view.tsx']
  );
  assert.equal(violations.crossSlice.size, 0);
});

test('findStaleAllowlistEntries reports stale tsxInApi entries', () => {
  const stale = findStaleAllowlistEntries(
    {
      tsxInApi: [
        'apps/emdash-desktop/src/core/features/a/api/view.tsx',
        'apps/emdash-desktop/src/core/features/b/api/view.tsx',
      ],
    },
    {
      coreToHost: new Set(),
      mainCoreToFeatures: new Set(),
      crossSlice: new Set(),
      tsxInApi: new Set(['apps/emdash-desktop/src/core/features/a/api/view.tsx']),
    }
  );

  assert.deepEqual(stale, {
    tsxInApi: ['apps/emdash-desktop/src/core/features/b/api/view.tsx'],
  });
});

test('collectBoundaryViolations ignores unrelated diagnostics and dedupes files', () => {
  const violations = collectBoundaryViolations([
    diagnostic('emdash(no-dynamic-imports)', 'apps/emdash-desktop/src/core/features/a/view.tsx'),
    diagnostic('eslint(no-unused-vars)', 'apps/emdash-desktop/src/core/features/a/view.tsx'),
    diagnostic('emdash(core-host-boundaries)', 'apps/emdash-desktop/src/core/features/a/view.tsx'),
    diagnostic('emdash(core-host-boundaries)', 'apps/emdash-desktop/src/core/features/a/view.tsx'),
  ]);

  assert.equal(violations.coreToHost.size, 1);
  assert.equal(violations.crossSlice.size, 0);
  assert.equal(violations.mainCoreToFeatures.size, 0);
});

test('collectBoundaryViolations normalizes windows separators and leading ./', () => {
  const violations = collectBoundaryViolations([
    diagnostic(
      'emdash(core-host-boundaries)',
      './apps/emdash-desktop/src/core/features/a/view.tsx'
    ),
    diagnostic(
      'emdash(core-module-boundaries)',
      'apps\\emdash-desktop\\src\\core\\services\\x\\service.ts'
    ),
  ]);

  assert.deepEqual(
    [...violations.coreToHost],
    ['apps/emdash-desktop/src/core/features/a/view.tsx']
  );
  assert.deepEqual(
    [...violations.crossSlice],
    ['apps/emdash-desktop/src/core/services/x/service.ts']
  );
});

test('findStaleAllowlistEntries reports entries with no matching violation', () => {
  const allowlists = {
    coreToHost: [
      'apps/emdash-desktop/src/core/features/a/view.tsx',
      'apps/emdash-desktop/src/core/features/b/view.tsx',
    ],
    mainCoreToFeatures: [],
    crossSlice: ['apps/emdash-desktop/src/core/services/x/service.ts'],
  };
  const violations = {
    coreToHost: new Set(['apps/emdash-desktop/src/core/features/a/view.tsx']),
    mainCoreToFeatures: new Set(),
    crossSlice: new Set(['apps/emdash-desktop/src/core/services/x/service.ts']),
  };

  const stale = findStaleAllowlistEntries(allowlists, violations);

  assert.deepEqual(stale, {
    coreToHost: ['apps/emdash-desktop/src/core/features/b/view.tsx'],
  });
});

test('findStaleAllowlistEntries returns empty object when every entry still violates', () => {
  const allowlists = {
    coreToHost: ['apps/emdash-desktop/src/core/features/a/view.tsx'],
    mainCoreToFeatures: [],
    crossSlice: [],
  };
  const violations = {
    coreToHost: new Set(['apps/emdash-desktop/src/core/features/a/view.tsx']),
    mainCoreToFeatures: new Set(),
    crossSlice: new Set(),
  };

  assert.deepEqual(findStaleAllowlistEntries(allowlists, violations), {});
});

test('findStaleAllowlistEntries never reports extra violations as a problem', () => {
  const allowlists = { coreToHost: [], mainCoreToFeatures: [], crossSlice: [] };
  const violations = {
    coreToHost: new Set(['apps/emdash-desktop/src/core/features/new/view.tsx']),
    mainCoreToFeatures: new Set(),
    crossSlice: new Set(),
  };

  assert.deepEqual(findStaleAllowlistEntries(allowlists, violations), {});
});

test('findStaleAllowlistEntries treats a deleted crossSlice key as legal', () => {
  const stale = findStaleAllowlistEntries(
    { coreToHost: [], mainCoreToFeatures: [] },
    {
      coreToHost: new Set(),
      mainCoreToFeatures: new Set(),
      crossSlice: new Set(['apps/emdash-desktop/src/core/services/x/service.ts']),
    }
  );

  assert.deepEqual(stale, {});
});

test('findStaleAllowlistEntries tolerates missing categories in the allowlist file', () => {
  const stale = findStaleAllowlistEntries(
    { coreToHost: ['apps/emdash-desktop/src/core/features/gone/view.tsx'] },
    { coreToHost: new Set(), mainCoreToFeatures: new Set(), crossSlice: new Set() }
  );

  assert.deepEqual(stale, {
    coreToHost: ['apps/emdash-desktop/src/core/features/gone/view.tsx'],
  });
});
