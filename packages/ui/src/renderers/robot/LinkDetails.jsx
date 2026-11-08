import { TooltipHint } from "@cad/ui/primitives/tooltip";
import { CoordValue } from "../kit/inspector/referenceRows.jsx";
import { english, useI18n } from "@cad/ui/i18n";

// What a selected link or object IS, as the Selected pane and its Quick Edit chip's card read it
// (`kit/inspector/ItemDetail.jsx`, one component for both: `robotReferences.jsx`). Its head names it, so
// the rows never repeat the name.
//
// A link reads back what the description says about it (its inertial properties, its
// visual and collision geometry, its parent joint with limits and origin); a named
// mesh object reads back the mesh facts a person uses to tell two objects of one link
// apart. What names something else can be followed: a mesh path opens that file, a
// link name selects that link. A click on any other value copies it.

function formatCount(value) {
  return Number(value || 0).toLocaleString();
}

// Millimetres, to the precision the number deserves: a 0.4 mm feature keeps its
// tenths, a 240 mm frame does not pretend to them.
function formatMillimetres(value) {
  const size = Number(value);
  if (!Number.isFinite(size)) return "";
  if (size >= 100) return size.toFixed(0);
  if (size >= 10) return size.toFixed(1);
  return size.toFixed(2);
}

// As written, without the noise of a float: 1.5707963 stays readable, 0 stays 0.
function formatValue(value, digits = 4) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "—";
  const rounded = Number(number.toFixed(digits));
  return String(Object.is(rounded, -0) ? 0 : rounded);
}

const ANGULAR = new Set(["revolute", "continuous"]);
const degrees = radians => `${formatValue((radians * 180) / Math.PI, 1)}°`;

const LINK_CLASS = "rounded-sm text-left text-sidebar-foreground underline decoration-muted-foreground/50 underline-offset-2 hover:decoration-current focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring [overflow-wrap:anywhere]";
const isZero = vector => vector.every(value => Math.abs(value) < 1e-12);
const isUnit = vector => vector.every(value => Math.abs(value - 1) < 1e-12);
const vectorText = (vector, digits = 4) => vector.map(value => formatValue(value, digits)).join("  ");

/** Another link of the same robot: pressing it selects that link in the tree and the viewport. */
function LinkName({ name, onSelect, selectable = true }) {
  const { t } = useI18n();
  if (!onSelect || !selectable) return name;
  return <TooltipHint content={t("robot.selectLink")}><button type="button" className={LINK_CLASS} onClick={() => onSelect(name)} >{name}</button></TooltipHint>;
}

// What a primitive IS, in the description's own metres.
function dimensions(entry) {
  if (entry.type === "box" && entry.size) return `${entry.size.map(value => formatValue(value)).join(" × ")} m`;
  if (entry.type === "cylinder" && entry.radius !== null && entry.length !== null) return `r ${formatValue(entry.radius)} · l ${formatValue(entry.length)} m`;
  if (entry.type === "sphere" && entry.radius !== null) return `r ${formatValue(entry.radius)} m`;
  return "";
}

// One visual or collision: the file or the primitive, then only what the description
// bothered to say (a zero origin and a unit scale are the defaults, not facts). A mesh file
// opens by the host path cadgen resolved for it; a reference it could not resolve to one
// (a package:// URI) is text.
function GeometryEntry({ entry, onOpenFile }) {
  const { t } = useI18n();
  const path = entry.filename ? entry.path : "";
  const detail = [
    entry.type !== "mesh" && dimensions(entry),
    entry.scale && !isUnit(entry.scale) && `scale ${vectorText(entry.scale)}`,
    entry.origin && !isZero(entry.origin.xyz) && `xyz ${vectorText(entry.origin.xyz)}`,
    entry.origin && !isZero(entry.origin.rpy) && `rpy ${vectorText(entry.origin.rpy)}`,
  ].filter(Boolean);
  return <span className="block py-0.5">
    <span className="flex min-w-0 items-baseline gap-1.5">
      {entry.color && <TooltipHint content={entry.materialName || entry.color}><span className="size-2.5 shrink-0 self-center rounded-sm border border-border/70" style={{ backgroundColor: entry.color }}  aria-hidden="true"/></TooltipHint>}
      {entry.filename
        ? path && onOpenFile
          ? <TooltipHint content={t("robot.openFile")}><button type="button" className={LINK_CLASS} onClick={() => onOpenFile(path)} >{entry.filename}</button></TooltipHint>
          : <span>{entry.filename}</span>
        : <span>{entry.type}</span>}
    </span>
    {detail.map(line => <span key={line} className="block tabular-nums text-muted-foreground">{line}</span>)}
  </span>;
}

