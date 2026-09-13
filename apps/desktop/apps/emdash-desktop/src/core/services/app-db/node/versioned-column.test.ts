import { defineVersionedSchema } from '@emdash/core/primitives/versioned-schema/api';
import { describe, expect, it, vi } from 'vitest';
import z from 'zod';
import { parseVersionedColumn, serializeVersionedColumn } from './versioned-column';

// ---------------------------------------------------------------------------
// Shared test schemas
// ---------------------------------------------------------------------------

const v1Schema = z.object({ version: z.literal('1'), name: z.string() });
const v2Schema = z.object({ version: z.literal('2'), name: z.string(), count: z.number() });

function makeTestSchema() {
  return defineVersionedSchema()
    .initial('1', v1Schema)
    .version('2', v2Schema, (v1) => ({
      version: '2' as const,
      name: v1.name,
      count: 0,
    }))
    .build();
}

// ---------------------------------------------------------------------------
// parseVersionedColumn (fromDriver equivalent)
// ---------------------------------------------------------------------------

describe('parseVersionedColumn', () => {
  it('returns null for null input', () => {
    expect(parseVersionedColumn(makeTestSchema(), null)).toBeNull();
  });

  it('returns null for empty string', () => {
    expect(parseVersionedColumn(makeTestSchema(), '')).toBeNull();
  });

  it('parses and returns current-version data', () => {
    const schema = makeTestSchema();
    const data = { version: '2', name: 'Alice', count: 42 };
    expect(parseVersionedColumn(schema, JSON.stringify(data))).toEqual(data);
  });

  it('upgrades older-version data transparently', () => {
    const schema = makeTestSchema();
    const result = parseVersionedColumn(schema, JSON.stringify({ version: '1', name: 'Bob' }));
    expect(result).toEqual({ version: '2', name: 'Bob', count: 0 });
  });

  it('returns null for corrupt (non-JSON) input without throwing', () => {
    const schema = makeTestSchema();
    expect(() => parseVersionedColumn(schema, 'not-json')).not.toThrow();
    expect(parseVersionedColumn(schema, 'not-json')).toBeNull();
  });

  it('returns null for future-version data without throwing', () => {
    const schema = makeTestSchema();
    const futureData = JSON.stringify({ version: '99', name: 'Carol', count: 0 });
    expect(() => parseVersionedColumn(schema, futureData)).not.toThrow();
    expect(parseVersionedColumn(schema, futureData)).toBeNull();
  });

  it('returns null when version field is absent and no unversioned entry exists', () => {
    const schema = makeTestSchema();
    expect(parseVersionedColumn(schema, JSON.stringify({ name: 'Dave', count: 0 }))).toBeNull();
  });

  it('returns null for needs-context data without throwing', () => {
    const schema = defineVersionedSchema()
      .initial('1', v1Schema)
      .version('2', v2Schema, (_v1) => null)
      .build();
    const input = JSON.stringify({ version: '1', name: 'Eve' });
    expect(() => parseVersionedColumn(schema, input)).not.toThrow();
    expect(parseVersionedColumn(schema, input)).toBeNull();
  });

  it('handles unversioned data with an unversioned entry', () => {
    const unversionedSchema = z.object({ name: z.string() });
    const schema = defineVersionedSchema()
      .unversioned(unversionedSchema)
      .version('1', v1Schema, (v0) => ({ version: '1' as const, name: v0.name }))
      .build();
    expect(parseVersionedColumn(schema, JSON.stringify({ name: 'Frank' }))).toEqual({
      version: '1',
      name: 'Frank',
    });
  });

  it('does not throw when up() function throws', () => {
    const schema = defineVersionedSchema()
      .initial('1', v1Schema)
      .version('2', v2Schema, (_v1) => {
        throw new Error('Upgrade exploded');
      })
      .build();
    const input = JSON.stringify({ version: '1', name: 'Grace' });
    expect(() => parseVersionedColumn(schema, input)).not.toThrow();
    expect(parseVersionedColumn(schema, input)).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// serializeVersionedColumn (toDriver equivalent)
// ---------------------------------------------------------------------------

describe('serializeVersionedColumn', () => {
  it('returns null for null input', () => {
    expect(serializeVersionedColumn(makeTestSchema(), null)).toBeNull();
  });

  it('returns null for undefined input', () => {
    expect(serializeVersionedColumn(makeTestSchema(), undefined)).toBeNull();
  });

  it('serializes a valid object to a JSON string', () => {
    const schema = makeTestSchema();
    const data = { version: '2' as const, name: 'Henry', count: 7 };
    const result = serializeVersionedColumn(schema, data);
    expect(typeof result).toBe('string');
    expect(JSON.parse(result!)).toEqual(data);
  });
});

// ---------------------------------------------------------------------------
// Round-trip
// ---------------------------------------------------------------------------

describe('round-trip', () => {
  it('parseVersionedColumn(serializeVersionedColumn(data)) returns the original data', () => {
    const schema = makeTestSchema();
    const data = { version: '2' as const, name: 'Iris', count: 3 };
    expect(parseVersionedColumn(schema, serializeVersionedColumn(schema, data))).toEqual(data);
  });

  it('parseVersionedColumn(serializeVersionedColumn(null)) returns null', () => {
    const schema = makeTestSchema();
    expect(parseVersionedColumn(schema, serializeVersionedColumn(schema, null))).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// Logging
// ---------------------------------------------------------------------------

describe('logging', () => {
  it('logs a warning for future-version data', async () => {
    const loggerModule = await import('@emdash/shared/logger');
    const warnSpy = vi.spyOn(loggerModule.log, 'warn').mockImplementation(() => {});

    try {
      parseVersionedColumn(
        makeTestSchema(),
        JSON.stringify({ version: '99', name: 'Jake', count: 0 })
      );
      expect(warnSpy).toHaveBeenCalledWith(
        expect.stringContaining('Future schema version'),
        expect.objectContaining({ version: '99' })
      );
    } finally {
      warnSpy.mockRestore();
    }
  });

  it('logs a warning for corrupt non-JSON data', async () => {
    const loggerModule = await import('@emdash/shared/logger');
    const warnSpy = vi.spyOn(loggerModule.log, 'warn').mockImplementation(() => {});

    try {
      parseVersionedColumn(makeTestSchema(), 'not-valid-json');
      expect(warnSpy).toHaveBeenCalledWith(expect.stringContaining('JSON.parse'));
    } finally {
      warnSpy.mockRestore();
    }
  });

  it('logs a warning for invalid data (dev mode validation failure)', async () => {
    const loggerModule = await import('@emdash/shared/logger');
    const warnSpy = vi.spyOn(loggerModule.log, 'warn').mockImplementation(() => {});

    try {
      // version: '2' but missing required 'count' — fails dev validation
      parseVersionedColumn(makeTestSchema(), JSON.stringify({ version: '2', name: 'Kim' }));
      expect(warnSpy).toHaveBeenCalled();
    } finally {
      warnSpy.mockRestore();
    }
  });
});
