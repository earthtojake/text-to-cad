import { comparer, observable, runInAction } from 'mobx';
import type {
  ChromeCommand,
  ChromeCommands,
  ChromeStoreDefinition,
} from '@core/primitives/chrome-stores/api';
import type { MementoHandle, SubjectSpace } from '@core/primitives/mementos/browser';

/** Maps each defined command to its dispatcher (command args minus the context). */
export type ChromeStoreCommands<TCommands> = {
  readonly [K in keyof TCommands]: TCommands[K] extends (
    current: never,
    ...args: infer TArgs
  ) => unknown
    ? (...args: TArgs) => void
    : never;
};

export interface ChromeStore<
  TState,
  TEphemeral extends Record<string, unknown>,
  TCommands extends ChromeCommands<TState, TEphemeral>,
> {
  /** The persisted chrome state (observable). Read-only: mutate via `commands`. */
  readonly state: Readonly<TState>;
  /** Ephemeral, never-persisted observable fields. Set only inside commands. */
  readonly ephemeral: Readonly<TEphemeral>;
  /** Named command dispatchers — the only mutation path. */
  readonly commands: ChromeStoreCommands<TCommands>;
  /** Durably saves any pending debounced write (delegates to the memento handle). */
  flush(): Promise<void>;
}

/**
 * Binds a chrome-store definition to one subject. The instance reads from an
 * already-hydrated memento — callers render below the `space.isHydrated`
 * gate — and every command result writes through the normal debounced
 * memento path. Reading state or dispatching before hydration is a dev-mode
 * assertion failure so a missing gate is a loud bug, never a silent reset.
 */
export function createChromeStore<
  TState,
  TEphemeral extends Record<string, unknown>,
  TCommands extends ChromeCommands<TState, TEphemeral>,
  TKind extends string,
>(
  definition: ChromeStoreDefinition<TState, TEphemeral, TCommands, TKind>,
  space: SubjectSpace<TKind>
): ChromeStore<TState, TEphemeral, TCommands> {
  return new SubjectChromeStore(definition, space);
}

class SubjectChromeStore<
  TState,
  TEphemeral extends Record<string, unknown>,
  TCommands extends ChromeCommands<TState, TEphemeral>,
  TKind extends string,
> implements ChromeStore<TState, TEphemeral, TCommands> {
  readonly commands: ChromeStoreCommands<TCommands>;
  private readonly handle: MementoHandle<TState>;
  private readonly ephemeralValues: TEphemeral;

  constructor(
    private readonly definition: ChromeStoreDefinition<TState, TEphemeral, TCommands, TKind>,
    private readonly space: SubjectSpace<TKind>
  ) {
    this.handle = space.handle(definition.memento);
    // Cloned per instance so stores never share ephemeral state through the
    // definition's default object; shallow observability keeps fields refs.
    this.ephemeralValues = observable({ ...definition.ephemeral }, {}, { deep: false });
    const dispatchers: Record<string, (...args: never[]) => void> = {};
    for (const [name, command] of Object.entries(definition.commands)) {
      dispatchers[name] = (...args) => this.dispatch(name, command, args);
    }
    this.commands = Object.freeze(dispatchers) as ChromeStoreCommands<TCommands>;
  }

  get state(): Readonly<TState> {
    this.assertHydrated('was read');
    return this.handle.value;
  }

  get ephemeral(): Readonly<TEphemeral> {
    return this.ephemeralValues;
  }

  async flush(): Promise<void> {
    await this.handle.flush();
  }

  private dispatch(
    name: string,
    command: ChromeCommand<TState, TEphemeral, never[]>,
    args: never[]
  ): void {
    this.assertHydrated(`dispatched command '${name}'`);
    const result = command({ state: this.handle.value, ephemeral: this.ephemeralValues }, ...args);
    if (!result) return;
    runInAction(() => {
      if (result.state !== undefined && !comparer.structural(result.state, this.handle.value)) {
        this.handle.update(result.state);
      }
      if (result.ephemeral !== undefined) Object.assign(this.ephemeralValues, result.ephemeral);
    });
  }

  private assertHydrated(action: string): void {
    if (!import.meta.env.DEV || this.space.isHydrated) return;
    throw new Error(
      `Chrome store '${this.definition.memento.id}' ${action} before its subject space hydrated; ` +
        'render below the space.isHydrated gate'
    );
  }
}