// A link's visuals or collisions: each its file or primitive (a file a link, which keeps its own click).
function GeometryValue({ entries, onOpenFile }) {
  const { t } = useI18n();
  return entries.length
    ? entries.map((entry, index) => <GeometryEntry key={`${entry.filename || entry.type}:${index}`} {...{ entry, onOpenFile }}/>)
    : <span className="text-muted-foreground">{t("robot.none")}</span>;
}

// The six terms the description writes, laid out as the symmetric tensor they are: three columns the
// panel's width, a value too long for its cell truncated (the whole of it is its hint), never wrapping
// inside the number.
const INERTIA_ROWS = [["ixx", "ixy", "ixz"], ["ixy", "iyy", "iyz"], ["ixz", "iyz", "izz"]];
function InertiaValue({ inertia }) {
  return <span className="grid w-full grid-cols-3 gap-x-2 tabular-nums">
    {INERTIA_ROWS.flatMap((row, r) => row.map((term, c) => {
      const text = formatValue(inertia[term], 6);
      return <TooltipHint key={`${r}${c}`} content={text} overflowOnly>
        <span className={`min-w-0 truncate${c < r ? " text-muted-foreground" : ""}`} data-inertia-term={term}>{text}</span>
      </TooltipHint>;
    }))}
  </span>;
}

// A joint's limits: its range in the description's units (and an angular one in degrees under it), its
// effort and its velocity, each where the description gives it.
function limitFacts(joint, t, section) {
  const limit = joint.limit;
  if (!limit) return [];
  const angular = ANGULAR.has(joint.type);
  const unit = angular ? "rad" : "m";
  const range = Number.isFinite(limit.lower) || Number.isFinite(limit.upper);
  const text = `${formatValue(limit.lower)} … ${formatValue(limit.upper)} ${unit}`;
  return [
    ...(range ? [{ section, label: t("robot.limits"), title: t(angular ? "robot.limitsRadians" : "robot.limitsMetres"), copy: text, value: <>
      <span className="tabular-nums">{text}</span>
      {angular && Number.isFinite(limit.lower) && Number.isFinite(limit.upper) &&
        <span className="block text-muted-foreground">{`${degrees(limit.lower)} … ${degrees(limit.upper)}`}</span>}
    </> }] : []),
    ...(Number.isFinite(limit.effort) ? [{ section, label: t("robot.effort"), value: `${formatValue(limit.effort)} ${angular ? "N·m" : "N"}` }] : []),
    ...(Number.isFinite(limit.velocity) ? [{ section, label: t("robot.velocity"), value: `${formatValue(limit.velocity)} ${angular ? "rad/s" : "m/s"}` }] : [])
  ];
}

/**
 * A link, as the frame reads a pick (`kit/inspector/inspect.js`'s `DetailItem`), from what the description
 * says of it (`robotTree.js`'s `robotLinkFacts`): its kind (a root or a link), its planning groups and
 * end effectors; its inertial properties; its visual and collision geometry, a mesh file opening that
 * file (`onOpenFile`); its joint to its parent — name, type, the parent link (pressing it selects that
 * link, `onSelectLink`, where the tree has its row), axis, limits with their units, effort, velocity,
 * mimic, origin — and its child links, a row each with their joint, as what it is connected to. Its hover
 * tip's short kind is its parent joint's type.
 * @param {ReturnType<typeof import("./robotTree.js").robotLinkFacts>} facts
 */
