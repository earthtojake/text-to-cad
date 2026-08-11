import { useEffect, useRef, useState } from "react";
import { Check, ChevronLeft, ChevronRight, Copy, SquareMousePointer } from "lucide-react";
import { cn } from "@/ui/utils";
import { copyTextToClipboard } from "@/ui/clipboard";
import { FILE_SHEET_SECTION_IDS } from "@/workbench/fileSheetSections";
import { Button } from "../ui/button";

// A selected "element" is either a topology reference (face / edge / solid,
// carrying reference.pickData) or an assembly node (component / subassembly).
// All values below come straight off the selection objects — no extra geometry
// work — mirroring the per-selection readouts in Onshape / Fusion / SolidWorks.

const SELECTOR_TYPE_LABELS = Object.freeze({
  face: "Face",
  edge: "Edge",
  shape: "Solid",
  occurrence: "Component"
});

const SURFACE_LABELS = Object.freeze({
  plane: "Planar",
  cylinder: "Cylindrical",
  cone: "Conical",
  sphere: "Spherical",
  torus: "Toroidal",
  spline: "Freeform",
  bspline: "Freeform",
  nurbs: "Freeform"
});

const CURVE_LABELS = Object.freeze({
  line: "Line",
  circle: "Circle",
  arc: "Arc",
  ellipse: "Ellipse",
  spline: "Spline",
  bspline: "Spline"
});

// Onshape-style axis colour coding for coordinate triples.
const AXES = Object.freeze([
  { key: "X", className: "text-rose-500 dark:text-rose-400" },
  { key: "Y", className: "text-emerald-500 dark:text-emerald-400" },
  { key: "Z", className: "text-sky-500 dark:text-sky-400" }
]);

const SUMMARY_PATTERN = /^(.*?)\s+(area|length|volume)\s*=\s*([-\d.eE+]+)\s*$/;

function titleCase(value) {
  const text = String(value || "").trim();
  return text ? text.charAt(0).toUpperCase() + text.slice(1) : "";
}

function formatNumber(value, digits = 2) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) {
    return "—";
  }
  return numeric.toLocaleString(undefined, { maximumFractionDigits: digits });
}

function parseSummary(summary) {
  const text = String(summary || "").trim();
  const match = text.match(SUMMARY_PATTERN);
  if (match) {
    return { subtype: match[1].trim(), measureKey: match[2], measureValue: Number(match[3]) };
  }
  return { subtype: text, measureKey: null, measureValue: null };
}

function readBbox(source) {
  const bbox = source?.bbox || source?.boundingBox || null;
  const min = Array.isArray(bbox?.min) ? bbox.min : null;
  const max = Array.isArray(bbox?.max) ? bbox.max : null;
  if (!min || !max) {
    return null;
  }
  const dims = [0, 1, 2].map((axis) => Math.abs((Number(max[axis]) || 0) - (Number(min[axis]) || 0)));
  const center = [0, 1, 2].map((axis) => ((Number(min[axis]) || 0) + (Number(max[axis]) || 0)) / 2);
  return dims.some((value) => value > 1e-9) ? { dims, center } : null;
}

function radiusFromParams(params) {
  if (!params || typeof params !== "object") {
    return null;
  }
  const candidate = params.radius ?? params.radius1 ?? params.majorRadius ?? params.minorRadius;
  const numeric = Number(candidate);
  return Number.isFinite(numeric) && numeric > 0 ? numeric : null;
}

function isPartNode(item) {
  return Boolean(item) && !item.pickData && (item.nodeType || Array.isArray(item.children));
}

function CopyButton({ text, className }) {
  const [copied, setCopied] = useState(false);
  const timerRef = useRef(null);
  useEffect(() => () => {
    if (timerRef.current) {
      clearTimeout(timerRef.current);
    }
  }, []);
  if (!text) {
    return null;
  }
  return (
    <Button
      type="button"
      variant="ghost"
      size="icon-xs"
      className={cn("size-5 text-muted-foreground hover:text-foreground", className)}
      aria-label="Copy reference"
      title="Copy reference"
      onClick={() => {
        copyTextToClipboard(text);
        setCopied(true);
        if (timerRef.current) {
          clearTimeout(timerRef.current);
        }
        timerRef.current = setTimeout(() => setCopied(false), 1200);
      }}
    >
      {copied ? (
        <Check className="size-3 text-emerald-500" strokeWidth={2.5} aria-hidden="true" />
      ) : (
        <Copy className="size-3" strokeWidth={2} aria-hidden="true" />
      )}
    </Button>
  );
}

