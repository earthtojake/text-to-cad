import { CoordValue, InfoRow, MonoValue } from "./StepReferenceSection.js";

// The Reference pane at the foot of the Components tab: what the selection IS.
//
// A link reads back what the description says about it (its parent joint, limits,
// origin, mass, geometry files); a named mesh object reads back the mesh facts a
// person uses to tell two objects of one link apart. There is no copy button: robot
// formats have no reference grammar a CLI or a skill parses, so a copied locator
// would lead nowhere.

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

function GeometryRows({ label, entries }) {
  if (!entries) return null;
  const files = entries.map(entry => entry.filename || entry.type).filter(Boolean);
  return <InfoRow label={label}>
    <MonoValue>{entries.length}</MonoValue>
    {files.length > 0 && <span className="block text-muted-foreground">{files.map((file, index) => <span key={`${file}:${index}`} className="block">{file}</span>)}</span>}
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

export function RobotLinkDetails({ facts }) {
  const joint = facts.parentJoint;
  return <div className="flex min-w-0 flex-col text-tiny font-normal" aria-label="Link details">
    <InfoRow label="Name">{facts.name}</InfoRow>
    <InfoRow label="Type">{facts.isRoot ? "Root link" : "Link"}</InfoRow>
    {Number.isFinite(facts.mass) && <InfoRow label="Mass"><MonoValue>{`${formatValue(facts.mass, 3)} kg`}</MonoValue></InfoRow>}
    <GeometryRows label="Visuals" entries={facts.visuals}/>
    <GeometryRows label="Collisions" entries={facts.collisions}/>
    {facts.groups.length > 0 && <InfoRow label="Groups" title="SRDF planning groups this link belongs to">{facts.groups.join(", ")}</InfoRow>}
    {facts.endEffectors.length > 0 && <InfoRow label="End effector">{facts.endEffectors.join(", ")}</InfoRow>}
    {joint && <Section label="Parent joint">
      <InfoRow label="Joint">{joint.name}</InfoRow>
      <InfoRow label="Joint type">{joint.type}</InfoRow>
      <InfoRow label="Parent">{joint.parentLink}</InfoRow>
      {joint.axis && <InfoRow label="Axis"><CoordValue vector={joint.axis} digits={4}/></InfoRow>}
      <LimitRows joint={joint}/>
      {joint.mimic && <InfoRow label="Mimic"><MonoValue>{`${joint.mimic.joint} × ${formatValue(joint.mimic.multiplier)} + ${formatValue(joint.mimic.offset)}`}</MonoValue></InfoRow>}
      {joint.origin && <>
        <InfoRow label="Origin xyz" title="Joint origin in the parent link frame, metres"><CoordValue vector={joint.origin.xyz} digits={4}/></InfoRow>
        <InfoRow label="Origin rpy" title="Joint origin roll, pitch and yaw, radians"><MonoValue>{joint.origin.rpy.map(value => formatValue(value)).join("  ")}</MonoValue></InfoRow>
      </>}
    </Section>}
    {facts.childJoints.length > 0 && <Section label="Child joints">
      <InfoRow label="Children"><span className="flex flex-col">
        {facts.childJoints.map(child => <span key={child.name}>{child.childLink}<span className="text-muted-foreground">{` · ${child.name} · ${child.type}`}</span></span>)}
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
