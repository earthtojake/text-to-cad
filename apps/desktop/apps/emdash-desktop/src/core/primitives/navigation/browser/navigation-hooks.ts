import { useObserver } from 'mobx-react-lite';
import { Fragment, useCallback, type ComponentType, type ReactNode } from 'react';
import type { z } from 'zod';
import type { JsonObject } from '@core/primitives/json/api';
import type { ViewParams, ViewRef } from '@core/primitives/views/api';
import { getViewRuntime } from '@core/primitives/views/react';
import { getNavigation } from './navigation-selectors';

export type NavigateFnTyped = (ref: ViewRef) => void;

/** Structural slice of a view definition the params hooks operate on. */
export interface NavigationViewDefinition {
  readonly id: string;
  readonly params: z.ZodType<JsonObject>;
  safeRef(params: unknown): ViewRef | undefined;
}

export type SlotsContextValue = {
  WrapView: ComponentType<{ children: ReactNode } & Record<string, unknown>>;
  TitlebarSlot: ComponentType;
  MainPanel: ComponentType;
  currentView: string;
};

export type WorkspaceViewParamsValue = {
  params: Record<string, unknown>;
};

const EmptyTitlebar = () => null;

export function useNavigate(): { navigate: NavigateFnTyped } {
  const navigate = useCallback((ref: ViewRef) => {
    getNavigation().navigate(ref);
  }, []);
  return { navigate };
}

export function useWorkspaceSlots(): SlotsContextValue {
  return useObserver(() => {
    const viewId = getNavigation().currentViewId;
    const contribution = getViewRuntime(viewId) ?? getViewRuntime('home');
    if (!contribution) throw new Error('Home view runtime is not registered');
    const slots = contribution.runtime.slots as unknown as {
      wrap?: ComponentType<{ children: ReactNode } & Record<string, unknown>>;
      titlebar?: ComponentType;
      main: ComponentType;
    };
    return {
      WrapView: slots.wrap ?? Fragment,
      TitlebarSlot: slots.titlebar ?? EmptyTitlebar,
      MainPanel: slots.main,
      currentView: contribution.def.id,
    };
  });
}

export function useWorkspaceViewParams(): WorkspaceViewParamsValue {
  return useObserver(() => ({
    params: getNavigation().currentRef.params,
  }));
}

export function useViewParams<TDef extends NavigationViewDefinition>(
  definition: TDef
): ViewParams<TDef> | undefined {
  return useObserver(() => {
    const navigation = getNavigation();
    const current = navigation.currentRef;
    const ref = current.viewId === definition.id ? current : navigation.lastRefFor(definition);
    return ref?.params as ViewParams<TDef> | undefined;
  });
}

/**
 * Returns current params while the view is active and its last recorded params
 * during an unmount transition. `setParams` is a no-op when the view is not current.
 */
export function useCurrentViewParams<TDef extends NavigationViewDefinition>(
  definition: TDef
): {
  params: ViewParams<TDef>;
  setParams: (
    update: Partial<ViewParams<TDef>> | ((previous: ViewParams<TDef>) => ViewParams<TDef>)
  ) => void;
} {
  const setParams = useCallback(
    (update: Partial<ViewParams<TDef>> | ((previous: ViewParams<TDef>) => ViewParams<TDef>)) => {
      const current = getNavigation().currentRef;
      if (current.viewId !== definition.id) return;
      const previous = current.params as ViewParams<TDef>;
      const next = typeof update === 'function' ? update(previous) : { ...previous, ...update };
      const ref = definition.safeRef(next);
      if (ref) getNavigation().navigate(ref);
    },
    [definition]
  );

  return useObserver(() => {
    const navigation = getNavigation();
    const current = navigation.currentRef;
    const ref = current.viewId === definition.id ? current : navigation.lastRefFor(definition);
    if (!ref) throw new Error(`No params have been recorded for view '${definition.id}'`);
    return {
      params: ref.params as ViewParams<TDef>,
      setParams,
    };
  });
}

export function isCurrentView(currentView: string | null | undefined, target: string): boolean {
  return currentView === target;
}
