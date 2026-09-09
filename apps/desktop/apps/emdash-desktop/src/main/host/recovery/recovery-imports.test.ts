/**
 * Guard test: verify that recovery-critical source files do not acquire static
 * imports from heavyweight modules (database, gateway, SSH, ACP, updater, Wire).
 *
 * A static import from any of those modules means a load failure there will
 * also prevent the recovery window from opening — defeating its purpose.
 *
 * Dynamic imports (`await import(...)`) are intentionally NOT detected here
 * because they are evaluated lazily and their failures are caught by the
 * surrounding try/catch in recovery-window.ts.
 */
import { readFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

// Two levels up: recovery/ → host/ → main/
const SRC_MAIN = resolve(dirname(fileURLToPath(import.meta.url)), '../..');

function staticValueImports(filePath: string): string[] {
  const source = readFileSync(filePath, 'utf8');
  // Match `import Foo from '...'` and `import { ... } from '...'` but exclude
  // `import type` (type-only imports are erased and never affect the runtime graph).
  const pattern = /^import(?!\s+type[\s{])[\s\S]*?from\s+['"]([^'"]+)['"]/gm;
  const modules: string[] = [];
  let match: RegExpExecArray | null;
  while ((match = pattern.exec(source)) !== null) {
    modules.push(match[1]);
  }
  return modules;
}

// Any static import matching one of these patterns in a recovery file is a bug:
// it means a module-load failure in that package will prevent recovery.
const FORBIDDEN_PATTERNS: RegExp[] = [
  /^@main\/db/,
  /^@main\/gateway/,
  /^@main\/core\/acp/,
  /^@main\/core\/ssh/,
  /^@main\/core\/tasks/,
  /drizzle/,
  /electron-updater/,
  /@emdash\/wire/,
  /better-sqlite/,
  /node-pty/,
];

const RECOVERY_FILES = [
  { label: 'bootstrap/core/recovery.ts', path: join(SRC_MAIN, 'bootstrap/core/recovery.ts') },
  {
    label: 'host/recovery/recovery-window.ts',
    path: join(SRC_MAIN, 'host/recovery/recovery-window.ts'),
  },
  {
    label: 'host/recovery/recovery-bootstrap.ts',
    path: join(SRC_MAIN, 'host/recovery/recovery-bootstrap.ts'),
  },
];

describe('recovery module import isolation', () => {
  for (const file of RECOVERY_FILES) {
    it(`${file.label} has no heavy static imports`, () => {
      const imports = staticValueImports(file.path);
      for (const imp of imports) {
        for (const pattern of FORBIDDEN_PATTERNS) {
          expect(imp, `forbidden import "${imp}" in ${file.label} matched ${pattern}`).not.toMatch(
            pattern
          );
        }
      }
    });
  }
});
