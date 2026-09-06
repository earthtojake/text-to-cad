import { describe, expect, it } from 'vitest';
import z from 'zod';
import { defineVersionedSchema } from './versioned-schema';

// ---------------------------------------------------------------------------
// Shared test schemas
// ---------------------------------------------------------------------------

const v1Schema = z.object({
  version: z.literal('1'),
  name: z.string(),
});

const v2Schema = z.object({
  version: z.literal('2'),
  name: z.string(),
  count: z.number(),
});

const v3Schema = z.object({
  version: z.literal('3'),
  name: z.string(),
  count: z.number(),
  active: z.boolean(),
});

// A simple two-version schema used across many tests
function makeTwoVersionSchema() {
  return defineVersionedSchema()
    .initial('1', v1Schema)
    .version('2', v2Schema, (v1) => ({
      version: '2' as const,
      name: v1.name,
      count: 0,
    }))
    .build();
}

function makeThreeVersionSchema() {
  return defineVersionedSchema()
    .initial('1', v1Schema)
    .version('2', v2Schema, (v1) => ({
      version: '2' as const,
      name: v1.name,
      count: 0,
    }))
    .version('3', v3Schema, (v2) => ({
      version: '3' as const,
      name: v2.name,
      count: v2.count,
      active: true,
    }))
    .build();
}

// ---------------------------------------------------------------------------
// safeParse — fast path (current version)
// ---------------------------------------------------------------------------

describe('safeParse — current-version fast path', () => {
  it('returns ok without running any up() when data is at the latest version', () => {
    const schema = makeTwoVersionSchema();
    const data = { version: '2', name: 'Alice', count: 42 };
    const result = schema.safeParse(data);
    expect(result).toEqual({ status: 'ok', data });
  });

  it('returns ok for a schema with only one version', () => {
    const schema = defineVersionedSchema().initial('1', v1Schema).build();
    const data = { version: '1', name: 'Bob' };
    expect(schema.safeParse(data)).toEqual({ status: 'ok', data });
  });
});

// ---------------------------------------------------------------------------
// safeParse — single-step upgrade
// ---------------------------------------------------------------------------

describe('safeParse — single-step upgrade', () => {
  it('upgrades v1 data to v2 using the up() function', () => {
    const schema = makeTwoVersionSchema();
    const result = schema.safeParse({ version: '1', name: 'Carol' });
    expect(result).toEqual({
      status: 'ok',
      data: { version: '2', name: 'Carol', count: 0 },
    });
  });

  it('up() receives the correctly-typed previous version data', () => {
    let capturedPrev: unknown;
    const schema = defineVersionedSchema()
      .initial('1', v1Schema)
      .version('2', v2Schema, (v1) => {
        capturedPrev = v1;
        return { version: '2' as const, name: v1.name, count: 0 };
      })
      .build();

    schema.safeParse({ version: '1', name: 'Dave' });
    expect(capturedPrev).toEqual({ version: '1', name: 'Dave' });
  });
});

// ---------------------------------------------------------------------------
// safeParse — multi-step upgrade chain
// ---------------------------------------------------------------------------

describe('safeParse — multi-step upgrade chain', () => {
  it('runs all upgrade steps in order from v1 to v3', () => {
    const schema = makeThreeVersionSchema();
    const result = schema.safeParse({ version: '1', name: 'Eve' });
    expect(result).toEqual({
      status: 'ok',
      data: { version: '3', name: 'Eve', count: 0, active: true },
    });
  });

  it('runs only the required steps when starting from v2', () => {
    const schema = makeThreeVersionSchema();
    const result = schema.safeParse({ version: '2', name: 'Frank', count: 5 });
    expect(result).toEqual({
      status: 'ok',
      data: { version: '3', name: 'Frank', count: 5, active: true },
    });
  });

  it('tracks exactly which up() calls ran', () => {
    const calls: string[] = [];
    const schema = defineVersionedSchema()
      .initial('1', v1Schema)
      .version('2', v2Schema, (v1) => {
        calls.push('1->2');
        return { version: '2' as const, name: v1.name, count: 0 };
      })
      .version('3', v3Schema, (v2) => {
        calls.push('2->3');
        return { version: '3' as const, name: v2.name, count: v2.count, active: false };
      })
      .build();

    schema.safeParse({ version: '1', name: 'Grace' });
    expect(calls).toEqual(['1->2', '2->3']);
  });
});

// ---------------------------------------------------------------------------
// safeParse — unversioned data (legacy rows with no version field)
// ---------------------------------------------------------------------------

