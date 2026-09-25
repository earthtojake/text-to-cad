import { useEffect, useState } from "react";
import ToolPanel from "../../../kit/tools/ToolPanel.jsx";
import { CrossSectionControls, ExplodeControls } from "./ModelViewControls.js";
import { explodablePartCount } from "../../workbench/explodableParts.js";

/** Separated assembly layers, distinct from a fullscreen/expand affordance. */
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

/** Selection belongs to the toolbar; applied effects and their panels outlive it. */
export function useModelTools({ modelKey, view, features, store, mesh, disabled, selectedTool, onSelect, hidden, measure = null }) {
  const applied = [
    ...(view.exploded.enabled && view.exploded.amount > 0 ? ["exploded"] : []),
    ...(view.clip.enabled && Math.abs(view.clip.offsets[view.clip.axis] - (view.clip.invert ? 0 : 1)) > 1e-6 ? ["clip"] : []),
  ];
  const [panels, setPanels] = useState(() => ({ modelKey, ids: applied }));
  const panelIds = panels.modelKey === modelKey ? panels.ids : applied;
  const appliedKey = applied.join(",");
  // A pointer held down in a panel (a slider mid-drag): a kept panel whose value passes
  // through neutral on the way somewhere else must not vanish under the pointer, so panels
  // are only dropped once it lets go.
  const [holding, setHolding] = useState(false);
  useEffect(() => {
    if (!holding) return undefined;
    const release = () => setHolding(false);
    window.addEventListener("pointerup", release, true);
    window.addEventListener("pointercancel", release, true);
    return () => {
      window.removeEventListener("pointerup", release, true);
      window.removeEventListener("pointercancel", release, true);
    };
  }, [holding]);
  useEffect(() => {
    setPanels(current => {
      const existing = current.modelKey === modelKey ? current.ids : [];
      // Retain an untouched panel only while it owns input. The settings store is
      // authoritative, so an external Reset also removes previously applied panels.
      const ids = existing.filter(id => holding || id === selectedTool || applied.includes(id));
      ids.push(...applied.filter(id => !ids.includes(id)));
      return current.modelKey === modelKey && ids.join(",") === current.ids.join(",")
        ? current : { modelKey, ids };
    });
  }, [modelKey, selectedTool, appliedKey, holding]);
  const definitions = [
    ...(measure ? [{ ...measure, id: "measure", label: "Measure" }] : []),
    { id: "exploded", label: "Explode", Icon: ExplodeIcon, unavailable: explodablePartCount(mesh) <= 1,
      summary: `${Math.round((view.exploded.enabled ? view.exploded.amount : 0) * 100)}%`,
      controls: <ExplodeControls compact viewSettings={view} onViewSettingsPatch={store.patch} /> },
    { id: "clip", label: "Clip", Icon: ClipIcon,
      controls: <CrossSectionControls viewSettings={view} onViewSettingsPatch={store.patch} bounds={mesh?.bounds || null} /> }
  ].filter(tool => tool.id === "measure" || features.sections.includes(tool.id));
  const remove = id => {
    if (id === "measure") { measure.onRemove(); return; }
    else if (id === "exploded") store.patch({ exploded: { enabled: false, amount: 0 } });
    else store.patch({ clip: { enabled: false, axis: "x", offsets: { x: 1, y: 1, z: 1 }, invert: false } });
    setPanels(current => ({ modelKey, ids: current.ids.filter(value => value !== id) }));
    if (selectedTool === id) onSelect("references");
  };
  return {
    tools: definitions.filter(tool => tool.id !== "measure").map(({ id, label, Icon, unavailable }) => ({
      id, label, active: panelIds.includes(id), disabled: disabled || unavailable,
      icon: <Icon className="size-3" strokeWidth={2} aria-hidden="true" />,
      onSelect: () => {
        if (panelIds.includes(id)) { remove(id); return; }
        onSelect(id);
        // A panel starts neutral. Actual edits enable its effect.
        if (id === "clip") store.patch({ clip: { enabled: false, axis: "x", offsets: { x: 1, y: 1, z: 1 }, invert: false } });
        else if (id === "exploded") store.patch({ exploded: { enabled: false, amount: 0 } });
        setPanels(current => ({ modelKey, ids: [...new Set([...(current.modelKey === modelKey ? current.ids.filter(value => applied.includes(value)) : []), id])] }));
      }
    })),
    panels: <div hidden={hidden} className="min-h-0 w-40 max-w-full space-y-2 overflow-y-auto" data-model-tool-panels=""
      onPointerDownCapture={() => setHolding(true)}>
      {[...(measure?.hasMeasurements ? ["measure"] : []), ...panelIds].map(id => {
        const tool = definitions.find(value => value.id === id);
        return tool ? <section key={id} aria-label={`${tool.label} controls`}
          className="pointer-events-auto overflow-hidden rounded-md border border-border bg-popover text-popover-foreground shadow-sm text-tiny">
          <ToolPanel title={tool.label} label={`${tool.label} controls`} summary={tool.summary} collapsible
            onClose={() => remove(id)}>
            <div className="space-y-1 pb-1">{tool.controls}</div>
          </ToolPanel>
        </section> : null;
      })}
    </div>
  };
}
