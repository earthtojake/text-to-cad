import { cn } from "@text-to-cad/ui/utils";
import { TREE_GLYPH_STROKE } from "@text-to-cad/ui/primitives/tree-row";

/**
 * Study's setup glyphs, drawn as the model draws its markers (`feaMarkers.js`), in lucide's 24px
 * grid at the trees' light stroke: a fixture is a cone pointing into the face it holds, in the
 * markers' muted grey, and a roller (a face that may slide) that cone on a plate that rolls on the
 * face; a load an arrow with a cone for its head, in their ink; a material a swatch.
 */
function Glyph({ className, children }) {
  return <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={TREE_GLYPH_STROKE * 1.5} strokeLinecap="round" strokeLinejoin="round"
    className={cn("size-3 shrink-0", className)} aria-hidden="true">{children}</svg>;
}

const MUTED = "text-muted-foreground";
const INK = "text-foreground/80";
/** A glyph of these shapes in this tone. */
const glyph = (tone, shapes) => function StudyGlyph({ className }) {
  return <Glyph className={cn(tone, className)}>{shapes}</Glyph>;
};

export const STUDY_GLYPHS = Object.freeze({
  fixture: glyph(MUTED, <>
    <path d="M6 3.5h12L12 15z" fill="currentColor" fillOpacity={0.35} />
    <path d="M3.5 19.5h17" />
  </>),
  // A roller: the fixture's cone pressing on a plate that rolls on the face, so the face may slide but not lift.
  roller: glyph(MUTED, <>
    <path d="M7 2.5h10L12 10.5z" fill="currentColor" fillOpacity={0.35} />
    <path d="M6.5 12.5h11" />
    <circle cx="9.25" cy="16.5" r="2" />
    <circle cx="14.75" cy="16.5" r="2" />
    <path d="M3.5 20.5h17" />
  </>),
  load: glyph(INK, <>
    <path d="M3 12h11" />
    <path d="M13.5 6.5 21 12l-7.5 5.5z" fill="currentColor" />
  </>),
  material: glyph(MUTED, <>
    <rect x="4" y="4" width="16" height="16" rx="3.5" fill="currentColor" fillOpacity={0.25} />
    <path d="M8 16 16 8" strokeOpacity={0.6} />
  </>),
});
