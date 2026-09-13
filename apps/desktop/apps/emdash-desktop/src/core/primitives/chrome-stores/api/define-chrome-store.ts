/**
 * Chrome command stores: one plain state object per subject, persisted as one
 * memento document, mutated only through named commands.
 *
 * A definition binds a versioned memento document to a set of commands — pure
 * functions over the state object, DOM-free and testable without React.
 * Commands are the only mutation path: invariants live inside them, and call
 * sites get no partial setter access. Commands may also set ephemeral
 * (non-persisted, observable) fields, which have no other write path.
 *
 * Example — a two-command store where `openSidebarTab` enforces the
 * "opening a sidebar tab ⇒ sidebar expanded" invariant in one place:
 *
 * ```ts
 * const chromeStore = defineChromeStore({
 *   memento: defineMemento({
 *     id: 'tasks.chrome',
 *     subject: taskSubject,
 *     schema: chromeSchema, // defineVersionedSchema() per repo conventions
 *     default: { version: '1', sidebarCollapsed: true, sidebarTab: 'changes' },
 *   }),
 *   ephemeral: { focusedRegion: undefined as 'sidebar' | undefined },
 *   commands: {
 *     toggleSidebar: ({ state }) => ({
 *       state: { ...state, sidebarCollapsed: !state.sidebarCollapsed },
 *     }),
 *     // Invariant: selecting a tab always expands the sidebar.
 *     openSidebarTab: ({ state }, tab: 'changes' | 'files') => ({
 *       state: { ...state, sidebarTab: tab, sidebarCollapsed: false },
 *       ephemeral: { focusedRegion: 'sidebar' as const },
 *     }),
 *   },
 * });
 * ```
 *
 * Definitions are runtime-independent. Instantiate one per subject with
 * `createChromeStore(definition, space)` from
 * `@core/primitives/chrome-stores/browser`, where `space` is a `SubjectSpace`
 * rendered below a hydration gate (`space.isHydrated`).
 */
import type { z } from 'zod';
import type { MementoDef } from '@core/primitives/mementos/api';
import type { SubjectDef } from '@core/primitives/subjects/api';

export interface ChromeCommandContext<TState, TEphemeral> {
  readonly state: Readonly<TState>;
  readonly ephemeral: Readonly<TEphemeral>;
}

/**
 * What a command returns. Omitted (or `undefined`) members leave that side
 * untouched; returning nothing at all makes the command a no-op.
 */
export interface ChromeCommandResult<TState, TEphemeral> {
  readonly state?: TState;
  readonly ephemeral?: Partial<TEphemeral>;
}

export type ChromeCommand<TState, TEphemeral, TArgs extends readonly unknown[]> = (
  current: ChromeCommandContext<TState, TEphemeral>,
  ...args: TArgs
) => ChromeCommandResult<TState, TEphemeral> | undefined | void;

export type ChromeCommands<TState, TEphemeral> = Record<
  string,
  ChromeCommand<TState, TEphemeral, never[]>
>;

export interface ChromeStoreDefinition<
  TState,
  TEphemeral extends Record<string, unknown>,
  TCommands extends ChromeCommands<TState, TEphemeral>,
  TKind extends string,
> {
  readonly memento: MementoDef<TState, SubjectDef<TKind, z.ZodType>>;
  /** Default values for the ephemeral (never persisted) fields. */
  readonly ephemeral: TEphemeral;
  readonly commands: TCommands;
}

export function defineChromeStore<
  TState,
  TEphemeral extends Record<string, unknown>,
  TCommands extends ChromeCommands<TState, TEphemeral>,
  TKind extends string,
>(
  definition: ChromeStoreDefinition<TState, TEphemeral, TCommands, TKind>
): ChromeStoreDefinition<TState, TEphemeral, TCommands, TKind> {
  return Object.freeze({
    memento: definition.memento,
    ephemeral: definition.ephemeral,
    commands: Object.freeze({ ...definition.commands }),
  });
}
