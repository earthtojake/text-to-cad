// The display modes' icons, one family: the same sphere, drawn as each mode draws a model — shaded
// with its edge (Solid), shaded alone (Shaded), in parts of their own colour (Parts), see-through
// with its hidden lines (X-ray), its visible lines alone (Hidden line), every line (Wireframe). The
// Grid switch's icon is the floor grid the Grid draws, a tile of it in perspective.
const SPHERE = { viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: "1.7", strokeLinecap: "round", strokeLinejoin: "round" };
// Solid's shading, a hard-edged unlit side: the outline's right half, back up a terminator that
// bulges a little to the right — a drawing's shading.
const Shade = ({ cy = 12, r = 9 }) => <path d={`M12 ${cy - r}a${r} ${r} 0 0 1 0 ${2 * r}a${r * 0.15} ${r} 0 0 0 0-${2 * r}Z`}
  fill="currentColor" fillOpacity="0.45" stroke="none" />;
// The sphere's equator where it faces the viewer: the edge Solid draws over its shading.
const EQUATOR = "M3 12a9 3.5 0 0 0 18 0";

export function SolidModeIcon(props) {
  return <svg {...SPHERE} {...props}><Shade /><circle cx="12" cy="12" r="9" /><path d={EQUATOR} /></svg>;
}

// Solid's shading with no edge: the outline faint, as a silhouette rather than a line.
export function ShadedModeIcon(props) {
  return <svg {...SPHERE} {...props}>
    <circle cx="12" cy="12" r="9" fill="currentColor" fillOpacity="0.12" strokeOpacity="0.45" /><Shade />
  </svg>;
}

// Two parts of the sphere, each its own colour, the edge between them drawn.
export function PartsModeIcon(props) {
  return <svg {...SPHERE} {...props}>
    <path d="M3 12a9 9 0 0 1 18 0a9 3.5 0 0 1-18 0Z" fill="currentColor" fillOpacity="0.5" stroke="none" />
    <path d="M3 12a9 3.5 0 0 0 18 0a9 9 0 0 1-18 0Z" fill="currentColor" fillOpacity="0.15" stroke="none" />
    <circle cx="12" cy="12" r="9" /><path d={EQUATOR} />
  </svg>;
}

export function XRayModeIcon(props) {
  return <svg {...SPHERE} {...props}>
    <circle cx="12" cy="12" r="9" fill="currentColor" fillOpacity="0.12" />
    <path d={EQUATOR} />
    <path d="M3 12a9 3.5 0 0 1 18 0" strokeDasharray="1.5 2" strokeOpacity="0.55" />
  </svg>;
}

export function HiddenLineModeIcon(props) {
  return <svg {...SPHERE} {...props}><circle cx="12" cy="12" r="9" /><path d={`${EQUATOR}M12 3a3.5 9 0 0 0 0 18`} /></svg>;
}

export function WireframeModeIcon(props) {
  return <svg {...SPHERE} {...props}>
    <circle cx="12" cy="12" r="9" />
    <path d={`M3 12h18M12 3a3.5 9 0 0 0 0 18M12 3a3.5 9 0 0 1 0 18${EQUATOR}`} />
  </svg>;
}

// A tile of floor grid in perspective: the Grid switch.
export function GridIcon(props) {
  return <svg {...SPHERE} {...props}>
    <path d="M6.5 6.5h11L22 17.5H2ZM10.2 6.5l-1.5 11M13.8 6.5l1.5 11M4.2 12h15.6" strokeWidth="1.5" />
  </svg>;
}

// Each mode says its name in the view's language by its `key`; `label` and `title` are its English.
export const DISPLAY_MODE_OPTIONS = Object.freeze([
  Object.freeze({ value: "solid", key: "mode.solid", label: "Solid", title: "Shaded surfaces with visible CAD edges", Icon: SolidModeIcon }),
  Object.freeze({ value: "shaded", key: "mode.shaded", label: "Shaded", title: "Shaded surfaces, no edges", Icon: ShadedModeIcon }),
  Object.freeze({ value: "parts", key: "mode.parts", label: "Parts", title: "Each part its own colour, with visible CAD edges", Icon: PartsModeIcon }),
  Object.freeze({ value: "xray", key: "mode.xray", label: "X-ray", title: "Transparent surfaces with visible and hidden CAD edges", Icon: XRayModeIcon }),
  Object.freeze({ value: "hidden-line", key: "mode.hidden-line", label: "Hidden line", title: "Visible contours with obscured edges removed", Icon: HiddenLineModeIcon }),
  Object.freeze({ value: "wireframe", key: "mode.wireframe", label: "Wireframe", title: "All CAD edges through the model", Icon: WireframeModeIcon })
]);
