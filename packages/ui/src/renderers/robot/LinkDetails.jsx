import { CoordValue, InfoRow, MonoValue } from "../kit/inspector/referenceRows.jsx";

// The Reference pane at the foot of the Links section: what the selection IS.
//
// A link reads back what the description says about it (its inertial properties, its
// visual and collision geometry, its parent joint with limits and origin); a named
// mesh object reads back the mesh facts a person uses to tell two objects of one link
// apart. What names something else can be followed: a mesh path opens that file, a
// link name selects that link. There is no copy button: robot formats have no
// reference grammar a CLI or a skill parses, so a copied locator would lead nowhere.

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

function Section({ label, children }) {
  return <div className="mt-2 border-t border-sidebar-border/60 pt-2" aria-label={label}>{children}</div>;
}

const LINK_CLASS = "rounded-sm text-left text-sidebar-foreground underline decoration-muted-foreground/50 underline-offset-2 hover:decoration-current focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring [overflow-wrap:anywhere]";
const isZero = vector => vector.every(value => Math.abs(value) < 1e-12);
const isUnit = vector => vector.every(value => Math.abs(value - 1) < 1e-12);
const vectorText = (vector, digits = 4) => vector.map(value => formatValue(value, digits)).join("  ");

/** Another link of the same robot: pressing it selects that link in the tree and the viewport. */
function LinkName({ name, onSelect, selectable = true }) {
  if (!onSelect || !selectable) return name;
  return <button type="button" className={LINK_CLASS} onClick={() => onSelect(name)} title={`Select ${name}`}>{name}</button>;
}

// What a primitive IS, in the description's own metres.
function dimensions(entry) {
  if (entry.type === "box" && entry.size) return `${entry.size.map(value => formatValue(value)).join(" × ")} m`;
  if (entry.type === "cylinder" && entry.radius !== null && entry.length !== null) return `r ${formatValue(entry.radius)} · l ${formatValue(entry.length)} m`;
  if (entry.type === "sphere" && entry.radius !== null) return `r ${formatValue(entry.radius)} m`;
  return "";
}

// One visual or collision: the file or the primitive, then only what the description
// bothered to say (a zero origin and a unit scale are the defaults, not facts).
function GeometryEntry({ entry, meshPath, onOpenFile }) {
  const path = entry.filename ? meshPath?.(entry.filename) : "";
  const detail = [
    entry.type !== "mesh" && dimensions(entry),
    entry.scale && !isUnit(entry.scale) && `scale ${vectorText(entry.scale)}`,
    entry.origin && !isZero(entry.origin.xyz) && `xyz ${vectorText(entry.origin.xyz)}`,
    entry.origin && !isZero(entry.origin.rpy) && `rpy ${vectorText(entry.origin.rpy)}`,
  ].filter(Boolean);
  return <span className="block py-0.5">
    <span className="flex min-w-0 items-baseline gap-1.5">
      {entry.color && <span className="size-2.5 shrink-0 self-center rounded-sm border border-border/70" style={{ backgroundColor: entry.color }} title={entry.materialName || entry.color} aria-hidden="true"/>}
      {entry.filename
        ? path && onOpenFile
          ? <button type="button" className={LINK_CLASS} onClick={() => onOpenFile(path)} title={`Open ${path}`}>{entry.filename}</button>
          : <span>{entry.filename}</span>
        : <span>{entry.type}</span>}
    </span>
    {detail.map(line => <span key={line} className="block font-mono text-micro tabular-nums text-muted-foreground">{line}</span>)}
  </span>;
}

function GeometryRows({ label, entries, meshPath, onOpenFile }) {
  if (!entries) return null;
  return <InfoRow label={label}>
    {entries.length
      ? entries.map((entry, index) => <GeometryEntry key={`${entry.filename || entry.type}:${index}`} {...{ entry, meshPath, onOpenFile }}/>)
      : <span className="text-muted-foreground">None</span>}
  </InfoRow>;
}

// The six terms the description writes, laid out as the symmetric tensor they are.
function InertiaRows({ inertia }) {
  if (!inertia) return null;
  const rows = [["ixx", "ixy", "ixz"], ["ixy", "iyy", "iyz"], ["ixz", "iyz", "izz"]];
  return <InfoRow label="Inertia" title="Inertia tensor about the centre of mass, kg·m², as the description writes it">
    <span className="grid w-fit grid-cols-3 gap-x-3 font-mono tabular-nums">
      {rows.flatMap((row, r) => row.map((term, c) => <span key={`${r}${c}`} className={c < r ? "text-muted-foreground" : undefined}>{formatValue(inertia[term], 6)}</span>))}
    </span>
  </InfoRow>;
}

function LimitRows({ joint }) {
  const limit = joint.limit;
  if (!limit) return null;
  const angular = ANGULAR.has(joint.type);
  const unit = angular ? "rad" : "m";
  const range = Number.isFinite(limit.lower) || Number.isFinite(limit.upper);
  return <>
    {range && <InfoRow label="Limits" title={`Lower and upper position limits, in ${angular ? "radians" : "metres"} as the description writes them`}>
      <MonoValue>{`${formatValue(limit.lower)} … ${formatValue(limit.upper)} ${unit}`}</MonoValue>
      {angular && Number.isFinite(limit.lower) && Number.isFinite(limit.upper) &&
        <span className="block text-muted-foreground">{`${degrees(limit.lower)} … ${degrees(limit.upper)}`}</span>}
    </InfoRow>}
    {Number.isFinite(limit.effort) && <InfoRow label="Effort"><MonoValue>{`${formatValue(limit.effort)} ${angular ? "N·m" : "N"}`}</MonoValue></InfoRow>}
    {Number.isFinite(limit.velocity) && <InfoRow label="Velocity"><MonoValue>{`${formatValue(limit.velocity)} ${angular ? "rad/s" : "m/s"}`}</MonoValue></InfoRow>}
  </>;
}

