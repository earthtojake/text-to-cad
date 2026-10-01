import { useEffect, useState } from "react";
import { ToolbarTooltipScope } from "@text-to-cad/ui/primitives/toolbar-button";

export const PREVIEW_CHROME_IDLE_MS = 1000;
// A browser test on a slow software renderer stretches the idle (`window.__cadPreviewChromeIdleMs`)
// so the chrome is not put away between two of its steps.
const previewChromeIdleMs = () => Number(globalThis.window?.__cadPreviewChromeIdleMs) || PREVIEW_CHROME_IDLE_MS;

/**
 * The viewer's chrome around preview mode. `children` — the tool strip and its stack, Quick Edit,
 * everything a person edits with — is hidden and inert while `active`; the view's own controls
 * (Display settings, Preview) are in the navbar, outside the view, and stay. In preview the
 * `playbar` under the model has one idle deadline and a 150ms fade: movement over `surface` wakes
 * it, and hovering it (`data-preview-hover-hold`), an open menu, or `hold` (a popover the owner
 * keeps, such as Display settings) keeps it up.
 *
 * @param {{ active: boolean, surface?: Element | null, hold?: boolean,
 *   playbar?: import("react").ReactNode | ((onMenuOpenChange: (open: boolean) => void) => import("react").ReactNode),
 *   children?: import("react").ReactNode }} props
 *   `playbar`, when it is a function, is given the setter a menu in it reports its open state to
 *   (Playback settings sits at the playbar's right end).
 */
export default function PreviewChrome({ active, surface, hold = false, playbar, children }) {
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
      }, previewChromeIdleMs());
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
      {active ? (typeof playbar === "function" ? playbar(setMenuOpen) : playbar) : null}
    </div></ToolbarTooltipScope>
  </>;
}
