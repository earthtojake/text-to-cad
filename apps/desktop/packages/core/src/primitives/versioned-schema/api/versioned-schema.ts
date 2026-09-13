import z from 'zod';

// ---------------------------------------------------------------------------
// Environment
// ---------------------------------------------------------------------------

// Structural declaration keeps this browser-reachable api file free of node
// ambient types; the typeof guard below already handles environments without it.
declare const process: { env: { NODE_ENV?: string } } | undefined;

/**
 * Whether to run full (dev-only) schema validation. In dev we validate stored
 * data against its declared schema to catch drift; in production we trust the
 * data was valid when written and skip validation for performance.
 *
 * Uses `process.env.NODE_ENV` so it works across Node, bundled main/renderer
 * (Vite statically replaces this), and test runners. Falls back to disabled
 * when `process` is unavailable (e.g. a browser context without a shim).
 */
function isDevMode(): boolean {
  return typeof process !== 'undefined' && process.env.NODE_ENV !== 'production';
}

// ---------------------------------------------------------------------------
// ParseResult
// ---------------------------------------------------------------------------

/**
 * Result of parsing a versioned JSON blob. The version field is read first,
 * then the matching version's schema is validated (dev only), then upgrade
 * functions run sequentially to reach the latest version.
 */
export type ParseResult<T> =
  | { status: 'ok'; data: T }
  | {
      status: 'needs-context';
      /** The version string of the data that could not be automatically upgraded. */
      version: string;
      /** The original parsed object, for callers that can supply missing context. */
      raw: unknown;
    }
  | {
      status: 'future-version';
      /** The version string that was not recognized by this version of the app. */
      version: string;
    }
  | { status: 'invalid'; reason: string };

// ---------------------------------------------------------------------------
// Internal version entry types
// ---------------------------------------------------------------------------

type AnyVersionEntry = {
  schema: z.ZodType;
  initial: boolean;
  unversioned?: boolean;
  up?: (prev: unknown) => unknown | null;
};

type VersionMap = Record<string, AnyVersionEntry>;

// ---------------------------------------------------------------------------
// VersionedSchema class
// ---------------------------------------------------------------------------

/**
 * A versioned JSON schema that handles version detection, sequential upgrades,
 * and serialization. Registered via `defineVersionedSchema()`.
 *
 * - `safeParse()` reads the version field first, validates (dev only), then
 *   runs the upgrade chain from the stored version to the latest.
 * - `parseJson()` is a convenience wrapper for DB column strings.
 * - `serialize()` always writes the latest version.
 * - `asNested()` returns a Zod schema for embedding inside other Zod objects.
 *   Note: uses `.transform()` internally, so it cannot be used with `z.encode()`.
 */
export class VersionedSchema<TLatest> {
  private readonly versionField: string;
  private readonly order: string[];
  private readonly versions: VersionMap;
  private readonly latestVersion: string;
  private readonly _schema: z.ZodType<TLatest>;
  /** The version key that accepts objects with no version field at all. */
  private readonly unversionedKey: string | undefined;

  constructor(opts: {
    versionField: string;
    order: string[];
    versions: VersionMap;
    unversionedKey?: string;
  }) {
    this.versionField = opts.versionField;
    this.order = opts.order;
    this.versions = opts.versions;
    this.unversionedKey = opts.unversionedKey;
    this.latestVersion = opts.order[opts.order.length - 1]!;
    this._schema = opts.versions[this.latestVersion]!.schema as z.ZodType<TLatest>;
  }

  /**
   * Phantom property — never accessed at runtime. Provides a convenient way
   * to infer the latest-version TypeScript type: `typeof mySchema.Type`.
   */
  get Type(): TLatest {
    return undefined as unknown as TLatest;
  }

  /** The Zod schema for the latest version. Useful for form validation or composing with other schemas. */
  get schema(): z.ZodType<TLatest> {
    return this._schema;
  }

  /** The version string of the latest registered version (e.g. `'2'`). */
  get currentVersion(): string {
    return this.latestVersion;
  }

