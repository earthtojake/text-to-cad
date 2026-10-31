import { useState } from "react";
import { RotateCcw } from "lucide-react";
import { Popover, PopoverAnchor, PopoverContent, PopoverTrigger } from "@text-to-cad/ui/primitives/popover";
import { ToolbarButton } from "@text-to-cad/ui/primitives/toolbar-button";
import { cn } from "@text-to-cad/ui/utils";
import { ChangedDot } from "../ChangedDot.jsx";
import { useStripButtonClass } from "../stripTouch.js";
import SubToolbar, { SLIDER_SUB_TOOLBAR_CLASS, SUB_TOOLBAR_SLIDER_CLASS, SubToolbarValue } from "../SubToolbar.jsx";
import { CrossSectionControls, ExplodeControls, clipSummary } from "./ModelViewControls.js";
import { useControlUsage } from "../../../../usage/controls.js";
import { useI18n } from "@text-to-cad/ui/i18n";

/** Separated assembly layers, distinct from an expand affordance. */
function ExplodeIcon(props) {
  return <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" {...props}>
    <path d="m12 2 8 4-8 4-8-4Z M4 11l8 4 8-4 M4 17l8 4 8-4" />
    <path d="M4 6v2l8 4 8-4V6 M4 17v2l8 4 8-4v-2" />
  </svg>;
}

function ClipIcon(props) {
  return <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" {...props}>
    <path d="M16 4.5a8.5 8.5 0 1 0 0 15" />
    <ellipse cx="16" cy="12" rx="3" ry="7.5" />
  </svg>;
}

/**
 * One model effect's tile on the strip, as Projection's and Display's are: its button, which opens
 * its row (`children`, the sub-toolbar it was) in a popover under it — the same size and look —
 * closed by a press outside it (a press on the model is a pick as well), by Escape or by its button
 * again. The button has no pressed state: the effect is the model's, and stays set when the
 * popover closes, its dot in the tile's corner while it is set (`changed`). A menu inside it (Clip's
 * axis) is part of it: choosing there keeps it open. On a phone's strip with no room for the tile,
 * it opens from the strip's More button instead (`anchor`, with `open` held by the strip).
 */
function EffectPopover({ label, icon, changed = false, disabled = false, row, onOpen, anchor = null, open: held, onOpenChange }) {
  const [ownOpen, setOpen] = useState(false);
  const open = held ?? ownOpen;
  const stripClass = useStripButtonClass();
  const changeOpen = next => { if (next && !open) onOpen?.(); setOpen(next); onOpenChange?.(next); };
  return <Popover open={open} onOpenChange={changeOpen} modal={false}>
    {anchor ? <PopoverAnchor virtualRef={anchor} /> : <PopoverTrigger asChild>
      <ToolbarButton tooltipSide="top" label={label} disabled={disabled} className={cn(stripClass, changed && "relative")}
        data-model-effect="" data-changed={changed ? "" : undefined}>
        {icon}
        {changed ? <ChangedDot /> : null}
      </ToolbarButton>
    </PopoverTrigger>}
    {/* The row brings its own surface: the popover is only where it opens. */}
    <PopoverContent side="bottom" align="center" sideOffset={6} collisionPadding={8} aria-label={label}
      onOpenAutoFocus={event => event.preventDefault()}
      className="w-auto border-0 bg-transparent p-0 shadow-none data-[state=closed]:animate-none!">
      {row}
    </PopoverContent>
  </Popover>;
}

/**
 * Explode and Clip: the model's effects, each a popover from its tile on the strip (`EffectPopover`),
 * as the view's controls are, never a tool in hand: opening one leaves the tool in hand as it is, and
 * what it sets stays on the model once it closes, until its Reset, as a Display setting does. Its row
 * leads with what it is (Explode's name; Clip's axis, whose dropdown holds its settings too), then its
 * slider, the amount beside the slider, then Reset, which takes the effect away (the amount back at
 * zero, Clip's axis and settings kept), idle while none is set. (Measure's results are Quick Edit's chips.)
 *
 * Each is offered where the view's features list it (`ViewFeatures`): a renderer decides which of its
 * files have them, and lists Explode only where there are parts to separate.
 */
