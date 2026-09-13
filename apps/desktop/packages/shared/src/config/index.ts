import { readFileSync } from 'node:fs';
import { parseEnv } from 'node:util';
import type { z } from 'zod';
import { err, ok, type Result } from '../result/index';

export type ConfigError = {
  type: 'args' | 'env-file' | 'validation';
  message: string;
  path?: string;
};

export type ConfigLayer = Record<string, unknown>;

export type ConfigArgOption = {
  type: 'boolean' | 'string';
  key?: string | false;
  optionalValue?: boolean;
  whenPresent?: ConfigLayer;
  group?: string;
};

export type ConfigArgsOptions = {
  options: Record<string, ConfigArgOption>;
  allowPositionals?: boolean;
};

export type ParseConfigOptions<Schema extends z.ZodTypeAny> = {
  schema: Schema;
  argv?: string[];
  env?: NodeJS.ProcessEnv;
  envPrefix?: string;
  envFiles?: readonly string[];
  defaults?: ConfigLayer;
  args?: ConfigArgsOptions;
};

type ParsedArgs = {
  layer: ConfigLayer;
  seenGroups: Map<string, string>;
};

export function parseConfig<Schema extends z.ZodTypeAny>(
  options: ParseConfigOptions<Schema>
): Result<z.output<Schema>, ConfigError> {
  const envFileLayer = readEnvFileLayer(options.envFiles ?? [], options.envPrefix);
  if (!envFileLayer.success) return envFileLayer;

  const argsLayer = readArgLayer(options.argv ?? process.argv.slice(2), options.args);
  if (!argsLayer.success) return argsLayer;

  const parsed = options.schema.safeParse({
    ...stripUndefined(options.defaults ?? {}),
    ...envFileLayer.data,
    ...readEnvLayer(options.env ?? process.env, options.envPrefix),
    ...argsLayer.data,
  });

  if (!parsed.success) {
    return err({
      type: 'validation',
      message: formatZodError(parsed.error),
    });
  }

  return ok(parsed.data);
}

export function formatConfigError(error: ConfigError): string {
  const path = error.path === undefined ? '' : ` (${error.path})`;
  return `Invalid config${path}: ${error.message}`;
}

function readEnvFileLayer(
  paths: readonly string[],
  prefix: string | undefined
): Result<ConfigLayer, ConfigError> {
  const layer: ConfigLayer = {};

  for (const path of paths) {
    const file = readEnvFile(path);
    if (!file.success) return file;
    Object.assign(layer, readEnvLayer(file.data, prefix));
  }

  return ok(layer);
}

function readEnvFile(path: string): Result<NodeJS.ProcessEnv, ConfigError> {
  try {
    return ok(parseEnv(readFileSync(path, 'utf8')));
  } catch (error) {
    if (isMissingFileError(error)) return ok({});
    return err({
      type: 'env-file',
      path,
      message: error instanceof Error ? error.message : String(error),
    });
  }
}

function readEnvLayer(env: NodeJS.ProcessEnv, prefix: string | undefined): ConfigLayer {
  const layer: ConfigLayer = {};

  for (const [name, value] of Object.entries(env)) {
    if (value === undefined) continue;
    if (prefix !== undefined && !name.startsWith(prefix)) continue;

    const key = prefix === undefined ? name : name.slice(prefix.length);
    if (key.length === 0) continue;
    layer[envNameToConfigKey(key)] = value;
  }

  return layer;
}

function readArgLayer(
  argv: string[],
  options: ConfigArgsOptions | undefined
): Result<ConfigLayer, ConfigError> {
  if (options === undefined) {
    return argv.length === 0
      ? ok({})
      : err({ type: 'args', message: `Unexpected argument '${argv[0]}'` });
  }

  const parsed: ParsedArgs = {
    layer: {},
    seenGroups: new Map(),
  };

  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];

    if (!arg.startsWith('--')) {
      if (options.allowPositionals) continue;
      return err({ type: 'args', message: `Unexpected positional argument '${arg}'` });
    }

    const result = readOption(argv, index, options, parsed);
    if (!result.success) return result;
    index = result.data;
  }

  return ok(parsed.layer);
}

function readOption(
  argv: string[],
  index: number,
  options: ConfigArgsOptions,
  parsed: ParsedArgs
): Result<number, ConfigError> {
  const arg = argv[index];
  const equalsIndex = arg.indexOf('=');
  const name = equalsIndex === -1 ? arg.slice(2) : arg.slice(2, equalsIndex);
  const inlineValue = equalsIndex === -1 ? undefined : arg.slice(equalsIndex + 1);
  const option = options.options[name];

  if (option === undefined) {
    return err({ type: 'args', message: `Unknown option '--${name}'` });
  }

  const groupResult = checkOptionGroup(name, option, parsed);
  if (!groupResult.success) return groupResult;

  Object.assign(parsed.layer, option.whenPresent);

  if (option.type === 'boolean') {
    if (inlineValue !== undefined) {
      return err({ type: 'args', message: `Option '--${name}' does not take a value` });
    }
    setOptionValue(parsed.layer, name, option, true);
    return ok(index);
  }

  if (inlineValue !== undefined) {
    setOptionValue(parsed.layer, name, option, inlineValue);
    return ok(index);
  }

  const next = argv[index + 1];
  if (next !== undefined && !next.startsWith('--')) {
    setOptionValue(parsed.layer, name, option, next);
    return ok(index + 1);
  }

  if (option.optionalValue) {
    return ok(index);
  }

  return err({ type: 'args', message: `Option '--${name}' requires a value` });
}

function checkOptionGroup(
  name: string,
  option: ConfigArgOption,
  parsed: ParsedArgs
): Result<void, ConfigError> {
  if (option.group === undefined) return ok();

  const seen = parsed.seenGroups.get(option.group);
  if (seen !== undefined && seen !== name) {
    return err({
      type: 'args',
      message: `Use either --${seen} or --${name}, not both`,
    });
  }

  parsed.seenGroups.set(option.group, name);
  return ok();
}

function setOptionValue(
  layer: ConfigLayer,
  optionName: string,
  option: ConfigArgOption,
  value: string | boolean
): void {
  if (option.key === false) return;
  layer[option.key ?? argNameToConfigKey(optionName)] = value;
}

function envNameToConfigKey(name: string): string {
  return name.toLowerCase().replace(/_([a-z0-9])/g, (_, value: string) => value.toUpperCase());
}

function argNameToConfigKey(name: string): string {
  return name.replace(/-([a-z0-9])/g, (_, value: string) => value.toUpperCase());
}

function stripUndefined(value: ConfigLayer): ConfigLayer {
  return Object.fromEntries(Object.entries(value).filter(([, entry]) => entry !== undefined));
}

function formatZodError(error: z.ZodError): string {
  return error.issues
    .map((issue) => {
      const path = issue.path.join('.') || 'config';
      return `${path}: ${issue.message}`;
    })
    .join('; ');
}

function isMissingFileError(error: unknown): boolean {
  return (
    error instanceof Error && 'code' in error && (error as NodeJS.ErrnoException).code === 'ENOENT'
  );
}
