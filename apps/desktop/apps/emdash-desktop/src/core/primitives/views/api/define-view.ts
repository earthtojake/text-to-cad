import type { z } from 'zod';
import { deepFreeze, type JsonObject, type JsonValue } from '@core/primitives/json/api';
import type { LayoutDef } from '@core/primitives/layouts/api';
import type { Subject } from '@core/primitives/subjects/api';
import type { ViewScopeRef } from '@core/primitives/view-scopes/api';

declare const viewRefBrand: unique symbol;

export type ViewTrait = 'library';

export type RefArgs<TSchema extends z.ZodType<JsonObject>> =
  Record<string, never> extends z.input<TSchema>
    ? [params?: z.input<TSchema>]
    : [params: z.input<TSchema>];

export interface ViewRef<TId extends string = string, TParams extends JsonObject = JsonObject> {
  readonly viewId: TId;
  readonly params: TParams;
  readonly key: string;
  readonly [viewRefBrand]: TId;
}

export interface LocationContract<TSchema extends z.ZodType<JsonValue>> {
  readonly schema: TSchema;
  readonly key: (location: z.output<TSchema>) => string;
}

export interface ViewDef<
  TId extends string,
  TParamsSchema extends z.ZodType<JsonObject>,
  TLayout extends LayoutDef,
  TLocationSchema extends z.ZodType<JsonValue> = z.ZodNever,
  TTelemetryEvent extends string = string,
> {
  (...args: RefArgs<TParamsSchema>): ViewRef<TId, z.output<TParamsSchema>>;
  readonly id: TId;
  readonly params: TParamsSchema;
  readonly layout: TLayout;
  readonly traits: ReadonlySet<ViewTrait>;
  readonly telemetryEvent: TTelemetryEvent | undefined;
  readonly historyKey: (params: z.output<TParamsSchema>) => string;
  readonly subject: ((params: z.output<TParamsSchema>) => Subject) | undefined;
  readonly scope: ((params: z.output<TParamsSchema>) => ViewScopeRef) | undefined;
  readonly location: LocationContract<TLocationSchema> | undefined;
  safeRef(params: unknown): ViewRef<TId, z.output<TParamsSchema>> | undefined;
}

export interface DefineViewOptions<
  TId extends string,
  TParamsSchema extends z.ZodType<JsonObject>,
  TLayout extends LayoutDef,
  TLocationSchema extends z.ZodType<JsonValue>,
  TTelemetryEvent extends string,
> {
  readonly id: TId;
  readonly params: TParamsSchema;
  readonly layout: TLayout;
  readonly traits?: readonly ViewTrait[];
  readonly telemetryEvent?: TTelemetryEvent;
  readonly historyKey?: (params: z.output<TParamsSchema>) => string;
  readonly subject?: (params: z.output<TParamsSchema>) => Subject;
  readonly scope?: (params: z.output<TParamsSchema>) => ViewScopeRef;
  readonly location?: LocationContract<TLocationSchema>;
}

export function defineView<
  const TId extends string,
  TParamsSchema extends z.ZodType<JsonObject>,
  TLayout extends LayoutDef,
  TLocationSchema extends z.ZodType<JsonValue> = z.ZodNever,
  const TTelemetryEvent extends string = string,
>(
  options: DefineViewOptions<TId, TParamsSchema, TLayout, TLocationSchema, TTelemetryEvent>
): ViewDef<TId, TParamsSchema, TLayout, TLocationSchema, TTelemetryEvent> {
  if (options.id.trim().length === 0) {
    throw new Error('A view id must not be empty');
  }

  const historyKey = options.historyKey ?? (() => '');

  const createRef = (parsed: z.output<TParamsSchema>): ViewRef<TId, z.output<TParamsSchema>> => {
    const suffix = historyKey(parsed);
    const params = deepFreeze(parsed);
    return Object.freeze({
      viewId: options.id,
      params,
      key: suffix.length > 0 ? `${options.id}:${suffix}` : options.id,
    }) as ViewRef<TId, z.output<TParamsSchema>>;
  };

  const create = (...args: RefArgs<TParamsSchema>) =>
    createRef(options.params.parse(args[0] === undefined ? {} : args[0]));

  return Object.freeze(
    Object.assign(create, {
      id: options.id,
      params: options.params,
      layout: options.layout,
      traits: Object.freeze(new Set(options.traits ?? [])),
      telemetryEvent: options.telemetryEvent,
      historyKey,
      subject: options.subject,
      scope: options.scope,
      location: options.location,
      safeRef: (input: unknown) => {
        const parsed = options.params.safeParse(input === undefined ? {} : input);
        return parsed.success ? createRef(parsed.data) : undefined;
      },
    })
  );
}

export type ViewParams<TDef> = TDef extends {
  readonly params: infer TSchema extends z.ZodType<JsonObject>;
}
  ? z.output<TSchema>
  : never;

export type ViewLocation<TDef> = TDef extends {
  readonly location: LocationContract<infer TSchema extends z.ZodType<JsonValue>> | undefined;
}
  ? z.output<TSchema>
  : never;