  /**
   * Parse unknown data (already JSON-parsed). Checks the version field first,
   * then validates (in dev), then runs the upgrade chain to the latest version.
   */
  safeParse(data: unknown): ParseResult<TLatest> {
    if (typeof data !== 'object' || data === null || Array.isArray(data)) {
      return { status: 'invalid', reason: 'Data must be a non-null object' };
    }

    const record = data as Record<string, unknown>;
    const versionValue = record[this.versionField];

    // Determine which version to use.
    let resolvedVersion: string;
    if (versionValue === undefined || versionValue === null) {
      if (this.unversionedKey !== undefined) {
        resolvedVersion = this.unversionedKey;
      } else {
        return {
          status: 'invalid',
          reason: `Missing '${this.versionField}' field and no unversioned entry registered`,
        };
      }
    } else if (typeof versionValue !== 'string') {
      return {
        status: 'invalid',
        reason: `'${this.versionField}' must be a string, got ${typeof versionValue}`,
      };
    } else {
      resolvedVersion = versionValue;
    }

    const versionIndex = this.order.indexOf(resolvedVersion);
    if (versionIndex === -1) {
      return { status: 'future-version', version: resolvedVersion };
    }

    const entry = this.versions[resolvedVersion]!;

    // In dev: validate the stored data against its declared schema to catch drift.
    // In production: trust the data was valid when written, skip validation for performance.
    let current: unknown = data;
    if (isDevMode()) {
      const parsed = entry.schema.safeParse(data);
      if (!parsed.success) {
        return {
          status: 'invalid',
          reason: `Validation failed for version '${resolvedVersion}': ${parsed.error.message}`,
        };
      }
      current = parsed.data;
    }

    // Fast path: already at the latest version.
    if (resolvedVersion === this.latestVersion) {
      return { status: 'ok', data: current as TLatest };
    }

    // Run upgrade chain: resolvedVersion → resolvedVersion+1 → ... → latestVersion
    for (let i = versionIndex + 1; i < this.order.length; i++) {
      const targetVersion = this.order[i]!;
      const nextEntry = this.versions[targetVersion]!;

      if (nextEntry.initial || !nextEntry.up) {
        return {
          status: 'invalid',
          reason: `Version '${targetVersion}' is marked initial but is not the first version`,
        };
      }

      let upgraded: unknown;
      try {
        upgraded = nextEntry.up(current);
      } catch (e) {
        return {
          status: 'invalid',
          reason: `Upgrade to version '${targetVersion}' threw: ${e instanceof Error ? e.message : String(e)}`,
        };
      }

      if (upgraded === null) {
        return { status: 'needs-context', version: resolvedVersion, raw: data };
      }

      if (isDevMode()) {
        const check = nextEntry.schema.safeParse(upgraded);
        if (!check.success) {
          return {
            status: 'invalid',
            reason: `Upgrade to version '${targetVersion}' produced invalid data: ${check.error.message}`,
          };
        }
        current = check.data;
      } else {
        current = upgraded;
      }
    }

    return { status: 'ok', data: current as TLatest };
  }

  /**
   * Convenience wrapper for DB column strings. Calls `JSON.parse` then
   * `safeParse`. Returns `null` on any failure — never throws.
   */
  parseJson(raw: string | null | undefined): TLatest | null {
    if (!raw) return null;
    try {
      const result = this.safeParse(JSON.parse(raw));
      return result.status === 'ok' ? result.data : null;
    } catch {
      return null;
    }
  }

  /** Serialize a latest-version value to a JSON string for storage. */
  serialize(data: TLatest): string {
    return JSON.stringify(data);
  }

  /**
   * Returns a Zod schema that transparently runs version detection and upgrade
   * when used inside another Zod object schema. Useful for nesting versioned
   * schemas (e.g. a parent versioned schema that embeds a child versioned schema).
   *
   * @note Uses `.transform()` internally. Parent schemas containing this cannot
   * be used with `z.encode()` — writes must go through `serialize()` / `toDriver`.
   */
  asNested(): z.ZodType<TLatest> {
    return z
      .custom<unknown>((val) => {
        if (typeof val !== 'object' || val === null) return false;
        const result = this.safeParse(val);
        return result.status === 'ok' || result.status === 'needs-context';
      })
      .transform((val) => {
        const result = this.safeParse(val);
        if (result.status === 'ok') return result.data;
        // needs-context reached here — the parent's up() is responsible for handling null
        throw new Error(
          `Nested versioned schema requires context to upgrade from version '${
            result.status === 'needs-context' ? result.version : 'unknown'
          }'`
        );
      }) as unknown as z.ZodType<TLatest>;
  }
}

