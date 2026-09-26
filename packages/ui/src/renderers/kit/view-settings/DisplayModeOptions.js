import {
  Eye,
  Spline,
  SquareDashed
} from "lucide-react";

export function SolidModeIcon(props) {
  return <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" {...props}>
    <circle cx="12" cy="12" r="9" />
  </svg>;
}

export function RenderModeIcon(props) {
  return <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" {...props}>
    <circle cx="12" cy="12" r="9" />
    <path d="M18 11a6 6 0 0 1-6 7" />
    <circle cx="15.5" cy="8" r="1.2" fill="currentColor" stroke="none" />
  </svg>;
}

export const DISPLAY_MODE_OPTIONS = Object.freeze([
  Object.freeze({ value: "solid", label: "Solid", title: "Solid surfaces with visible CAD edges", Icon: SolidModeIcon }),
  Object.freeze({ value: "render", label: "Render", title: "Photographic materials, lighting and backdrop", Icon: RenderModeIcon }),
  Object.freeze({ value: "xray", label: "X-ray", title: "Transparent surfaces with visible and hidden CAD edges", Icon: Eye }),
  Object.freeze({ value: "hidden-line", label: "Hidden line", title: "Visible contours with obscured edges removed", Icon: SquareDashed }),
  Object.freeze({ value: "wireframe", label: "Wireframe", title: "All CAD edges through the model", Icon: Spline })
]);
