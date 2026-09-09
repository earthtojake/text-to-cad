import type { ZodType } from 'zod';

/**
 * Environment-neutral part of a settings contribution: key + schema. Shared
 * manifests aggregate this shape so both the browser and node programs can
 * derive settings types; contributions whose defaults need node APIs attach
 * them in their node surface via the full {@link SettingsContribution}.
 */
export type SettingsSchemaContribution<K extends string, T> = Readonly<{
  key: K;
  schema: ZodType<T>;
}>;

export type SettingsContribution<K extends string, T> = SettingsSchemaContribution<K, T> &
  Readonly<{
    defaults: T | (() => T);
  }>;

export type SettingsContributionMap<TSettings extends object> = {
  readonly [K in keyof TSettings]: SettingsContribution<K & string, TSettings[K]>;
};

export type SettingsValueOf<TContribution> =
  TContribution extends SettingsSchemaContribution<string, infer TValue> ? TValue : never;

export type SettingsValues<TContributions extends Record<string, unknown>> = {
  readonly [K in keyof TContributions]: SettingsValueOf<TContributions[K]>;
};

export function defineSettingsContribution<K extends string, T>(
  contribution: SettingsContribution<K, T>
): SettingsContribution<K, T> {
  return Object.freeze(contribution);
}

export function defineSettingsSchemaContribution<K extends string, T>(
  contribution: SettingsSchemaContribution<K, T>
): SettingsSchemaContribution<K, T> {
  return Object.freeze(contribution);
}
