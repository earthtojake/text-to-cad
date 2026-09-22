import { useRef, useState } from 'react';

// The details pane opens at a third of its section. On a short screen a third is too little
// to read, so it never goes below MIN_DETAILS — nor above what leaves the tree MIN_TREE.
const DEFAULT_RATIO = 1 / 3;
const MIN_DETAILS = '11rem';
const MIN_TREE = '7rem';

/** Shared tree/details layout; resizing changes only the space given to inspection. */
export default function InspectorSplit({ children, details, title, actions, label = 'Selection details' }) {
  const [ratio, setRatio] = useState(DEFAULT_RATIO);
  const container = useRef(null);
  const resize = value => setRatio(Math.min(0.65, Math.max(0.2, value)));
  const drag = event => {
    if (!event.currentTarget.hasPointerCapture(event.pointerId)) return;
    const bounds = container.current.getBoundingClientRect();
    resize((bounds.bottom - event.clientY) / bounds.height);
  };
  return <div ref={container} className="flex min-h-0 flex-1 flex-col overflow-hidden">
    <div className="flex min-h-0 flex-1 flex-col overflow-hidden">{children}</div>
    {details && <>
      <div role="separator" tabIndex={0} aria-label="Resize selection details" aria-orientation="horizontal"
        aria-valuemin={20} aria-valuemax={65} aria-valuenow={Math.round(ratio * 100)}
        onKeyDown={event => {
          if (!['ArrowUp', 'ArrowDown', 'Home', 'End'].includes(event.key)) return;
          event.preventDefault();
          resize(event.key === 'Home' ? 0.2 : event.key === 'End' ? 0.65 : ratio + (event.key === 'ArrowUp' ? 0.05 : -0.05));
        }}
        onPointerDown={event => { event.preventDefault(); event.currentTarget.setPointerCapture(event.pointerId); }}
        onPointerMove={drag}
        onPointerUp={event => { if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId); }}
        className="relative z-10 h-px shrink-0 cursor-row-resize touch-none bg-sidebar-border/70 before:absolute before:inset-x-0 before:-top-1 before:h-2 hover:bg-ring focus-visible:bg-ring focus-visible:outline-none" />
      <section aria-label={label} className="flex min-h-0 shrink-0 flex-col overflow-hidden"
        style={{ flexBasis: `${ratio * 100}%`, minHeight: `min(${MIN_DETAILS}, calc(100% - ${MIN_TREE}))` }}>
        <div className="flex h-8 min-w-0 shrink-0 items-center gap-2 px-2">
          <h3 className="min-w-0 flex-1 truncate text-xs font-normal">{title}</h3>
          {actions}
        </div>
        <div className="min-h-0 flex-1 overflow-x-hidden overflow-y-auto px-2 pb-2">{details}</div>
      </section>
    </>}
  </div>;
}
