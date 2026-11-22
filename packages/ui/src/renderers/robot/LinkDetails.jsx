import { TooltipHint } from "@cad/ui/primitives/tooltip";
import { english, useI18n } from "@cad/ui/i18n";

// What a selected link or object IS, as its Quick Edit chip's card reads it (`kit/inspector/ItemDetail.jsx`:
// `robotReferences.jsx`): the thing in focus alone, its name the card's heading, so the rows never repeat
// it, and a few key facts — never its child links, which the Links tree holds. A link reads its mass and
// the joint that holds it to its parent (its name, its type, the parent link, which a press selects); a
// named mesh object, its link and its size. A click on any other value copies it.

// A card's numbers, read at a glance: three significant figures, a number of four figures or more whole;
// the description keeps every digit.
const significant = value => {
  const number = Number(value);
  if (!Number.isFinite(number)) return "—";
  return number.toLocaleString(undefined, Math.abs(number) >= 1000 ? { maximumFractionDigits: 0 } : { maximumSignificantDigits: 3 });
};
// A mass in kg as a card shows it: kg, or g under 10 g.
const massText = kg => (Math.abs(kg) >= 0.01 ? `${significant(kg)} kg` : `${significant(kg * 1e3)} g`);

const LINK_CLASS = "rounded-sm text-left text-foreground underline decoration-muted-foreground/50 underline-offset-2 hover:decoration-current focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring [overflow-wrap:anywhere]";

/** Another link of the same robot: pressing it selects that link in the tree and the viewport. */
function LinkName({ name, onSelect, selectable = true }) {
  const { t } = useI18n();
  if (!onSelect || !selectable) return name;
  return <TooltipHint content={t("robot.selectLink")}><button type="button" className={LINK_CLASS} onClick={() => onSelect(name)} >{name}</button></TooltipHint>;
}

/**
 * A link, as the frame reads a pick (`kit/inspector/inspect.js`'s `DetailItem`), from what the description
 * says of it (`robotTree.js`'s `robotLinkFacts`): its mass, and its joint to its parent — name, type, and
 * the parent link (pressing it selects that link, `onSelectLink`, where the tree has its row). Its hover
 * tip's short kind is its parent joint's type ("Root link" for the root).
 * @param {ReturnType<typeof import("./robotTree.js").robotLinkFacts>} facts
 */
export function robotLinkItem(facts, { onSelectLink = null, hasLinkRow = () => true, t = english } = {}) {
  const joint = facts.parentJoint;
  const selectable = Boolean(onSelectLink) && joint && hasLinkRow(joint.parentLink);
  return {
    id: `link:${facts.name}`, pick: facts.name, kind: "solid", title: facts.name,
    tip: joint ? joint.type : t("robot.rootLink"),
    facts: [
      ...(facts.mass !== null ? [{ label: t("robot.mass"), value: massText(facts.mass) }] : []),
      ...(joint ? [
        { label: t("robot.joint"), value: <>{joint.name}</> },
        { label: t("robot.jointType"), value: <>{joint.type}</> },
        // A frame-only root has no row to go to; it is still named.
        { label: t("robot.parent"), copy: selectable ? false : undefined,
          value: <LinkName name={joint.parentLink} onSelect={onSelectLink} selectable={hasLinkRow(joint.parentLink)}/> }
      ] : [{ label: t("robot.type"), value: <>{t("robot.rootLink")}</> }])
    ]
  };
}

/** A named mesh object, as the frame reads a pick: its link and its size. */
export function robotComponentItem(component, t = english) {
  const size = component.sizeMillimetres;
  return {
    id: `object:${component.id}`, pick: component.id, kind: "solid", title: component.name || component.link, tip: component.link,
    facts: [
      { label: t("robot.link"), value: <>{component.link}</> },
      ...(size ? [{ label: t("robot.size"), title: t("robot.sizeHint"), value: `${size.map(significant).join(" × ")} mm` }] : [])
    ]
  };
}
