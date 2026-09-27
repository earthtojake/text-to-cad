import { useEffect, useState } from "react";
import { ToolbarTooltipScope } from "@hardcore/ui/primitives/toolbar-button";
import { VIEWPORT_INSET_PX, VIEWPORT_TOP_BAR_PX } from "../shell/viewportLayout.js";

export const PREVIEW_CHROME_IDLE_MS = 1000;

const BAR_POSITION = Object.freeze({ top: `${VIEWPORT_INSET_PX}px`, right: `${VIEWPORT_INSET_PX}px`, height: VIEWPORT_TOP_BAR_PX });

/**
 * The viewer's chrome around preview mode. `children` — the tool strip and its stack, everything
 * a person edits with — is hidden and inert while `active`. The top-right bar (`actions`) is ONE
 * bar in one place in both modes, so a button that is in both (Display settings) never moves:
 * outside preview it is always shown; in preview it fades with the `playbar` under the model.
 *
 * In preview the controls share one idle deadline and a 150ms fade: movement over `surface`
 * wakes them, and hovering their area (`data-preview-hover-hold`), an open menu, or `hold`
 * (a popover the owner keeps, such as Display settings) keeps them up.
 *
 * @param {{ active: boolean, surface?: Element | null, hold?: boolean,
 *   actions?: (onMenuOpenChange: (open: boolean) => void) => import("react").ReactNode,
 *   playbar?: import("react").ReactNode | ((onMenuOpenChange: (open: boolean) => void) => import("react").ReactNode),
 *   children?: import("react").ReactNode }} props
 *   `actions`, and `playbar` when it is a function, are given the setter a menu in them reports its
 *   open state to (Playback settings sits at the playbar's right end).
 */
export default function PreviewChrome({ active, surface, hold = false, actions, playbar, children }) {
  const [visible, setVisible] = useState(true);
  const [menuOpen, setMenuOpen] = useState(false);
  const held = menuOpen || hold;
  // A menu the bar loses on the way out of preview never reports closing: the next preview starts idle.
  useEffect(() => { if (!active) setMenuOpen(false); }, [active]);
  useEffect(() => {
    setVisible(true);
    if (!active || !surface || held) return;
    let timer;
    let pressing = false;
    const wake = event => {
      clearTimeout(timer);
      setVisible(true);
      if (pressing || event?.target?.closest?.('[data-preview-hover-hold]')) return;
      timer = setTimeout(() => {
        if (!surface.querySelector("[data-preview-hover-hold]:hover")) setVisible(false);
      }, PREVIEW_CHROME_IDLE_MS);
    };
    const leave = () => wake();
    const focus = () => wake();
    const down = event => { pressing = true; wake(event); };
    const up = event => { pressing = false; wake(event); };
    wake();
    surface.addEventListener('pointermove', wake);
    surface.addEventListener('pointerdown', down);
    surface.addEventListener('pointerleave', leave);
    surface.addEventListener('focusin', focus);
    window.addEventListener('pointerup', up);
    window.addEventListener('pointercancel', up);
    return () => {
      clearTimeout(timer);
      surface.removeEventListener('pointermove', wake);
      surface.removeEventListener('pointerdown', down);
      surface.removeEventListener('pointerleave', leave);
      surface.removeEventListener('focusin', focus);
      window.removeEventListener('pointerup', up);
      window.removeEventListener('pointercancel', up);
    };
  }, [active, surface, held]);
  const shown = !active || visible || held;
  return <>
    <div data-preview-chrome="" data-visible={!active} hidden={active} inert={active}
      className="pointer-events-none absolute inset-0 z-20">
      <ToolbarTooltipScope enabled={!active}>{children}</ToolbarTooltipScope>
    </div>
    <ToolbarTooltipScope enabled={shown}><div data-preview-controls="" data-preview-active={active ? "" : undefined}
      data-visible={shown} inert={!shown}
      className="pointer-events-none absolute inset-0 z-30 transition-opacity duration-150"
      style={{ opacity: shown ? 1 : 0 }}>
      <div data-preview-hover-hold="" data-viewport-actions="" style={BAR_POSITION}
        className="pointer-events-auto absolute flex items-center justify-end gap-0.5">
        {actions?.(setMenuOpen)}
      </div>
      {active ? (typeof playbar === "function" ? playbar(setMenuOpen) : playbar) : null}
    </div></ToolbarTooltipScope>
  </>;
}
