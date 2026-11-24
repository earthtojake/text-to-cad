import { FieldLabel } from "@cad/ui/primitives/field-label";
import { RotateCcw } from "lucide-react";
import { ToolbarButton } from "@cad/ui/primitives/toolbar-button";
import SubToolbar, { SLIDER_SUB_TOOLBAR_CLASS } from "../SubToolbar.jsx";
import { CrossSectionControls, ExplodeControls } from "./ModelViewControls.js";
import { useControlUsage } from "../../../../usage/controls.js";
import { useI18n } from "@cad/ui/i18n";

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
 * Explode and Clip: the model's effects, each a tool of the strip as Draw is. Pressed, it is the tool in hand (its
 * button pressed) and its row hangs under the strip (`SubToolbar`, the drawing tools' width): what leads it (Explode's
 * name; Clip's axis, whose dropdown holds its settings too), then its slider, the amount beside it, then Reset, which
 * takes the effect away (the amount back at zero, Clip's axis and settings kept), idle while none is set. In hand it
 * stands over Select, the mode underneath (`useRendererShell`'s `effectTool`), so a press on the model picks as
 * Select's does and the camera is as ever. Another tool taken up puts it down and leaves what it set on the model,
 * its tile's dot saying so while it is not in hand. (Measure's results are Quick Edit's chips.)
 *
 * Each is offered where the view's features list it (`ViewFeatures`): a renderer decides which of its
 * files have them, and lists Explode only where there are parts to separate.
 */
export function useModelTools({ view, features, store, mesh, disabled, shell }) {
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
      controls: <ExplodeControls viewSettings={view} onViewSettingsPatch={store.patch}
        label={<FieldLabel className="shrink-0 pl-1.5 pr-1">{t("explode.label")}</FieldLabel>} /> },
    { id: "clip", label: t("clip.label"), reset: t("clip.reset"), Icon: ClipIcon,
      controls: <CrossSectionControls viewSettings={view} onViewSettingsPatch={store.patch} bounds={clipBounds} /> }
  ].filter(tool => features.settings.includes(tool.id));
  // Neutral is the amount at zero, nothing else: Clip's axis and its settings (Part colours, Reverse) stay as set.
  const neutral = id => id === "exploded" ? { exploded: { enabled: false, amount: 0 } } : { clip: { enabled: false } };
  const inHand = shell?.effectTool ?? null;
  const rows = {};
  const tools = definitions.map(tool => {
    const changed = applied.includes(tool.id);
    const active = inHand === tool.id;
    const icon = <tool.Icon className="size-3" strokeWidth={2} aria-hidden="true" />;
    // Its row, unnamed but for what leads it: the slider control (what leads it, the slider, the amount), Reset.
    rows[tool.id] = <SubToolbar label={t("effects.controls", { tool: tool.label })} className={SLIDER_SUB_TOOLBAR_CLASS} data-model-tool={tool.id}>
      {tool.controls}
      <ToolbarButton label={tool.reset} disabled={!changed} onClick={() => { controls.used(tool.id === "exploded" ? "explode_reset" : "clip_reset"); store.patch(neutral(tool.id)); }}>
        <RotateCcw className="size-3" strokeWidth={2} aria-hidden="true" />
      </ToolbarButton>
    </SubToolbar>;
    // Counted as used each time it is taken up (`usage/controls.js`: `explode`, `clip`), as its popover's opening was.
    // Their own group on the strip, after the tools that pick. Its dot while it is set and not in hand.
    return { id: tool.id, label: tool.label, group: "model", disabled, active, changed: changed && !active, icon,
      onSelect: () => { if (active) return; controls.used(tool.id === "exploded" ? "explode" : "clip"); shell?.selectEffectTool(tool.id); } };
  });
  return { tools, subToolbar: inHand ? rows[inHand] ?? null : null };
}
