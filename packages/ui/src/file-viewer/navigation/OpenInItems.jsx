import { Fragment, useEffect, useState } from "react";

import { DropdownMenuItem, DropdownMenuSeparator } from "@cad/ui/primitives/dropdown-menu";
import { TooltipHint } from "@cad/ui/primitives/tooltip";

import { OpenInMark } from "./appMarks.jsx";

// Open in's rows, wherever a menu lists the places and apps a file opens in: the navbar's ⋯ (its Open in submenu,
// `ViewerNavbar.jsx`) and the home's menu of a file no page opens (`library/ModelLibrary.tsx`). One drawing of them,
// from the entries `entry-menu.js` makes.

/**
 * A disabled row with its reason as a hint. A disabled Radix item takes no pointer, so the hint is
 * on a wrapper that does, as shadcn hints a disabled button.
 */
export function WhyDisabled({ reason, children }) {
  return <TooltipHint content={reason} side="right"><span className="block" data-disabled-reason="">{children}</span></TooltipHint>;
}

/**
 * The host's apps for a file (`apps`), asked each time its menu opens and never before: null until they come, and null
 * for good where the host has none, or fails or never answers (the menu is then as without them). An answer to an
 * opening since closed is dropped.
 *
 * @param {boolean} open
 * @param {((options: { signal: AbortSignal }) => Promise<import("./entry-menu.js").OpenInFiles | null>) | null | undefined} apps
 */
export function useOpenInApps(open, apps) {
  const [files, setFiles] = useState(null);
  useEffect(() => {
    if (!open || !apps) return undefined;
    const controller = new AbortController();
    setFiles(null);
    Promise.resolve().then(() => apps({ signal: controller.signal })).then(answer => {
      if (!controller.signal.aborted) setFiles(answer && Array.isArray(answer.targets) ? answer : null);
    }, () => {});
    return () => controller.abort();
  }, [open, apps]);
  return open ? files : null;
}

/**
 * Open in's entries as menu rows: each its mark (an app's own, a place's glyph) and its label, a separator between
 * groups, one that cannot open now drawn disabled with its reason as a hint.
 *
 * @param {{ entries: readonly import("./entry-menu.js").OpenInEntry[], onChoose(entry: import("./entry-menu.js").OpenInEntry): void }} props
 */
export function OpenInItems({ entries, onChoose }) {
  return entries.map((item, index) => {
    const row = <DropdownMenuItem data-open-in={item.action} data-open-in-app={item.app} disabled={!item.enabled} onSelect={() => onChoose(item)}>
      <OpenInMark action={item.action} app={item.app} className="size-3.5" />{item.label}</DropdownMenuItem>;
    return <Fragment key={`${item.action}:${item.target ?? ""}:${item.app ?? ""}`}>
      {index && entries[index - 1].group !== item.group ? <DropdownMenuSeparator /> : null}
      {item.enabled ? row : <WhyDisabled reason={item.reason}>{row}</WhyDisabled>}
    </Fragment>;
  });
}
