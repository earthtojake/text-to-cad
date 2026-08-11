import {
  Contrast,
  Eye,
  EyeOff,
  Layers,
  Paintbrush,
  Spline,
  SquareDashed
} from "lucide-react";
import { CAD_DISPLAY_MODE } from "cadjs/lib/displaySettings";

export const DISPLAY_MODE_OPTIONS = Object.freeze([
  Object.freeze({ value: CAD_DISPLAY_MODE.SOLID, label: "Solid", title: "Shaded with CAD edges", Icon: Layers }),
  Object.freeze({ value: CAD_DISPLAY_MODE.RENDERED, label: "Rendered", title: "Shaded material theme without edge overlay", Icon: Paintbrush }),
  Object.freeze({ value: CAD_DISPLAY_MODE.TRANSPARENT, label: "X-Ray", title: "Transparent solids with visible CAD edges", Icon: Eye }),
  Object.freeze({ value: CAD_DISPLAY_MODE.HIDDEN_EDGES, label: "Hidden", title: "Shaded with hidden edges visible", Icon: EyeOff }),
  Object.freeze({ value: CAD_DISPLAY_MODE.HIDDEN_LINES_REMOVED, label: "Lines", title: "Visible lines with hidden lines removed", Icon: SquareDashed }),
  Object.freeze({ value: CAD_DISPLAY_MODE.UNSHADED, label: "Flat", title: "Unshaded flat color", Icon: Contrast }),
  Object.freeze({ value: CAD_DISPLAY_MODE.WIREFRAME, label: "Wire", title: "Full wireframe", Icon: Spline })
]);

export function displayModeOptionForValue(value) {
  return DISPLAY_MODE_OPTIONS.find((option) => option.value === value) || DISPLAY_MODE_OPTIONS[0];
}
