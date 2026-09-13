import {
  createContext,
  createElement,
  useCallback,
  useContext,
  useLayoutEffect,
  useRef,
  useState,
  type ReactNode,
  type RefCallback,
} from 'react';
import type { JsonObject } from '@core/primitives/json/api';
import type {
  CommandBinding,
  ViewScopeDefinition,
  ViewScopeImpl,
  ViewScopeRef,
} from '@core/primitives/view-scopes/api';
import { enabled, viewScopeDefFor } from '@core/primitives/view-scopes/api';
import {
  scopes,
  type ViewScopeInstance,
  type ViewScopes,
} from '@core/primitives/view-scopes/browser';
import { assertImplHasAllCommands } from '@core/primitives/view-scopes/browser/implementation-validation';

const ViewScopeInstanceContext = createContext<ViewScopeInstance | undefined>(undefined);

type BindingFactory = (params: JsonObject) => CommandBinding;
type ErasedViewScopeImpl = Readonly<Record<string, BindingFactory>>;

function createDelegatingImplementation<TDef extends ViewScopeDefinition>(
  definition: ViewScopeDefinition,
  getImplementation: () => ViewScopeImpl<TDef>
): ViewScopeImpl<TDef> {
  const delegated: Record<string, BindingFactory> = {};
  for (const command of definition.commands) {
    delegated[command.id] = (params) => {
      let boundImplementation: ViewScopeImpl<TDef> | undefined;
      let binding: CommandBinding | undefined;
      const currentBinding = (): CommandBinding => {
        const implementation = getImplementation();
        if (boundImplementation !== implementation) {
          boundImplementation = implementation;
          const factory = (boundImplementation as unknown as ErasedViewScopeImpl)[command.id];
          if (!factory) {
            throw new Error(`Missing command binding ${command.id} in view scope ${definition.id}`);
          }
          binding = factory(params);
        }
        if (!binding) {
          throw new Error(`Failed to bind command ${command.id} in view scope ${definition.id}`);
        }
        return binding;
      };
      return {
        availability: () => currentBinding().availability?.() ?? enabled,
        presentation: () => currentBinding().presentation?.(),
        execute: (input, source) => currentBinding().execute(input, source),
      };
    };
  }
  return delegated as unknown as ViewScopeImpl<TDef>;
}

export interface ViewScopeInstanceProviderProps {
  readonly instance: ViewScopeInstance | undefined;
  readonly children?: ReactNode;
}

export function ViewScopeInstanceProvider({ instance, children }: ViewScopeInstanceProviderProps) {
  return createElement(ViewScopeInstanceContext.Provider, { value: instance }, children);
}

export function useViewScopeInstance(): ViewScopeInstance | undefined {
  return useContext(ViewScopeInstanceContext);
}

export function useFocusDelegate<TElement extends HTMLElement>(): RefCallback<TElement> {
  const instance = useViewScopeInstance();
  return useCallback(
    (element) => {
      instance?.attachFocusDelegate(element);
    },
    [instance]
  );
}

export interface UseViewScopeResult {
  readonly instance: ViewScopeInstance | undefined;
  readonly attachRef: RefCallback<HTMLElement>;
}

export function useViewScope<TDef extends ViewScopeDefinition>(
  ref: ViewScopeRef,
  implementation: ViewScopeImpl<TDef>,
  runtime: ViewScopes = scopes
): UseViewScopeResult {
  const parent = useContext(ViewScopeInstanceContext);
  const [instance, setInstance] = useState<ViewScopeInstance>();
  const implementationRef = useRef(implementation);
  implementationRef.current = implementation;
  const definition = viewScopeDefFor(ref);
  const stableScopeRef = useRef<
    | {
        readonly definition: ViewScopeDefinition;
        readonly key: string;
        readonly ref: ViewScopeRef;
        readonly implementation: ViewScopeImpl<TDef>;
      }
    | undefined
  >(undefined);
  if (
    !stableScopeRef.current ||
    stableScopeRef.current.key !== ref.key ||
    stableScopeRef.current.definition !== definition
  ) {
    if (import.meta.env.DEV) {
      assertImplHasAllCommands(definition, implementationRef.current);
    }
    stableScopeRef.current = {
      definition,
      key: ref.key,
      ref,
      implementation: createDelegatingImplementation(definition, () => implementationRef.current),
    };
  }
  const stableScope = stableScopeRef.current;

  // Child layout effects run before a parent publishes its instance through context.
  // A nested scope can therefore instantiate once without a parent and then be
  // recreated with the parent on the following render; disposal keeps both paths safe.
  useLayoutEffect(() => {
    const next = runtime.instantiate(stableScope.ref, {
      parent,
      impl: stableScope.implementation,
    });
    setInstance(next);
    return () => {
      next.dispose();
    };
  }, [parent, runtime, stableScope]);

  const attachRef = useCallback<RefCallback<HTMLElement>>(
    (element) => instance?.attachRef(element),
    [instance]
  );

  return { instance, attachRef };
}
