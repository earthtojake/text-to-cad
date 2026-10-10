import { cn } from "@text-to-cad/ui/utils";
import { TREE_GLYPH_STROKE } from "@text-to-cad/ui/primitives/tree-row";

/**
 * Study's setup glyphs, drawn as the model draws its markers (`feaMarkers.js`), in lucide's 24px
 * grid at the trees' light stroke: a fixture is a cone pointing into the face it holds, in the
 * markers' muted grey, and a roller (a face that may slide) that cone on a plate that rolls on the
 * face; a load an arrow with a cone for its head, in their ink; a material a swatch.
 * Another analysis's setup in the same two tones, as its markers are: a thermometer (a fixed
 * temperature, grey), a flame (heat, ink), wind (the air that cools it, grey), a wave (the shaker,
 * ink), a drop (ink), the flow (ink) and a plane (a rigid floor, grey).
 */
function Glyph({ className, children }) {
  return <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={TREE_GLYPH_STROKE * 1.5} strokeLinecap="round" strokeLinejoin="round"
    className={cn("size-3 shrink-0", className)} aria-hidden="true">{children}</svg>;
}

export function FixtureGlyph({ className }) {
  return <Glyph className={cn("text-muted-foreground", className)}>
    <path d="M6 3.5h12L12 15z" fill="currentColor" fillOpacity={0.35} />
    <path d="M3.5 19.5h17" />
  </Glyph>;
}

/** A roller: the fixture's cone pressing on a plate that rolls on the face, so the face may slide but not lift. */
export function RollerGlyph({ className }) {
  return <Glyph className={cn("text-muted-foreground", className)}>
    <path d="M7 2.5h10L12 10.5z" fill="currentColor" fillOpacity={0.35} />
    <path d="M6.5 12.5h11" />
    <circle cx="9.25" cy="16.5" r="2" />
    <circle cx="14.75" cy="16.5" r="2" />
    <path d="M3.5 20.5h17" />
  </Glyph>;
}

export function LoadGlyph({ className }) {
  return <Glyph className={cn("text-foreground/80", className)}>
    <path d="M3 12h11" />
    <path d="M13.5 6.5 21 12l-7.5 5.5z" fill="currentColor" />
  </Glyph>;
}

export function MaterialGlyph({ className }) {
  return <Glyph className={cn("text-muted-foreground", className)}>
    <rect x="4" y="4" width="16" height="16" rx="3.5" fill="currentColor" fillOpacity={0.25} />
    <path d="M8 16 16 8" strokeOpacity={0.6} />
  </Glyph>;
}

export function TemperatureGlyph({ className }) {
  return <Glyph className={cn("text-muted-foreground", className)}>
    <path d="M14 14.76V4.5a2 2 0 0 0-4 0v10.26a4 4 0 1 0 4 0z" />
    <circle cx="12" cy="17.5" r="1.6" fill="currentColor" />
  </Glyph>;
}

export function HeatGlyph({ className }) {
  return <Glyph className={cn("text-foreground/80", className)}>
    <path d="M12 21c-3.5 0-6-2.4-6-5.7 0-3.3 2.6-5.1 3.5-8.3 1.6 1.2 2.4 2.9 2.5 4.6 1-.7 1.6-1.8 1.8-3.1 2.4 1.9 4.2 4.3 4.2 6.8C18 18.6 15.5 21 12 21z" fill="currentColor" fillOpacity={0.2} />
  </Glyph>;
}

export function ConvectionGlyph({ className }) {
  return <Glyph className={cn("text-muted-foreground", className)}>
    <path d="M3 8h10.5a2.5 2.5 0 1 0-2.5-2.5" />
    <path d="M3 12h15.5a2.5 2.5 0 1 1-2.5 2.5" />
    <path d="M3 16h7" />
  </Glyph>;
}

export function WaveGlyph({ className }) {
  return <Glyph className={cn("text-foreground/80", className)}>
    <path d="M2 12c1.7-4 3.3-4 5 0s3.3 4 5 0 3.3-4 5 0 3.3 4 5 0" />
  </Glyph>;
}

export function DropGlyph({ className }) {
  return <Glyph className={cn("text-foreground/80", className)}>
    <path d="M12 3v11" />
    <path d="M7.5 11 12 16.5 16.5 11" />
    <path d="M4 20.5h16" />
  </Glyph>;
}

export function FlowGlyph({ className }) {
  return <Glyph className={cn("text-foreground/80", className)}>
    <path d="M3 8h13" />
    <path d="M3 16h13" />
    <path d="M14 4.5 20 8l-6 3.5" />
    <path d="M14 12.5 20 16l-6 3.5" />
  </Glyph>;
}

export function PlaneGlyph({ className }) {
  return <Glyph className={cn("text-muted-foreground", className)}>
    <path d="M6 9h15l-3 8H3z" fill="currentColor" fillOpacity={0.25} />
  </Glyph>;
}

export const STUDY_GLYPHS = Object.freeze({
  fixture: FixtureGlyph, roller: RollerGlyph, load: LoadGlyph, material: MaterialGlyph, temperature: TemperatureGlyph, heat: HeatGlyph,
  convection: ConvectionGlyph, wave: WaveGlyph, drop: DropGlyph, flow: FlowGlyph, plane: PlaneGlyph,
});
