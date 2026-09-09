import type { VersionedSchema } from '@emdash/core/primitives/versioned-schema/api';
import type { z } from 'zod';
import type { SubjectDef } from '@core/primitives/subjects/api';

export const DEFAULT_PERSISTED_MAX_AGE = days(60);
export const DEFAULT_PERSISTED_MAX_ENTRIES = 500;
export const DEFAULT_TRANSIENT_MAX_ENTRIES = 1_000;

export interface PersistedMementoRetention {
  readonly tier: 'persisted';
  readonly maxAge: number;
  readonly maxEntries: number;
}

export interface TransientMementoRetention {
  readonly tier: 'transient';
  readonly maxEntries: number;
}

export type MementoRetention = PersistedMementoRetention | TransientMementoRetention;

export interface MementoDef<TValue, TSubject extends SubjectDef<string, z.ZodType>> {
  readonly id: string;
  readonly subject: TSubject;
  readonly schema: VersionedSchema<TValue>;
  readonly default: TValue;
  readonly retention: MementoRetention;
}

export interface DefineMementoOptions<TValue, TSubject extends SubjectDef<string, z.ZodType>> {
  readonly id: string;
  readonly subject: TSubject;
  readonly schema: VersionedSchema<TValue>;
  readonly default: TValue;
  readonly retention?:
    | {
        readonly tier: 'persisted';
        readonly maxAge?: number;
        readonly maxEntries?: number;
      }
    | {
        readonly tier: 'transient';
        readonly maxEntries?: number;
      };
}

export function days(value: number): number {
  return value * 24 * 60 * 60 * 1_000;
}

export function defineMemento<TValue, TSubject extends SubjectDef<string, z.ZodType>>(
  options: DefineMementoOptions<TValue, TSubject>
): MementoDef<TValue, TSubject> {
  if (options.id.trim().length === 0) {
    throw new Error('A memento id must not be empty');
  }

  const retention = options.retention ?? { tier: 'persisted' as const };
  const normalizedRetention: MementoRetention =
    retention.tier === 'persisted'
      ? {
          tier: 'persisted',
          maxAge:
            retention.maxAge ?? options.subject.retention?.maxAge ?? DEFAULT_PERSISTED_MAX_AGE,
          maxEntries:
            retention.maxEntries ??
            options.subject.retention?.maxEntries ??
            DEFAULT_PERSISTED_MAX_ENTRIES,
        }
      : {
          tier: 'transient',
          maxEntries:
            retention.maxEntries ??
            options.subject.retention?.maxEntries ??
            DEFAULT_TRANSIENT_MAX_ENTRIES,
        };

  return Object.freeze({
    id: options.id,
    subject: options.subject,
    schema: options.schema,
    default: options.default,
    retention: normalizedRetention,
  });
}

export type MementoValue<TDef extends MementoDef<unknown, SubjectDef<string, z.ZodType>>> =
  TDef extends MementoDef<infer TValue, SubjectDef<string, z.ZodType>> ? TValue : never;