// ---------------------------------------------------------------------------
// Builder
// ---------------------------------------------------------------------------

type BuilderState = {
  versionField: string;
  order: string[];
  versions: VersionMap;
  unversionedKey?: string;
};

/**
 * Chainable builder returned after the first version is registered.
 *
 * @typeParam TPrev - The output type of the most recently registered version.
 * @typeParam TLatest - The output type of the most recently registered version
 *   (same as TPrev until `.version()` is called, at which point it becomes the
 *   new version's output type).
 */
export class VersionedSchemaBuilder<TPrev, TLatest> {
  constructor(private readonly state: BuilderState) {}

  /**
   * Add a new version with an upgrade function from the previous version.
   *
   * @param version - The version string (e.g. `'2'`). Must not already be registered.
   * @param schema - The Zod schema for this version.
   * @param up - Upgrade function. Receives the previous version's validated data.
   *   Return `null` to signal that upgrade requires external context (the caller
   *   receives `{ status: 'needs-context' }`).
   */
  version<TVersion extends string, TSchema extends z.ZodType>(
    version: TVersion,
    schema: TSchema,
    up: (prev: TPrev) => z.output<TSchema> | null
  ): VersionedSchemaBuilder<z.output<TSchema>, z.output<TSchema>> {
    return new VersionedSchemaBuilder({
      ...this.state,
      order: [...this.state.order, version],
      versions: {
        ...this.state.versions,
        [version]: { schema, initial: false, up: up as (prev: unknown) => unknown | null },
      },
    });
  }

  /** Finalize and return the `VersionedSchema` instance. */
  build(): VersionedSchema<TLatest> {
    return new VersionedSchema<TLatest>(this.state);
  }
}

// ---------------------------------------------------------------------------
// Entry points
// ---------------------------------------------------------------------------

/**
 * Start defining a versioned schema. Specify the field name used to store the
 * version string (defaults to `'version'`).
 *
 * @example
 * ```ts
 * const myConfig = defineVersionedSchema()
 *   .initial('1', v1Schema)
 *   .version('2', v2Schema, (v1) => ({ ...v1, version: '2', newField: 'default' }))
 *   .build();
 * ```
 */
export function defineVersionedSchema(versionField = 'version') {
  return {
    /**
     * Register the first (initial) version — data stored at this version has
     * a version field present and matching the given string.
     */
    initial<TVersion extends string, TSchema extends z.ZodType>(
      version: TVersion,
      schema: TSchema
    ): VersionedSchemaBuilder<z.output<TSchema>, z.output<TSchema>> {
      return new VersionedSchemaBuilder<z.output<TSchema>, z.output<TSchema>>({
        versionField,
        order: [version],
        versions: { [version]: { schema, initial: true } },
      });
    },

    /**
     * Register an unversioned entry for data that was written before the
     * versioning system existed (i.e. has no version field). The data is
     * treated internally as version `'0'`.
     *
     * This must be the first entry in the chain. Use `.version()` after this
     * to define upgrade paths to versioned schemas.
     *
     * @example
     * ```ts
     * const conversationConfig = defineVersionedSchema()
     *   .unversioned(v0Schema)               // existing rows: no version field
     *   .version('1', v1Schema, (v0) => ...) // first versioned release
     *   .build();
     * ```
     */
    unversioned<TSchema extends z.ZodType>(
      schema: TSchema
    ): VersionedSchemaBuilder<z.output<TSchema>, z.output<TSchema>> {
      const unversionedKey = '0';
      return new VersionedSchemaBuilder<z.output<TSchema>, z.output<TSchema>>({
        versionField,
        order: [unversionedKey],
        versions: { [unversionedKey]: { schema, initial: true, unversioned: true } },
        unversionedKey,
      });
    },
  };
}