export function RobotLinkDetails({ facts, meshPath, onOpenFile, onSelectLink, hasLinkRow = () => true }) {
  const joint = facts.parentJoint;
  return <div className="flex min-w-0 flex-col text-tiny font-normal" aria-label="Link details">
    <InfoRow label="Name">{facts.name}</InfoRow>
    <InfoRow label="Type">{facts.isRoot ? "Root link" : "Link"}</InfoRow>
    {facts.groups.length > 0 && <InfoRow label="Groups" title="SRDF planning groups this link belongs to">{facts.groups.join(", ")}</InfoRow>}
    {facts.endEffectors.length > 0 && <InfoRow label="End effector">{facts.endEffectors.join(", ")}</InfoRow>}
    {(facts.mass !== null || facts.inertia) && <Section label="Inertial">
      {facts.mass !== null && <InfoRow label="Mass"><MonoValue>{`${formatValue(facts.mass, 4)} kg`}</MonoValue></InfoRow>}
      {facts.centerOfMass && <InfoRow label="Centre of mass" title="In the link frame, metres"><CoordValue vector={facts.centerOfMass.xyz} digits={4}/></InfoRow>}
      <InertiaRows inertia={facts.inertia}/>
    </Section>}
    <Section label="Geometry">
      <GeometryRows label="Visuals" entries={facts.visuals} {...{ meshPath, onOpenFile }}/>
      <GeometryRows label="Collisions" entries={facts.collisions} {...{ meshPath, onOpenFile }}/>
    </Section>
    {joint && <Section label="Parent joint">
      <InfoRow label="Joint">{joint.name}</InfoRow>
      <InfoRow label="Joint type">{joint.type}</InfoRow>
      <InfoRow label="Parent">{/* A frame-only root has no row to go to; it is still named. */}<LinkName name={joint.parentLink} onSelect={onSelectLink} selectable={hasLinkRow(joint.parentLink)}/></InfoRow>
      {joint.axis && <InfoRow label="Axis"><CoordValue vector={joint.axis} digits={4}/></InfoRow>}
      <LimitRows joint={joint}/>
      {joint.mimic && <InfoRow label="Mimic"><MonoValue>{`${joint.mimic.joint} × ${formatValue(joint.mimic.multiplier)} + ${formatValue(joint.mimic.offset)}`}</MonoValue></InfoRow>}
      {joint.origin && <>
        <InfoRow label="Origin xyz" title="Joint origin in the parent link frame, metres"><CoordValue vector={joint.origin.xyz} digits={4}/></InfoRow>
        {!isZero(joint.origin.rpy) && <InfoRow label="Origin rpy" title="Joint origin roll, pitch and yaw, radians"><MonoValue>{vectorText(joint.origin.rpy)}</MonoValue></InfoRow>}
      </>}
    </Section>}
    {facts.childJoints.length > 0 && <Section label="Child joints">
      <InfoRow label="Children"><span className="flex flex-col items-start">
        {facts.childJoints.map(child => <span key={child.name}><LinkName name={child.childLink} onSelect={onSelectLink}/><span className="text-muted-foreground">{` · ${child.name} · ${child.type}`}</span></span>)}
      </span></InfoRow>
    </Section>}
  </div>;
}

function ComponentDetails({ component }) {
  const size = component.sizeMillimetres;
  return <div className="flex min-w-0 flex-col text-tiny font-normal" aria-label="Component details">
    <InfoRow label="Name">{component.name}</InfoRow>
    <InfoRow label="Type">Mesh object</InfoRow>
    <InfoRow label="Link">{component.linkName}</InfoRow>
    {/* A cadgen mesh export groups an object BY colour, so it tells two rows of one link apart. */}
    {component.color && <InfoRow label="Colour"><span className="inline-flex items-center gap-1.5">
      <span className="size-3 shrink-0 rounded-sm border border-border/70" style={{ backgroundColor: component.color }} aria-hidden="true"/>
      <MonoValue>{component.color}</MonoValue>
    </span></InfoRow>}
    <InfoRow label="Triangles"><MonoValue>{formatCount(component.triangleCount)}</MonoValue></InfoRow>
    {size && <InfoRow label="Size" title="Bounding size of the object on the robot, millimetres"><MonoValue>{`${size.map(formatMillimetres).join(" × ")} mm`}</MonoValue></InfoRow>}
  </div>;
}

export default function RobotComponentDetails({ components, selectedIds }) {
  const selected = components.filter((component) => selectedIds.includes(component.id));
  if (!selected.length) return null;
  if (selected.length > 1) {
    const triangles = selected.reduce((total, component) => total + component.triangleCount, 0);
    return <div className="flex min-w-0 flex-col text-tiny font-normal" aria-label="Component details">
      <p className="py-1 text-micro text-muted-foreground">Selection · {selected.length} components</p>
      <InfoRow label="Links">{[...new Set(selected.map((component) => component.linkName))].join(", ")}</InfoRow>
      <InfoRow label="Triangles"><MonoValue>{formatCount(triangles)}</MonoValue></InfoRow>
    </div>;
  }
  return <ComponentDetails component={selected[0]} />;
}
