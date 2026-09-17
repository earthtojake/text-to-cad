import {
  FILE_SHEET_FIELD_LABEL_CLASSES,
  FileSheetFieldGrid,
  FileSheetStatusText,
  FileSheetSubsection,
  FileSheetValueField
} from "./FileSheet";

// What the selected object IS, at the foot of the Components tab.
//
// This replaced a locator string with a copy button. The locator named the object in a
// grammar no CLI and no skill parses, so copying it led nowhere; these are facts a
// person reads to decide whether they picked the right thing. The colour is first
// because a cadgen mesh export groups an object BY colour, so it is the attribute that
// tells two rows of one link apart.

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

// Full width: three numbers and two separators do not fit half a sidebar, and a
// truncated size ("89.2 x 31.3 x 4...") is worse than no size at all.
function SizeField({ sizeMillimetres }) {
  if (!sizeMillimetres) return null;
  const [x, y, z] = sizeMillimetres.map(formatMillimetres);
  return (
    <div className="col-span-2 min-w-0">
      <FileSheetValueField label="Size (mm)" value={`${x} × ${y} × ${z}`} mono />
    </div>
  );
}

function ColorField({ color }) {
  if (!color) return null;
  return (
    <div className="block min-w-0">
      <span className={FILE_SHEET_FIELD_LABEL_CLASSES}>Colour</span>
      <div className="mt-1 flex min-h-7 min-w-0 items-center gap-2 rounded-md border border-border/70 bg-muted/25 px-2 py-1">
        <span
          className="size-3.5 shrink-0 rounded-sm border border-border/70"
          style={{ backgroundColor: color }}
          aria-hidden="true"
        />
        <span className="truncate font-mono text-[11px] font-medium leading-4 tabular-nums text-foreground">{color}</span>
      </div>
    </div>
  );
}

function ComponentDetails({ component }) {
  return (
    <FileSheetSubsection title={component.name}>
      <FileSheetFieldGrid columns={2}>
        <FileSheetValueField label="Link" value={component.linkName} />
        <ColorField color={component.color} />
        <div className="col-span-2 min-w-0">
          <FileSheetValueField label="Triangles" value={formatCount(component.triangleCount)} mono />
        </div>
        <SizeField sizeMillimetres={component.sizeMillimetres} />
      </FileSheetFieldGrid>
    </FileSheetSubsection>
  );
}

export default function RobotComponentDetails({ components, selectedIds }) {
  const selected = components.filter((component) => selectedIds.includes(component.id));
  if (!selected.length) return null;
  if (selected.length > 1) {
    const triangles = selected.reduce((total, component) => total + component.triangleCount, 0);
    return (
      <FileSheetSubsection title={`${selected.length} components selected`}>
        <FileSheetFieldGrid columns={2}>
          <FileSheetValueField
            label="Links"
            value={[...new Set(selected.map((component) => component.linkName))].join(", ")}
          />
          <FileSheetValueField label="Triangles" value={formatCount(triangles)} mono />
        </FileSheetFieldGrid>
        <FileSheetStatusText>Select one component to see its size and colour.</FileSheetStatusText>
      </FileSheetSubsection>
    );
  }
  return <ComponentDetails component={selected[0]} />;
}
