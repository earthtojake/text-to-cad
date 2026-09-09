/**
 * contract — shared harness for browser measurement contract tests.
 *
 * Each contract test mounts the real Render component in a fixed-width
 * container and asserts that def.measure(data, ctx) equals the element's
 * actual offsetHeight.
 *
 * Usage:
 *   import { makeContractCtx, renderAndMeasureUnit } from '@/tests/contract';
 *
 *   const ctx = makeContractCtx({ width: 640 });
 *   const { computed, dom } = await renderAndMeasureUnit(def, item, ctx);
 *   expect(computed).toBe(dom);
 *
 * Notes:
 *   - For components that apply height via inline style, the test is trivially
 *     satisfied but still guards against regressions.
 *   - For text-layout components (message, thinking, prose), the test verifies
 *     that pretext shaping matches real browser glyph metrics.
 *   - Tolerance: heights must match exactly (integer px). Sub-pixel disagreements
 *     are bugs in the measurement model.
 */

import { CachesContext } from '@components/contexts/CachesContext';
import { ThemeContext } from '@components/contexts/ThemeContext';
import { createChatCaches } from '@core/caches';
import type { MeasureCtx, RenderCtx } from '@core/define';
import type { ChatTheme } from '@core/theme';
import { DEFAULT_THEME } from '@core/theme';
import type { UnitDef } from '@core/units';
import { type JSX } from 'solid-js';
import { render } from 'solid-js/web';
import { afterEach } from 'vitest';

export type ContractCtx = MeasureCtx;

/**
 * Build a MeasureCtx for contract tests.
 * Defaults: theme = DEFAULT_THEME, width = 640, no collapsed items.
 */
export function makeContractCtx(opts: {
  width?: number;
  theme?: ChatTheme;
  isCollapsed?: (id: string) => boolean;
  expanded?: (id: string) => boolean;
  expandedId?: string | null;
}): ContractCtx {
  return {
    theme: opts.theme ?? DEFAULT_THEME,
    width: opts.width ?? 640,
    isCollapsed: opts.isCollapsed ?? (() => false),
    expanded: opts.expanded ?? (() => false),
    caches: createChatCaches(),
    expandedId: opts.expandedId,
  };
}

/**
 * Mount a native `UnitDef.Render` in a fixed-width container, wait one rAF,
 * then return both the computed height (from `def.measure`) and the actual DOM height.
 *
 * The `renderCtx` supplied to the Render has:
 *   - `viewState.isCollapsed` = `ctx.isCollapsed` (matches the Lane A inputs)
 *   - `measureCtx` = `() => measureCtx` (so native Renders can access theme/width/caches)
 *
 * Note: `expanded(id) = isCollapsed(id)` mirrors the native UnitRow path, where
 * inverted-mode composites (thinking / plan / file-op) treat isCollapsed=true as
 * "expanded".
 */
export async function renderAndMeasureUnit<D>(
  def: UnitDef<D, Record<string, number>>,
  data: D,
  ctx: ContractCtx
): Promise<{ computed: number; dom: number }> {
  // Mirror the native UnitRow path: expanded(id) = isCollapsed(id).
  const measureCtx: MeasureCtx = {
    ...ctx,
    expanded: ctx.isCollapsed,
  };
  const computed = def.measure(data, measureCtx, def.vars ?? {});
  const renderCtx: RenderCtx = {
    viewState: { isCollapsed: ctx.isCollapsed },
    measureCtx: () => measureCtx,
  };

  const host = document.createElement('div');
  host.style.width = `${ctx.width}px`;
  document.body.appendChild(host);

  let dispose: (() => void) | undefined;

  try {
    // oxlint-disable-next-line typescript/no-explicit-any -- JSX typed per-def; safe at boundary
    const Comp = def.Render as (p: any) => JSX.Element;
    const caches = ctx.caches;
    dispose = render(
      () => (
        <ThemeContext.Provider value={() => ctx.theme}>
          <CachesContext.Provider value={caches}>
            <Comp data={data} ctx={renderCtx} vars={def.vars ?? {}} />
          </CachesContext.Provider>
        </ThemeContext.Provider>
      ),
      host
    );

    await new Promise<void>((r) => requestAnimationFrame(() => r()));

    const child = host.firstElementChild as HTMLElement | null;
    return { computed, dom: child?.offsetHeight ?? 0 };
  } finally {
    dispose?.();
    document.body.removeChild(host);
  }
}

// Auto-cleanup containers after each test (belt-and-suspenders).
afterEach(() => {
  document.querySelectorAll('[data-contract-host]').forEach((el) => el.remove());
});
