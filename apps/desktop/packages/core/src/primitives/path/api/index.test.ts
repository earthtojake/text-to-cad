import { readdirSync, readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';
import * as pathExports from './index';

describe('@emdash/core/primitives/path/api public exports', () => {
  it('exposes the foundation path API', () => {
    const exported = pathExports as Record<string, unknown>;

    expect(exported.parseAbsolute).toBeTypeOf('function');
    expect(exported.parsePortableRelativePath).toBeTypeOf('function');
    expect(exported.createPathSemantics).toBeTypeOf('function');
    expect(exported.hostFileRef).toBeTypeOf('function');
    expect(exported.hostFileRef).toBeTypeOf('function');
    expect(exported.scopedPath).toBeTypeOf('function');
    expect(exported.encodeResourceUri).toBeTypeOf('function');
    expect(exported.decodeResourceUri).toBeTypeOf('function');
    expect(exported.resourceKeyFromFileRef).toBeTypeOf('function');
    expect(exported.hostFileRefSchema).toBeTypeOf('object');
    expect(exported.absolutePathInputSchema).toBeTypeOf('function');
    expect(exported.resourceRefFromUriSchema).toBeTypeOf('object');
  });

  it('does not import Node APIs from implementation files', () => {
    const dir = dirname(fileURLToPath(import.meta.url));
    const implementationFiles = readdirSync(dir).filter(
      (file) => file.endsWith('.ts') && !file.endsWith('.test.ts')
    );

    for (const file of implementationFiles) {
      const source = readFileSync(join(dir, file), 'utf8');
      expect(source, file).not.toMatch(/from ['"]node:/u);
      expect(source, file).not.toMatch(/import\(['"]node:/u);
    }
  });
});
