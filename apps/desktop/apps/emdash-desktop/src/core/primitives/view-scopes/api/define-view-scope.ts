import type { z } from 'zod';
import type { CommandDef, CommandInput, CommandOutput } from '@core/primitives/commands/api';
import { deepFreeze, type JsonObject, type JsonValue } from '@core/primitives/json/api';

const viewScopeDefSymbol = Symbol('viewScopeDef');

export type ViewScopeActivation = 'logical' | 'focus';
export type ViewScopeTrait = 'text-input' | 'editor' | 'terminal' | 'capturing';
export type CommandSource = 'keybinding' | 'palette' | 'menu' | 'programmatic';

export type ViewScopeRefArgs<TSchema extends z.ZodType<JsonObject>> =
  Record<string, never> extends z.input<TSchema>
    ? [params?: z.input<TSchema>]
    : [params: z.input<TSchema>];

export interface ViewScopeRef<
  TId extends string = string,
  TParams extends JsonObject = JsonObject,
> {
  readonly scopeId: TId;
  readonly params: TParams;
  readonly key: string;
  readonly [viewScopeDefSymbol]: ViewScopeDefinition;
}

export interface CommandPresentation {
  readonly title?: string;
  readonly description?: string;
  readonly icon?: string;
}

export interface EnabledCommand {
  readonly kind: 'enabled';
}

export interface DisabledCommand {
  readonly kind: 'disabled';
  readonly reason: string;
}

export interface HiddenCommand {
  readonly kind: 'hidden';
}

export type CommandAvailability = EnabledCommand | DisabledCommand | HiddenCommand;

export const enabled: EnabledCommand = Object.freeze({ kind: 'enabled' });
export const hidden: HiddenCommand = Object.freeze({ kind: 'hidden' });

export function disabled(reason: string): DisabledCommand {
  return Object.freeze({ kind: 'disabled', reason });
}

export interface CommandBinding<TCommand extends CommandDef = CommandDef> {
  readonly availability?: () => CommandAvailability;
  readonly presentation?: () => CommandPresentation | undefined;
  execute(input: CommandOutput<TCommand>, source: CommandSource): void;
}

export interface BoundCommand<TCommand extends CommandDef = CommandDef> {
  readonly def: TCommand;
  readonly availability: CommandAvailability;
  readonly presentation: CommandPresentation | undefined;
  execute(input: CommandInput<TCommand>, source?: CommandSource): void;
}

export interface ViewScopeHandle {
  readonly ref: ViewScopeRef;
  readonly def: ViewScopeDefinition;
  getCommand<TCommand extends CommandDef>(command: TCommand): BoundCommand<TCommand> | undefined;
}

export interface ViewScopeDefinition {
  readonly id: string;
  readonly params: z.ZodType<JsonObject>;
  readonly commands: readonly CommandDef[];
  readonly activation: ViewScopeActivation;
  readonly traits: ReadonlySet<ViewScopeTrait>;
}

export interface ViewScopeDef<
  TId extends string = string,
  TParamsSchema extends z.ZodType<JsonObject> = z.ZodType<JsonObject>,
  TCommands extends readonly CommandDef[] = readonly CommandDef[],
> {
  (...args: ViewScopeRefArgs<TParamsSchema>): ViewScopeRef<TId, z.output<TParamsSchema>>;
  readonly id: TId;
  readonly params: TParamsSchema;
  readonly commands: TCommands;
  readonly activation: ViewScopeActivation;
  readonly traits: ReadonlySet<ViewScopeTrait>;
  key(params: z.output<TParamsSchema>): string;
  safeRef(params: unknown): ViewScopeRef<TId, z.output<TParamsSchema>> | undefined;
}

export interface DefineViewScopeOptions<
  TId extends string,
  TParamsSchema extends z.ZodType<JsonObject>,
  TCommands extends readonly CommandDef[],
> {
  readonly id: TId;
  readonly params: TParamsSchema;
  readonly commands: TCommands;
  readonly activation: ViewScopeActivation;
  readonly traits?: readonly ViewScopeTrait[];
  readonly key?: (params: z.output<TParamsSchema>) => string;
}

export type ViewScopeParams<TDef> = TDef extends {
  readonly params: infer TSchema extends z.ZodType<JsonObject>;
}
  ? z.output<TSchema>
  : never;

type ViewScopeCommand<TDef extends ViewScopeDefinition> = TDef['commands'][number];

export type ViewScopeImpl<TDef extends ViewScopeDefinition> = {
  readonly [TCommand in ViewScopeCommand<TDef> as TCommand['id']]: (
    params: ViewScopeParams<TDef>
  ) => CommandBinding<TCommand>;
};

function stableJson(value: JsonValue): string {
  if (value === null || typeof value !== 'object') {
    const serialized = JSON.stringify(value);
    if (serialized === undefined) {
      throw new TypeError('Cannot serialize a non-JSON value');
    }
    return serialized;
  }
  if (Array.isArray(value)) {
    return `[${value.map(stableJson).join(',')}]`;
  }

  return `{${Object.entries(value)
    .filter((entry): entry is [string, JsonValue] => entry[1] !== undefined)
    .sort(([left], [right]) => left.localeCompare(right))
    .map(([key, nested]) => `${JSON.stringify(key)}:${stableJson(nested)}`)
    .join(',')}}`;
}

export function defineViewScope<
  const TId extends string,
  TParamsSchema extends z.ZodType<JsonObject>,
  const TCommands extends readonly CommandDef[],
>(
  options: DefineViewScopeOptions<TId, TParamsSchema, TCommands>
): ViewScopeDef<TId, TParamsSchema, TCommands> {
  if (options.id.trim().length === 0) {
    throw new Error('A view scope id must not be empty');
  }

  const commandIds = new Set<string>();
  for (const command of options.commands) {
    if (commandIds.has(command.id)) {
      throw new Error(`Duplicate command id in view scope ${options.id}: ${command.id}`);
    }
    commandIds.add(command.id);
  }

  const commands = Object.freeze([...options.commands]) as unknown as TCommands;
  const key = options.key ?? ((params: z.output<TParamsSchema>) => stableJson(params));

  const createRef = (
    parsed: z.output<TParamsSchema>
  ): ViewScopeRef<TId, z.output<TParamsSchema>> => {
    const suffix = key(parsed);
    const params = deepFreeze(parsed);
    return Object.freeze({
      scopeId: options.id,
      params,
      key: suffix.length > 0 ? `${options.id}:${suffix}` : options.id,
      [viewScopeDefSymbol]: definition,
    });
  };

  const create = (...args: ViewScopeRefArgs<TParamsSchema>) =>
    createRef(options.params.parse(args[0] === undefined ? {} : args[0]));

  const definition: ViewScopeDef<TId, TParamsSchema, TCommands> = Object.freeze(
    Object.assign(create, {
      id: options.id,
      params: options.params,
      commands,
      activation: options.activation,
      traits: Object.freeze(new Set(options.traits ?? [])),
      key,
      safeRef: (input: unknown) => {
        const parsed = options.params.safeParse(input === undefined ? {} : input);
        return parsed.success ? createRef(parsed.data) : undefined;
      },
    })
  );
  return definition;
}

export function viewScopeDefFor(ref: ViewScopeRef): ViewScopeDefinition {
  return ref[viewScopeDefSymbol];
}