describe('safeParse — unversioned data', () => {
  const unversionedSchema = z.object({ name: z.string() });

  function makeUnversionedSchema() {
    return defineVersionedSchema()
      .unversioned(unversionedSchema)
      .version('1', v1Schema, (v0) => ({
        version: '1' as const,
        name: v0.name,
      }))
      .build();
  }

  it('parses data with no version field using the unversioned schema', () => {
    const schema = makeUnversionedSchema();
    const result = schema.safeParse({ name: 'Henry' });
    expect(result).toEqual({
      status: 'ok',
      data: { version: '1', name: 'Henry' },
    });
  });

  it('parses data with null version field using the unversioned schema', () => {
    const schema = makeUnversionedSchema();
    const result = schema.safeParse({ version: null, name: 'Iris' });
    expect(result).toEqual({
      status: 'ok',
      data: { version: '1', name: 'Iris' },
    });
  });

  it('parses unversioned data that is already at the latest version (no upgrade needed)', () => {
    // The unversioned schema must not require a version field — it describes
    // data that was written before any versioning existed.
    const legacySchema = z.object({ name: z.string() });
    const schema = defineVersionedSchema().unversioned(legacySchema).build();
    const result = schema.safeParse({ name: 'Jack' });
    expect(result.status).toBe('ok');
    if (result.status === 'ok') {
      expect(result.data.name).toBe('Jack');
    }
  });
});

// ---------------------------------------------------------------------------
// safeParse — needs-context
// ---------------------------------------------------------------------------

describe('safeParse — needs-context', () => {
  it('returns needs-context when up() returns null', () => {
    const schema = defineVersionedSchema()
      .initial('1', v1Schema)
      .version('2', v2Schema, (_v1) => null)
      .build();

    const input = { version: '1', name: 'Kate' };
    const result = schema.safeParse(input);
    expect(result).toEqual({
      status: 'needs-context',
      version: '1',
      raw: input,
    });
  });

  it('raw contains the original parsed object', () => {
    const input = { version: '1', name: 'Leo', extraField: 'extra' };
    const schema = defineVersionedSchema()
      .initial('1', z.object({ version: z.literal('1'), name: z.string() }).passthrough())
      .version('2', v2Schema, (_v1) => null)
      .build();

    const result = schema.safeParse(input);
    expect(result.status).toBe('needs-context');
    if (result.status === 'needs-context') {
      expect(result.raw).toBe(input);
      expect(result.version).toBe('1');
    }
  });
});

// ---------------------------------------------------------------------------
// safeParse — future-version
// ---------------------------------------------------------------------------

describe('safeParse — future-version', () => {
  it('returns future-version for an unrecognized version string', () => {
    const schema = makeTwoVersionSchema();
    const result = schema.safeParse({ version: '99', name: 'Mia', count: 1 });
    expect(result).toEqual({ status: 'future-version', version: '99' });
  });

  it('returns future-version even when the object is otherwise valid', () => {
    const schema = makeTwoVersionSchema();
    const result = schema.safeParse({ version: '3', name: 'Noah', count: 0 });
    expect(result).toEqual({ status: 'future-version', version: '3' });
  });
});

// ---------------------------------------------------------------------------
// safeParse — invalid data
// ---------------------------------------------------------------------------

describe('safeParse — invalid data', () => {
  it('returns invalid for null input', () => {
    const schema = makeTwoVersionSchema();
    const result = schema.safeParse(null);
    expect(result.status).toBe('invalid');
  });

  it('returns invalid for array input', () => {
    const schema = makeTwoVersionSchema();
    const result = schema.safeParse([{ version: '2', name: 'test', count: 0 }]);
    expect(result.status).toBe('invalid');
  });

  it('returns invalid for primitive input', () => {
    const schema = makeTwoVersionSchema();
    expect(schema.safeParse('string').status).toBe('invalid');
    expect(schema.safeParse(42).status).toBe('invalid');
    expect(schema.safeParse(true).status).toBe('invalid');
  });

  it('returns invalid when version field is missing and no unversioned entry exists', () => {
    const schema = makeTwoVersionSchema();
    const result = schema.safeParse({ name: 'Olivia', count: 0 });
    expect(result.status).toBe('invalid');
  });

  it('returns invalid when version field is a non-string', () => {
    const schema = makeTwoVersionSchema();
    const result = schema.safeParse({ version: 2, name: 'Peter', count: 0 });
    expect(result.status).toBe('invalid');
  });

  it('returns invalid when data fails schema validation for its declared version (dev mode)', () => {
    // In vitest (dev mode), safeParse runs full Zod validation
    const schema = makeTwoVersionSchema();
    // version: '2' but missing required 'count' field
    const result = schema.safeParse({ version: '2', name: 'Quinn' });
    expect(result.status).toBe('invalid');
  });
});

// ---------------------------------------------------------------------------
// safeParse — up() throws
// ---------------------------------------------------------------------------

