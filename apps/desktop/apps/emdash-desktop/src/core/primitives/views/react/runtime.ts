import type { z } from 'zod';
import type { JsonObject } from '@core/primitives/json/api';
import type { LayoutDef } from '@core/primitives/layouts/api';
import type { SlotFills } from '@core/primitives/layouts/react';
import type { Resolution } from '@core/primitives/navigation/api';
import type { ViewParams } from '@core/primitives/views/api';

export interface RuntimeViewDef {
  readonly id: string;
  readonly params: z.ZodType<JsonObject>;
  readonly layout: LayoutDef;
}

export interface ViewRuntime<TDef extends RuntimeViewDef = RuntimeViewDef> {
  readonly slots: SlotFills<TDef['layout'], ViewParams<TDef>>;
  readonly resolve?: (params: ViewParams<TDef>) => Resolution;
}

export interface ViewRuntimeContribution<TDef extends RuntimeViewDef = RuntimeViewDef> {
  readonly def: TDef;
  readonly runtime: ViewRuntime<TDef>;
}

export function defineViewRuntime<TDef extends RuntimeViewDef>(
  def: TDef,
  runtime: ViewRuntime<TDef>
): ViewRuntimeContribution<TDef> {
  return Object.freeze({ def, runtime: Object.freeze(runtime) });
}

const runtimes = new Map<string, ViewRuntimeContribution>();

interface RegistrableViewRuntime {
  readonly def: { readonly id: string };
  readonly runtime: object;
}

export function registerViewRuntime(contribution: RegistrableViewRuntime): void {
  if (runtimes.has(contribution.def.id)) {
    throw new Error(`Duplicate view runtime: ${contribution.def.id}`);
  }
  runtimes.set(
    contribution.def.id,
    contribution as unknown as ViewRuntimeContribution<RuntimeViewDef>
  );
}

export function getViewRuntime(viewId: string): ViewRuntimeContribution | undefined {
  return runtimes.get(viewId);
}

export function assertViewRuntimesComplete(catalog: {
  readonly defs: readonly { readonly id: string }[];
}): void {
  const missing = catalog.defs
    .filter((definition) => !runtimes.has(definition.id))
    .map((definition) => definition.id);
  if (missing.length > 0) {
    throw new Error(`Missing view runtimes: ${missing.join(', ')}`);
  }
}