function DetailHeader({ typeLabel, subtitle, selector, copyText }) {
  return (
    <>
      <div className="flex items-center gap-2 px-2 pb-1.5 pt-1">
        {subtitle ? (
          <span className="min-w-0 truncate text-[11px] font-medium text-sidebar-foreground">{subtitle}</span>
        ) : null}
        <span className="shrink-0 rounded-sm bg-muted px-1 py-0.5 font-mono text-[10px] text-muted-foreground">
          {typeLabel}
        </span>
        <span className="ml-auto inline-flex shrink-0 items-center gap-1">
          {selector ? (
            <code className="max-w-[8rem] truncate rounded-sm bg-muted px-1 py-0.5 font-mono text-[10px] text-muted-foreground">
              {selector}
            </code>
          ) : null}
          <CopyButton text={copyText} />
        </span>
      </div>
      <div className="mx-2 h-px bg-sidebar-border/60" />
    </>
  );
}

// Label-column rows keep the value next to its label instead of pushing it to
// the far edge, so the readout scans top-to-bottom.
function InfoRow({ label, children }) {
  return (
    <div className="flex items-baseline gap-3 px-2 py-1">
      <span className="w-[4.5rem] shrink-0 text-[11px] text-muted-foreground">{label}</span>
      <div className="min-w-0 flex-1 text-[11px] text-sidebar-foreground">{children}</div>
    </div>
  );
}

function MonoValue({ children }) {
  return <span className="font-mono tabular-nums">{children}</span>;
}

function CoordValue({ vector, digits = 2 }) {
  const values = Array.isArray(vector) ? vector : [];
  return (
    <span className="flex flex-wrap items-baseline gap-x-3 gap-y-0.5 font-mono tabular-nums">
      {AXES.map((axis, index) => (
        <span key={axis.key} className="inline-flex items-baseline gap-1">
          <span className={cn("text-[9px] font-semibold", axis.className)}>{axis.key}</span>
          <span>{formatNumber(values[index], digits)}</span>
        </span>
      ))}
    </span>
  );
}

function TopologyDetail({ reference }) {
  const pick = reference.pickData || {};
  const type = reference.selectorType;
  const parsed = parseSummary(reference.summary);
  let subtype = "";
  if (type === "face") {
    subtype = SURFACE_LABELS[pick.surfaceType] || titleCase(pick.surfaceType || parsed.subtype);
  } else if (type === "edge") {
    subtype = CURVE_LABELS[parsed.subtype] || titleCase(parsed.subtype);
  } else {
    subtype = titleCase(pick.kind || parsed.subtype);
  }
  const box = readBbox(pick);
  const radius = radiusFromParams(pick.params);
  const measureLabel = parsed.measureKey === "area"
    ? "Area"
    : parsed.measureKey === "length"
      ? "Length"
      : parsed.measureKey === "volume"
        ? "Volume"
        : null;
  const measureUnit = parsed.measureKey === "area" ? "mm²" : parsed.measureKey === "volume" ? "mm³" : "mm";
  const center = Array.isArray(pick.center) ? pick.center : box?.center;
  const component = String(pick.sourceName || pick.name || reference.occurrenceId || "").trim();

  return (
    <div className="flex min-w-0 flex-col">
      <DetailHeader
        typeLabel={SELECTOR_TYPE_LABELS[type] || "Reference"}
        subtitle={subtype}
        selector={String(reference.displaySelector || reference.normalizedSelector || "").trim()}
        copyText={reference.copyText}
      />
      <div className="flex flex-col py-0.5">
        {measureLabel && Number.isFinite(parsed.measureValue) ? (
          <InfoRow label={measureLabel}>
            <MonoValue>{`${formatNumber(parsed.measureValue)} ${measureUnit}`}</MonoValue>
          </InfoRow>
        ) : null}
        {radius != null ? (
          <InfoRow label="Radius"><MonoValue>{`${formatNumber(radius)} mm`}</MonoValue></InfoRow>
        ) : null}
        {box ? (
          <InfoRow label="Size">
            <MonoValue>{`${formatNumber(box.dims[0])} × ${formatNumber(box.dims[1])} × ${formatNumber(box.dims[2])} mm`}</MonoValue>
          </InfoRow>
        ) : null}
        {Array.isArray(center) ? (
          <InfoRow label="Center"><CoordValue vector={center} /></InfoRow>
        ) : null}
        {Array.isArray(pick.normal) ? (
          <InfoRow label="Normal"><CoordValue vector={pick.normal} digits={3} /></InfoRow>
        ) : null}
        {component ? <InfoRow label="Component">{component}</InfoRow> : null}
      </div>
    </div>
  );
}

