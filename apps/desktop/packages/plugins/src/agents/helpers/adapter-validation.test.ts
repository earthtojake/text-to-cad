import { mkdir, mkdtemp, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';
import type { AdapterAsset } from './adapter-assets';
import {
  collectModuleSpecifiers,
  validateAdapterBundleAssets,
  validateAdapterBundleSource,
} from './adapter-validation';

describe('adapter bundle validation', () => {
  it('collects live import and require specifiers', () => {
    const specifiers = collectModuleSpecifiers(`
      import fs from 'node:fs';
      export { x } from "node:path";
      const crypto = require('node:crypto');
      const lazy = import('node:os');
    `);

    expect([...specifiers].sort()).toEqual(['node:crypto', 'node:fs', 'node:os', 'node:path']);
  });

  it('allows only Node builtins as live specifiers', () => {
    expect(
      validateAdapterBundleSource({
        fileName: 'adapter.mjs',
        source: "import fs from 'node:fs';\nconst path = require('path');",
        sizeBytes: 100,
      })
    ).toEqual([]);

    expect(
      validateAdapterBundleSource({
        fileName: 'adapter.mjs',
        source: "import codex from '@openai/codex';",
        sizeBytes: 100,
      })
    ).toContain("adapter.mjs contains unexpected external '@openai/codex'");
  });

  it('rejects native bindings and oversized bundles', () => {
    expect(
      validateAdapterBundleSource({
        fileName: 'adapter.mjs',
        source: "const binding = 'native.node';",
        sizeBytes: 11,
        maxBytes: 10,
      })
    ).toEqual([
      'adapter.mjs is 11 bytes, above the 10 byte limit',
      'adapter.mjs contains a native .node binding reference',
    ]);
  });

  it('validates declared adapter files in a directory', async () => {
    const root = await mkdtemp(join(tmpdir(), 'emdash-adapter-validation-'));
    const assets: AdapterAsset[] = [
      { name: 'ok', specifier: '@example/ok', format: 'esm' },
      { name: 'missing', specifier: '@example/missing', format: 'cjs' },
    ];

    try {
      await mkdir(root, { recursive: true });
      await writeFile(join(root, 'ok.mjs'), "import fs from 'node:fs';", 'utf8');
      await expect(validateAdapterBundleAssets({ adapterDirectory: root, assets })).rejects.toThrow(
        /missing\.cjs is missing or unreadable/
      );
    } finally {
      await rm(root, { recursive: true, force: true });
    }
  });
});
