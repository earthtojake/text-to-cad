import { cn } from "@text-to-cad/ui/utils";
import { TREE_GLYPH_STROKE } from "@text-to-cad/ui/primitives/tree-row";

/**
 * Study's setup glyphs, drawn as the model draws its markers (`feaMarkers.js`), in lucide's 24px
 * grid at the trees' light stroke: a fixture is a cone pointing into the face it holds, in the
 * markers' muted grey; a load an arrow with a cone for its head, in their ink; a material a swatch.
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

export const STUDY_GLYPHS = Object.freeze({ fixture: FixtureGlyph, load: LoadGlyph, material: MaterialGlyph });
