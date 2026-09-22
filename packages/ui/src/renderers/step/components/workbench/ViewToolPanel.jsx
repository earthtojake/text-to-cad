// The panel an examining toggle (Explode, Cross-section) opens under the interaction
// tools: the Measure panel's surface, wide enough for a slider and its typed value. It is
// there while the toggle is on; the toggle's own button turns it off, so no close button.
const SURFACE = "pointer-events-auto w-60 max-w-full space-y-1 rounded-md border border-border bg-background py-1 text-foreground shadow-sm";

export default function ViewToolPanel({ title, children }) {
  return (
    <section aria-label={title} className={SURFACE}>
      <h3 className="px-2 text-micro leading-4 text-muted-foreground">{title}</h3>
      {children}
    </section>
  );
}
