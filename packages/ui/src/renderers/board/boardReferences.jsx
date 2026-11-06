import { useCallback, useMemo } from "react";
import { useI18n } from "@cad/ui/i18n";
import { formatPromptReference } from "@cad/core/prompt";
import { boardReferenceId } from "./boardFacts.js";
import {
  AreaKindIcon, DimensionKindIcon, GraphicKindIcon, NetKindIcon, PadKindIcon, PartKindIcon, RuleAreaKindIcon, TextKindIcon, TrackKindIcon, ViaKindIcon,
  ZoneKindIcon
} from "./boardIcons.jsx";
import { describeBoardPick, boardPickTip } from "./boardTree.js";

const EMPTY = Object.freeze([]);
// A chip leads with its kind's glyph, as Select's filter names the kinds: a part, a pad, a net or its
// copper, a track, a via, a zone, a rule area, a text, a dimension, a graphic, an area; a point keeps the pick's vertex.
const KIND_ICONS = Object.freeze({ solid: PartKindIcon, face: PadKindIcon, edge: NetKindIcon, track: TrackKindIcon, via: ViaKindIcon,
  zone: ZoneKindIcon, ruleArea: RuleAreaKindIcon, text: TextKindIcon, dimension: DimensionKindIcon, shape: GraphicKindIcon, area: AreaKindIcon });
const CHIP_ICON_CLASS = "size-2.5 shrink-0 text-muted-foreground";
const chipIcon = (glyph) => {
  const Icon = KIND_ICONS[glyph];
  return Icon ? { icon: <Icon className={CHIP_ICON_CLASS} /> } : { glyph };
};

// The board's glyphs in the Selected pane and a chip's card: a chip's kinds, and the lists' (a part, a pad, a net).
const BOARD_GLYPHS = Object.freeze({ ...KIND_ICONS, part: PartKindIcon, pad: PadKindIcon, net: NetKindIcon });

/**
 * What is picked on the board, as its frame reads it (`kit/inspector/inspect.js`): each pick described
 * (`describeBoardPick`: the Selected pane, a chip's card, the hover tip's name), what the pointer is on
 * (`hovered`), and what a row of the pane does (`select`, `hover`, `frame`, `onSelect`, `copyText`).
 */
export function useBoardInspect({ index, describe, tip = null, selection, hovered, onSelect, frame, copyText }) {
  const { selected, select, hover } = selection;
  return useMemo(() => (index ? { selected, describe, tip, hovered, glyphs: BOARD_GLYPHS, data: "board", select, hover, frame, onSelect, copyText } : null),
    [index, selected, describe, tip, hovered, select, hover, frame, onSelect, copyText]);
}

/** A board's picks described (`describeBoardPick`, a part's 3D model from the models table), in the view's language: what the pane and the cards read. */
export function useBoardDescribe(index, models = null) {
  const { t } = useI18n();
  return useCallback(id => (index ? describeBoardPick(index, id, t, models) : null), [index, t, models]);
}

/** The hover tip's short words for a pick (`boardPickTip`), in the view's language. */
export function useBoardTip(index) {
  const { t } = useI18n();
  return useCallback(id => (index ? boardPickTip(index, id, t) : ""), [index, t]);
}

/**
 * What is selected on a board, for Quick Edit (`useSceneSelection` over `boardScene.js`): each pick
 * as a reference into the file on screen, by its board reference, and as a chip named as the board
 * names it (`R1`, `R1.2`, `net VBUS`, `VBUS · track`, `“blinky”`, an area), led by its kind's glyph —
 * the kinds Select's filter shows (a net's copper is its net's), a point an agent wrote the pick's vertex — its card
 * what the board says of it (`describe`, the Selected pane's), its ID the reference.
 * A click on a chip copies its reference (`<file>#R1.2`); its X drops it; resting on it lights it.
 *
 * @param {{ scene: ReturnType<typeof import("./boardScene.js").createBoardScene> | null,
 *   selection: ReturnType<typeof import("../kit/tools/select/useSceneSelection.js").useSceneSelection>,
 *   resource: import("@cad/core/prompt").ResourceRef | null }} options
 */
export function useBoardReferences({ scene, selection, resource, describe = null }) {
  const { selected, select, hover } = selection;
  return useMemo(() => {
    if (!scene) return { references: EMPTY, chips: EMPTY };
    const reference = id => (resource?.kind === "workspace-file"
      ? { resource: { ...resource }, target: { kind: "cad-selector", selectors: [id] } } : null);
    const references = selected.map(reference).filter(Boolean);
    const chips = selected.map((id) => {
      const described = scene.describePart(id);
      const value = reference(id);
      return { key: `pick:${id}`, label: described?.name || boardReferenceId(id), ...chipIcon(described?.icon || described?.glyph || "solid"), id: boardReferenceId(id),
        ...(value ? { copy: formatPromptReference(value) } : {}),
        detail: describe?.(id) || null,
        onRemove: () => select(id, { multiSelect: true }), onHover: on => hover(on ? id : "") };
    });
    return { references, chips };
  }, [scene, selected, resource, select, hover, describe]);
}
