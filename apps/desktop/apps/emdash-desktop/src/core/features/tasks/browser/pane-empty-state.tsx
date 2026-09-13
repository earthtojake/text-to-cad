/**
 * Tasks begin in chat. Artifact panes are opened only by an actual file or
 * generated output, so an empty pane must not invent a second CAD-creation
 * workflow beside the composer.
 */
export function PaneEmptyState() {
  return <div className="h-full bg-background" aria-hidden="true" />;
}
