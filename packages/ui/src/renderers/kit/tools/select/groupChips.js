import { sceneCopyText } from "./sceneReferences.jsx";

/**
 * Quick Edit's chips with every whole group picked as ONE chip (a block whose every part is selected:
 * "graphic · 34 parts"), in the place its first member held; a group half picked keeps a chip per
 * pick. The references are unchanged: the prompt names each pick. A group chip copies one reference
 * naming them all, and its X lets them all go.
 *
 * @param {{ selected: readonly string[], chips: readonly object[], groups: readonly { id: string, label: string, picks: readonly string[] }[],
 *   label(group: { id: string, label: string, picks: readonly string[] }): string, select(id: string, options: { multiSelect: boolean }): void,
 *   resource: import("@cad/core/prompt").ResourceRef | null }} options  `chips`: one per `selected`, in its order.
 */
export function groupChips({ selected, chips, groups, label, select, resource }) {
  if (selected.length < 2 || !groups?.length) return chips;
  const picked = new Set(selected);
  const owner = new Map();
  for (const group of groups) {
    if (group.picks.length < 2 || !group.picks.every(id => picked.has(id)) || group.picks.some(id => owner.has(id))) continue;
    for (const id of group.picks) owner.set(id, group);
  }
  if (!owner.size) return chips;
  const out = [], placed = new Set();
  selected.forEach((id, at) => {
    const group = owner.get(id);
    if (!group) { out.push(chips[at]); return; }
    if (placed.has(group.id)) return;
    placed.add(group.id);
    const first = chips[at] || {};
    const copy = sceneCopyText(resource, group.picks);
    out.push({ key: `group:${group.id}`, label: label(group), ...(first.icon ? { icon: first.icon } : { glyph: first.glyph || "solid" }),
      ...(copy ? { copy } : {}), card: null,
      onRemove: () => { for (const pick of group.picks) select(pick, { multiSelect: true }); } });
  });
  return out;
}
