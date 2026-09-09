import { z } from 'zod';
import type { Keybinding } from '@core/primitives/keybindings/api';

declare const commandDefBrand: unique symbol;

export interface CommandDef<TId extends string = string, TInput extends z.ZodType = z.ZodType> {
  readonly id: TId;
  readonly title: string;
  readonly description: string | undefined;
  readonly category: string;
  readonly icon: string | undefined;
  readonly input: TInput;
  readonly keybinding: Keybinding | undefined;
  readonly [commandDefBrand]: TId;
}

export interface DefineCommandOptions<TId extends string, TInput extends z.ZodType> {
  readonly id: TId;
  readonly title: string;
  readonly description?: string;
  readonly category: string;
  readonly icon?: string;
  readonly input?: TInput;
  readonly keybinding?: Keybinding;
}

export function defineCommand<const TId extends string, TInput extends z.ZodType = z.ZodVoid>(
  options: DefineCommandOptions<TId, TInput>
): CommandDef<TId, TInput> {
  if (options.id.trim().length === 0) {
    throw new Error('A command id must not be empty');
  }

  return Object.freeze({
    id: options.id,
    title: options.title,
    description: options.description,
    category: options.category,
    icon: options.icon,
    input: options.input ?? z.void(),
    keybinding: options.keybinding,
  }) as CommandDef<TId, TInput>;
}

export type CommandInput<TDef> = TDef extends {
  readonly input: infer TInput extends z.ZodType;
}
  ? z.input<TInput>
  : never;

export type CommandOutput<TDef> = TDef extends {
  readonly input: infer TInput extends z.ZodType;
}
  ? z.output<TInput>
  : never;