function PartDetail({ node }) {
  const isAssembly =
    String(node.nodeType || "").trim() === "assembly" ||
    (Array.isArray(node.children) && node.children.length > 0);
  const name = String(node.name || node.displayName || "").trim();
  const selector = String(node.displaySelector || node.occurrenceId || node.id || "").trim();
  const partCount = Array.isArray(node.leafPartIds)
    ? node.leafPartIds.length
    : Array.isArray(node.children)
      ? node.children.length
      : 0;
  const box = readBbox(node);

  return (
    <div className="flex min-w-0 flex-col">
      <DetailHeader
        typeLabel={isAssembly ? "Subassembly" : "Component"}
        subtitle={name}
        selector={selector}
        copyText={node.copyText || selector}
      />
      <div className="flex flex-col py-0.5">
        {isAssembly && partCount > 0 ? (
          <InfoRow label="Parts"><MonoValue>{formatNumber(partCount, 0)}</MonoValue></InfoRow>
        ) : null}
        {box ? (
          <InfoRow label="Size">
            <MonoValue>{`${formatNumber(box.dims[0])} × ${formatNumber(box.dims[1])} × ${formatNumber(box.dims[2])} mm`}</MonoValue>
          </InfoRow>
        ) : null}
        {box ? <InfoRow label="Center"><CoordValue vector={box.center} /></InfoRow> : null}
        {selector ? <InfoRow label="Path">{selector}</InfoRow> : null}
      </div>
    </div>
  );
}

function ElementDetail({ item }) {
  if (!item) {
    return null;
  }
  return isPartNode(item) ? <PartDetail node={item} /> : <TopologyDetail reference={item} />;
}

function itemKey(item) {
  return String(item?.id || item?.occurrenceId || item?.displaySelector || "").trim();
}

export function StepReferenceSection({ references = [] }) {
  const items = Array.isArray(references) ? references.filter(Boolean) : [];
  const count = items.length;
  const idsKey = items.map(itemKey).join("|");
  const [index, setIndex] = useState(0);

  // When the selection set changes, jump to the most recently added element.
  useEffect(() => {
    setIndex(count > 0 ? count - 1 : 0);
  }, [idsKey, count]);

  if (!count) {
    return (
      <div className="flex min-h-[4.5rem] flex-col items-center justify-center gap-1.5 px-4 py-5 text-center">
        <SquareMousePointer className="size-4 text-muted-foreground/45" strokeWidth={1.5} aria-hidden="true" />
        <p className="text-[11px] text-muted-foreground">Select geometry to inspect</p>
      </div>
    );
  }

  const safeIndex = Math.min(Math.max(index, 0), count - 1);

  return (
    <div className="flex min-w-0 flex-col pb-2">
      {count > 1 ? (
        <div className="flex items-center justify-between gap-2 border-b border-sidebar-border/60 px-2 py-1">
          <span className="text-[11px] text-muted-foreground">{count} selected</span>
          <div className="inline-flex items-center gap-0.5">
            <Button
              type="button"
              variant="ghost"
              size="icon-xs"
              className="size-5 text-muted-foreground hover:text-foreground"
              aria-label="Previous element"
              title="Previous element"
              onClick={() => setIndex((current) => (current - 1 + count) % count)}
            >
              <ChevronLeft className="size-3.5" strokeWidth={2} aria-hidden="true" />
            </Button>
            <span className="min-w-[2.75rem] text-center font-mono text-[11px] tabular-nums text-sidebar-foreground">
              {safeIndex + 1} / {count}
            </span>
            <Button
              type="button"
              variant="ghost"
              size="icon-xs"
              className="size-5 text-muted-foreground hover:text-foreground"
              aria-label="Next element"
              title="Next element"
              onClick={() => setIndex((current) => (current + 1) % count)}
            >
              <ChevronRight className="size-3.5" strokeWidth={2} aria-hidden="true" />
            </Button>
          </div>
        </div>
      ) : null}
      <ElementDetail item={items[safeIndex]} />
    </div>
  );
}

export function buildStepReferenceTab({ references = [] } = {}) {
  const count = Array.isArray(references) ? references.filter(Boolean).length : 0;
  return {
    id: FILE_SHEET_SECTION_IDS.STEP_REFERENCE,
    title: (
      <span className="flex min-w-0 items-center gap-1.5">
        <span>Reference</span>
        {count > 1 ? (
          <span className="rounded-full bg-accent px-1.5 text-[10px] font-medium tabular-nums text-accent-foreground">
            {count}
          </span>
        ) : null}
      </span>
    ),
    content: <StepReferenceSection references={references} />
  };
}