export function robotLinkItem(facts, { reference = "", onOpenFile = null, onSelectLink = null, hasLinkRow = () => true, t = english } = {}) {
  const joint = facts.parentJoint;
  const inertial = t("robot.inertial"), geometry = t("robot.geometry"), parent = t("robot.parentJoint");
  const inertia = facts.inertia;
  const inertiaCopy = inertia ? INERTIA_ROWS.map(row => row.map(term => formatValue(inertia[term], 6)).join(", ")).join("; ") : "";
  const geometryFact = (label, entries) => (entries ? [{ section: geometry, label, copy: false, value: <GeometryValue entries={entries} onOpenFile={onOpenFile}/> }] : []);
  const selectable = Boolean(onSelectLink) && joint && hasLinkRow(joint.parentLink);
  return {
    id: `link:${facts.name}`, pick: facts.name, kind: "solid", title: facts.name, ref: reference,
    tip: joint ? joint.type : t("robot.rootLink"),
    facts: [
      { label: t("robot.type"), value: <>{facts.isRoot ? t("robot.rootLink") : t("robot.link")}</> },
      ...(facts.groups.length ? [{ label: t("robot.groups"), title: t("robot.groupsHint"), value: <>{facts.groups.join(", ")}</> }] : []),
      ...(facts.endEffectors.length ? [{ label: t("robot.endEffector"), value: <>{facts.endEffectors.join(", ")}</> }] : []),
      ...(facts.mass !== null ? [{ section: inertial, label: t("robot.mass"), value: `${formatValue(facts.mass, 4)} kg` }] : []),
      ...(facts.centerOfMass ? [{ section: inertial, label: t("robot.centreOfMass"), title: t("robot.centreOfMassHint"), value: <CoordValue vector={facts.centerOfMass.xyz} digits={4}/> }] : []),
      ...(inertia ? [{ section: inertial, label: t("robot.inertia"), title: t("robot.inertiaHint"), copy: inertiaCopy, value: <InertiaValue inertia={inertia}/> }] : []),
      ...geometryFact(t("robot.visuals"), facts.visuals),
      ...geometryFact(t("robot.collisions"), facts.collisions),
      ...(joint ? [
        { section: parent, label: t("robot.joint"), value: <>{joint.name}</> },
        { section: parent, label: t("robot.jointType"), value: <>{joint.type}</> },
        // A frame-only root has no row to go to; it is still named.
        { section: parent, label: t("robot.parent"), copy: selectable ? false : undefined,
          value: <LinkName name={joint.parentLink} onSelect={onSelectLink} selectable={hasLinkRow(joint.parentLink)}/> },
        ...(joint.axis ? [{ section: parent, label: t("robot.axis"), value: <CoordValue vector={joint.axis} digits={4}/> }] : []),
        ...limitFacts(joint, t, parent),
        ...(joint.mimic ? [{ section: parent, label: t("robot.mimic"), value: `${joint.mimic.joint} × ${formatValue(joint.mimic.multiplier)} + ${formatValue(joint.mimic.offset)}` }] : []),
        // A four-bar's crank follows its driver through the linkage cadgen solved: no formula to show, only the driver.
        ...(joint.fourBar ? [{ section: parent, label: t("robot.fourBarDriver"), value: joint.fourBar.driver }] : []),
        ...(joint.origin ? [{ section: parent, label: t("robot.originXyz"), title: t("robot.originXyzHint"), value: <CoordValue vector={joint.origin.xyz} digits={4}/> },
          ...(!isZero(joint.origin.rpy) ? [{ section: parent, label: t("robot.originRpy"), title: t("robot.originRpyHint"), value: vectorText(joint.origin.rpy) }] : [])] : [])
      ] : [])
    ],
    related: facts.childJoints.length ? { title: t("robot.childJoints"), count: String(facts.childJoints.length),
      rows: facts.childJoints.map(child => ({ id: `child:${child.name}`, kind: "solid", pick: child.childLink, label: child.childLink, detail: `${child.name} · ${child.type}` })) } : null
  };
}

/**
 * A named mesh object, as the frame reads a pick: what a person uses to tell two objects of one link
 * apart — its link, its colour (a cadgen mesh export groups an object BY colour), its triangles and its
 * size.
 */
export function robotComponentItem(component, t = english) {
  const size = component.sizeMillimetres;
  return {
    id: `object:${component.id}`, pick: component.id, kind: "solid", title: component.name || component.link, tip: component.link,
    facts: [
      { label: t("robot.type"), value: <>{t("robot.meshObject")}</> },
      { label: t("robot.link"), value: <>{component.link}</> },
      ...(component.color ? [{ label: t("robot.colour"), value: <span className="inline-flex items-baseline gap-1.5">
        <span className="size-3 shrink-0 self-center rounded-sm border border-border/70" style={{ backgroundColor: component.color }} aria-hidden="true"/>
        <span className="tabular-nums">{component.color}</span>
      </span> }] : []),
      { label: t("robot.triangles"), value: formatCount(component.triangleCount) },
      ...(size ? [{ label: t("robot.size"), title: t("robot.sizeHint"), value: `${size.map(formatMillimetres).join(" × ")} mm` }] : [])
    ],
    related: null
  };
}
