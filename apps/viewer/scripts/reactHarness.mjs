// A hook-accurate, DOM-free renderer for one component or hook at a time.
//
// The client's own tests run under `node --test` with no DOM, and a real
// react-dom render of a settings panel would drag in Radix, refs and layout
// measurement — none of which is the behaviour a panel test is about. So this
// installs React's own hook dispatcher, calls ONE component function, and hands
// back the element tree it returned. State updates re-run that function exactly
// as React would; nested components stay unrendered elements, which is what
// makes assertions like "the Undo button is gone" cheap and precise.
//
// It renders a single component: it is not a reconciler, has no keys, no
// context providers and no children rendering. Anything needing those belongs
// in a Playwright check instead.
import React from "react";

// React 19 renamed the shared internals object and flattened it: the hook
// dispatcher that was `__SECRET_INTERNALS_DO_NOT_USE_OR_YOU_WILL_BE_FIRED
// .ReactCurrentDispatcher.current` is now the `H` field of
// `__CLIENT_INTERNALS_DO_NOT_USE_OR_WARN_USERS_THEY_CANNOT_UPGRADE`. Same
// contract — read it, swap in this file's dispatcher for one call, put the
// previous one back — so everything below is unchanged.
const reactInternals = React.__CLIENT_INTERNALS_DO_NOT_USE_OR_WARN_USERS_THEY_CANNOT_UPGRADE;

function sameDeps(previous, next) {
  if (!previous || !next || previous.length !== next.length) return false;
  return previous.every((value, index) => Object.is(value, next[index]));
}

export function render(type, initialProps = {}) {
  const slots = [];
  const pending = [];
  let props = initialProps;
  let cursor = 0;
  let tree = null;
  let rendering = false;
  let dirty = false;
  let unmounted = false;

  function slot(initial) {
    const index = cursor++;
    if (slots.length <= index) slots[index] = initial();
    return slots[index];
  }

  function invalidate() {
    if (rendering) {
      dirty = true;
      return;
    }
    pass();
  }

  function useStateHook(initial) {
    const state = slot(() => ({ value: typeof initial === "function" ? initial() : initial }));
    return [state.value, (next) => {
      const value = typeof next === "function" ? next(state.value) : next;
      if (Object.is(value, state.value)) return;
      state.value = value;
      invalidate();
    }];
  }

  function useMemoHook(factory, deps) {
    const memo = slot(() => ({ deps: null, value: undefined, primed: false }));
    if (!memo.primed || !sameDeps(memo.deps, deps)) {
      memo.value = factory();
      memo.deps = deps;
      memo.primed = true;
    }
    return memo.value;
  }

  function useEffectHook(create, deps) {
    const effect = slot(() => ({ deps: null, cleanup: null, primed: false }));
    if (effect.primed && sameDeps(effect.deps, deps)) return;
    effect.deps = deps;
    effect.primed = true;
    pending.push({ effect, create });
  }

  const dispatcher = {
    useState: useStateHook,
    useReducer: (reducer, initialArg, init) => {
      const state = slot(() => ({ value: init ? init(initialArg) : initialArg }));
      return [state.value, (action) => {
        const value = reducer(state.value, action);
        if (Object.is(value, state.value)) return;
        state.value = value;
        invalidate();
      }];
    },
    useMemo: useMemoHook,
    useCallback: (fn, deps) => useMemoHook(() => fn, deps),
    useRef: (initial) => slot(() => ({ current: initial })),
    useEffect: useEffectHook,
    useLayoutEffect: useEffectHook,
    useInsertionEffect: useEffectHook,
    useContext: (context) => context._currentValue,
    useId: () => `:harness-${cursor++}:`,
    useDebugValue: () => {},
    useSyncExternalStore: (_subscribe, getSnapshot) => getSnapshot(),
    useTransition: () => [false, (fn) => fn()],
    useDeferredValue: (value) => value
  };

  function flush() {
    while (pending.length) {
      const { effect, create } = pending.shift();
      if (typeof effect.cleanup === "function") effect.cleanup();
      const cleanup = create();
      effect.cleanup = typeof cleanup === "function" ? cleanup : null;
    }
  }

  function pass() {
    rendering = true;
    try {
      let guard = 0;
      do {
        dirty = false;
        cursor = 0;
        const previous = reactInternals.H;
        reactInternals.H = dispatcher;
        try {
          tree = type(props);
        } finally {
          reactInternals.H = previous;
        }
        flush();
        if (++guard > 50) throw new Error("render did not settle after 50 passes");
      } while (dirty);
    } finally {
      rendering = false;
    }
  }

  pass();

  return {
    get tree() {
      return tree;
    },
    get result() {
      return tree;
    },
    update(nextProps = props) {
      if (unmounted) throw new Error("cannot update an unmounted render");
      props = nextProps;
      pass();
    },
    unmount() {
      unmounted = true;
      for (const state of slots) {
        if (typeof state?.cleanup === "function") state.cleanup();
      }
    }
  };
}

// A hook on its own: the "component" is the call itself, and `result` is what
// it returned on the latest pass.
export function renderHook(run, initialProps = {}) {
  return render(run, initialProps);
}

function childrenOf(node) {
  const children = node?.props?.children;
  if (children === undefined || children === null) return [];
  return Array.isArray(children) ? children : [children];
}

export function isElement(node) {
  return Boolean(node) && typeof node === "object" && "props" in node && "type" in node;
}

/** Every element in the returned tree, parents before children. */
export function elements(node, found = []) {
  if (Array.isArray(node)) {
    for (const child of node) elements(child, found);
    return found;
  }
  if (!isElement(node)) return found;
  found.push(node);
  for (const child of childrenOf(node)) elements(child, found);
  return found;
}

/** The visible text of a node: its string children, in order. */
export function text(node) {
  if (node === null || node === undefined || typeof node === "boolean") return "";
  if (Array.isArray(node)) return node.map(text).join("");
  if (typeof node === "string" || typeof node === "number") return String(node);
  if (!isElement(node)) return "";
  return childrenOf(node).map(text).join("");
}

function matcher(match) {
  if (typeof match === "function") return match;
  return (node) => text(node).trim() === match;
}

export function queryAll(node, match) {
  return elements(node).filter(matcher(match));
}

export function query(node, match) {
  return queryAll(node, match)[0] || null;
}

export function get(node, match) {
  const found = query(node, match);
  if (!found) {
    throw new Error(`no element matched ${typeof match === "function" ? "the predicate" : JSON.stringify(match)}`);
  }
  return found;
}

const CLICK_EVENT = Object.freeze({
  shiftKey: false,
  // Menus close themselves by walking up to their <details>; there is no DOM
  // here, so hand back something that absorbs the write.
  currentTarget: { closest: () => ({}) }
});

export function click(element, event = {}) {
  const onClick = element?.props?.onClick;
  if (typeof onClick !== "function") {
    throw new Error(`element <${String(element?.type?.name || element?.type)}> has no onClick`);
  }
  if (element.props.disabled) {
    throw new Error(`"${text(element).trim()}" is disabled and cannot be clicked`);
  }
  onClick({ ...CLICK_EVENT, ...event });
}
