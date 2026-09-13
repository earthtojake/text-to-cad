import type { LayoutStorage } from '@emdash/ui/react/primitives';
import type { z } from 'zod';
import type { MementoDef } from '@core/primitives/mementos/api';
import type { SubjectDef } from '@core/primitives/subjects/api';
import type { SubjectSpace } from './memento-client';

/**
 * Value shape shared by every panel-layouts memento (`tasks.panel-layouts`,
 * `projects.panel-layouts`): one document per subject mapping the
 * react-resizable-panels internal storage key
 * (`react-resizable-panels:${id}[:${panelIds}]`) to its serialized layout.
 */
export interface PanelLayoutsState {
  version: '1';
  layouts: Record<string, string>;
}

/**
 * The `LayoutStorage` contract from `@emdash/ui` plus pane-group cleanup:
 * `deleteEntry` removes one stored layout when its pane group is destroyed,
 * so a later re-split starts fresh from defaults.
 */
export interface MementoLayoutStorage extends LayoutStorage {
  deleteEntry(key: string): void;
}

/**
 * Synchronous facade over an already-hydrated panel-layouts memento, injected
 * into `useCollapsiblePanelBinding` / `useDefaultLayout` as their `storage`.
 *
 * `getItem` is called on every render via `useSyncExternalStore`, so it must
 * be fast and value-stable: it is a plain property read of the serialized
 * string kept in the memento value, and the memento parser is
 * content-memoized, so unchanged layouts yield identical strings across the
 * authoritative persistence echo. `setItem` writes through the normal
 * debounced memento path.
 *
 * Consumers must render below the subject space's `isHydrated` gate. Any
 * access before hydration throws in dev — a missing gate must be a loud bug,
 * never a silent layout reset — and in production logs and falls through to
 * the in-memory value.
 */
export function createLayoutStorage<TKind extends string>(
  space: SubjectSpace<TKind>,
  definition: MementoDef<PanelLayoutsState, SubjectDef<TKind, z.ZodType>>
): MementoLayoutStorage {
  const handle = space.handle(definition);

  const guardHydrated = (method: string, key: string): void => {
    if (space.isHydrated) return;
    const message =
      `LayoutStorage.${method}('${key}') on memento '${definition.id}' before subject ` +
      `'${space.subject.kind}:${space.subject.key}' hydrated. Render below the space's ` +
      `isHydrated gate; reading pre-hydration would silently reset the persisted layout.`;
    if (import.meta.env.DEV) throw new Error(message);
    console.error(message);
  };

  return {
    getItem(key: string): string | null {
      guardHydrated('getItem', key);
      return handle.value.layouts[key] ?? null;
    },

    setItem(key: string, value: string): void {
      guardHydrated('setItem', key);
      handle.update((current) => ({
        ...current,
        layouts: { ...current.layouts, [key]: value },
      }));
    },

    deleteEntry(key: string): void {
      guardHydrated('deleteEntry', key);
      if (!(key in handle.value.layouts)) return;
      handle.update((current) => {
        const layouts = { ...current.layouts };
        delete layouts[key];
        return { ...current, layouts };
      });
    },
  };
}