describe('safeParse — up() throws', () => {
  it('returns invalid when up() throws instead of crashing', () => {
    const schema = defineVersionedSchema()
      .initial('1', v1Schema)
      .version('2', v2Schema, (_v1) => {
        throw new Error('Simulated upgrade failure');
      })
      .build();

    const result = schema.safeParse({ version: '1', name: 'Rachel' });
    expect(result.status).toBe('invalid');
    if (result.status === 'invalid') {
      expect(result.reason).toContain('Simulated upgrade failure');
    }
  });

  it('does not propagate the thrown error to the caller', () => {
    const schema = defineVersionedSchema()
      .initial('1', v1Schema)
      .version('2', v2Schema, (_v1) => {
        throw new TypeError('Unexpected type');
      })
      .build();

    expect(() => schema.safeParse({ version: '1', name: 'Sam' })).not.toThrow();
  });
});

// ---------------------------------------------------------------------------
// parseJson
// ---------------------------------------------------------------------------

describe('parseJson', () => {
  it('returns null for null input', () => {
    const schema = makeTwoVersionSchema();
    expect(schema.parseJson(null)).toBeNull();
  });

  it('returns null for undefined input', () => {
    const schema = makeTwoVersionSchema();
    expect(schema.parseJson(undefined)).toBeNull();
  });

  it('returns null for empty string', () => {
    const schema = makeTwoVersionSchema();
    expect(schema.parseJson('')).toBeNull();
  });

  it('returns null for invalid JSON', () => {
    const schema = makeTwoVersionSchema();
    expect(schema.parseJson('not-json')).toBeNull();
  });

  it('returns null when the JSON is valid but the schema rejects it', () => {
    const schema = makeTwoVersionSchema();
    expect(schema.parseJson('"a string"')).toBeNull();
  });

  it('parses valid current-version JSON', () => {
    const schema = makeTwoVersionSchema();
    const data = { version: '2', name: 'Tina', count: 7 };
    expect(schema.parseJson(JSON.stringify(data))).toEqual(data);
  });

  it('parses and upgrades older-version JSON', () => {
    const schema = makeTwoVersionSchema();
    const result = schema.parseJson(JSON.stringify({ version: '1', name: 'Uma' }));
    expect(result).toEqual({ version: '2', name: 'Uma', count: 0 });
  });

  it('returns null for future-version JSON', () => {
    const schema = makeTwoVersionSchema();
    expect(
      schema.parseJson(JSON.stringify({ version: '99', name: 'Victor', count: 0 }))
    ).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// serialize and round-trip
// ---------------------------------------------------------------------------

describe('serialize', () => {
  it('produces a JSON string from a latest-version object', () => {
    const schema = makeTwoVersionSchema();
    const data = { version: '2' as const, name: 'Wendy', count: 3 };
    const serialized = schema.serialize(data);
    expect(typeof serialized).toBe('string');
    expect(JSON.parse(serialized)).toEqual(data);
  });

  it('round-trips: parseJson(serialize(data)) equals data', () => {
    const schema = makeTwoVersionSchema();
    const data = { version: '2' as const, name: 'Xavier', count: 10 };
    expect(schema.parseJson(schema.serialize(data))).toEqual(data);
  });
});

// ---------------------------------------------------------------------------
// asNested — embedding versioned schemas inside other Zod schemas
// ---------------------------------------------------------------------------

describe('asNested', () => {
  it('parses a current-version nested value transparently', () => {
    const inner = makeTwoVersionSchema();
    const outer = z.object({
      id: z.string(),
      config: inner.asNested(),
    });

    const result = outer.safeParse({
      id: 'abc',
      config: { version: '2', name: 'Yara', count: 4 },
    });
    expect(result.success).toBe(true);
    if (result.success) {
      expect(result.data.config).toEqual({ version: '2', name: 'Yara', count: 4 });
    }
  });

  it('upgrades an older nested version transparently', () => {
    const inner = makeTwoVersionSchema();
    const outer = z.object({
      id: z.string(),
      config: inner.asNested(),
    });

    const result = outer.safeParse({
      id: 'def',
      config: { version: '1', name: 'Zoe' },
    });
    expect(result.success).toBe(true);
    if (result.success) {
      expect(result.data.config).toEqual({ version: '2', name: 'Zoe', count: 0 });
    }
  });

  it('fails validation when the nested value is invalid', () => {
    const inner = makeTwoVersionSchema();
    const outer = z.object({
      id: z.string(),
      config: inner.asNested(),
    });

    const result = outer.safeParse({ id: 'ghi', config: null });
    expect(result.success).toBe(false);
  });

  it('fails validation when the nested version is from the future', () => {
    const inner = makeTwoVersionSchema();
    const outer = z.object({ config: inner.asNested() });

    const result = outer.safeParse({ config: { version: '99', name: 'A', count: 0 } });
    expect(result.success).toBe(false);
  });
});
