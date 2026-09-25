import { useEffect, useState } from "react";
import { X } from "lucide-react";
import { ToolbarButton } from "./ToolbarButton.js";
import { TooltipProvider } from "@hardcore/ui/primitives/tooltip";
import { ToolbarTooltipScope } from "@hardcore/ui/primitives/toolbar-button";

export const PREVIEW_CHROME_IDLE_MS = 1000;

/** Editor chrome stays hidden; only presentation controls wake on movement. */
export default function PreviewChrome({ active, surface, onExit, settings, playbar, children }) {
  const [visible, setVisible] = useState(true);
  const [menuOpen, setMenuOpen] = useState(false);
  useEffect(() => {
    setVisible(true);
    if (!active || !surface || menuOpen) return;
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
  }, [active, surface, menuOpen]);
  return <>
    <div data-preview-chrome="" data-visible={!active} hidden={active} inert={active}
      className="pointer-events-none absolute inset-0 z-20">
      <ToolbarTooltipScope enabled={!active}>{children}{!active && playbar}</ToolbarTooltipScope>
    </div>
    {active ? <TooltipProvider delayDuration={400}><ToolbarTooltipScope enabled={visible || menuOpen}><div data-preview-controls="" data-visible={visible || menuOpen} inert={!visible && !menuOpen}
      className="pointer-events-none absolute inset-0 z-30 transition-opacity duration-150"
      style={{ opacity: visible || menuOpen ? 1 : 0 }}>
      <div data-preview-exit="" data-preview-hover-hold="" className="pointer-events-auto absolute right-0 top-0 flex items-center gap-1 p-3">
        {settings?.(setMenuOpen)}
        <ToolbarButton tooltip={false} label="Exit fullscreen" onClick={onExit}>
          <X className="size-3.5" strokeWidth={1.5} aria-hidden="true" />
        </ToolbarButton>
      </div>
      {playbar}
    </div></ToolbarTooltipScope></TooltipProvider> : null}
  </>;
}