export function useModelTools({ view, features, store, mesh, disabled }) {
  const { t } = useI18n();
  const controls = useControlUsage();
  const applied = [
    ...(view.exploded.enabled && view.exploded.amount > 0 ? ["exploded"] : []),
    ...(view.clip.enabled ? ["clip"] : []),
  ];
  // The box Clip's plane is placed in, so its slider maps with exactly that box: the model at
  // rest, its declared box when a package has one (the scene's `restBounds`, which the viewport
  // hands the plane as `zeroPoseBounds`).
  const clipBounds = mesh?.declaredBounds || mesh?.bounds || null;
  const definitions = [
    { id: "exploded", label: t("explode.label"), reset: t("explode.reset"), Icon: ExplodeIcon,
      // Named, as Clip's axis and Animation's Play lead theirs: a bare slider says nothing of what it moves.
      lead: <span className="shrink-0 pl-1.5 pr-1 text-tiny text-foreground">{t("explode.label")}</span>,
      summary: `${Math.round((view.exploded.enabled ? view.exploded.amount : 0) * 100)}%`,
      controls: <ExplodeControls viewSettings={view} onViewSettingsPatch={store.patch} className={SUB_TOOLBAR_SLIDER_CLASS} /> },
    { id: "clip", label: t("clip.label"), reset: t("clip.reset"), Icon: ClipIcon, summary: clipSummary(view, clipBounds),
      controls: <CrossSectionControls viewSettings={view} onViewSettingsPatch={store.patch} bounds={clipBounds}
        className="flex min-w-0 flex-1 items-center gap-1" sliderClassName={SUB_TOOLBAR_SLIDER_CLASS} /> }
  ].filter(tool => features.settings.includes(tool.id));
  // Neutral is the amount at zero, nothing else: Clip's axis and its settings (Part colours, Reverse) stay as set.
  const neutral = id => id === "exploded" ? { exploded: { enabled: false, amount: 0 } } : { clip: { enabled: false } };
  return {
    tools: definitions.map(tool => {
      const changed = applied.includes(tool.id);
      const icon = <tool.Icon className="size-3" strokeWidth={2} aria-hidden="true" />;
      // Its row, unnamed but for what leads it: the slider, the amount, Reset.
      const row = <SubToolbar label={t("effects.controls", { tool: tool.label })} className={SLIDER_SUB_TOOLBAR_CLASS} data-model-tool={tool.id}>
        {tool.lead || null}
        {tool.controls}
        <SubToolbarValue data-model-tool-amount="">{tool.summary}</SubToolbarValue>
        <ToolbarButton label={tool.reset} disabled={!changed} onClick={() => { controls.used(tool.id === "exploded" ? "explode_reset" : "clip_reset"); store.patch(neutral(tool.id)); }}>
          <RotateCcw className="size-3" strokeWidth={2} aria-hidden="true" />
        </ToolbarButton>
      </SubToolbar>;
      // Counted as used each time its popover opens (`usage/controls.js`: `explode`, `clip`), with no
      // seconds: it is no tool in hand.
      const shared = { label: tool.label, icon, changed, disabled, row, onOpen: () => controls.used(tool.id === "exploded" ? "explode" : "clip") };
      // Their own group on the strip, ruled off from the tools that pick.
      return { id: tool.id, label: tool.label, group: "model", disabled, changed, icon,
        tile: <EffectPopover {...shared} />,
        popover: ({ anchor, open, onOpenChange }) => <EffectPopover {...shared} anchor={anchor} open={open} onOpenChange={onOpenChange} /> };
    }),
  };
}
