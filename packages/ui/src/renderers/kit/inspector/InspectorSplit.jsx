import { useContext, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { FilePanelReferenceContext } from './FilePanelSections.jsx';

// The details pane opens at a third of the space it shares. On a short screen a third is
// too little to read, so it never goes below MIN_DETAILS — nor above what leaves MIN_REST.
const DEFAULT_RATIO = 1 / 3;
const MIN_DETAILS = '11rem';
const MIN_REST = '7rem';

/**
 * A tree and the details of what is picked in it. In a file's panel the details are pinned
 * at the panel's foot (`FilePanelReferenceContext`), under every section; anywhere else they
 * sit under the tree. Resizing changes only the space given to the details.
 */
export default function InspectorSplit({ children, details, title, actions, label = 'Selection details' }) {
  const reference = useContext(FilePanelReferenceContext);
  const [ratio, setRatio] = useState(DEFAULT_RATIO);
  const container = useRef(null);
  const resize = value => setRatio(Math.min(0.65, Math.max(0.2, value)));
  const drag = event => {
    if (!event.currentTarget.hasPointerCapture(event.pointerId)) return;
    // The space the details share: the whole panel at its foot, else this split.
    const bounds = (reference ? reference.parentElement : container.current).getBoundingClientRect();
    resize((bounds.bottom - event.clientY) / bounds.height);
  };
  const pane = details ? <>
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
      style={{ flexBasis: `${ratio * 100}%`, minHeight: `min(${MIN_DETAILS}, calc(100% - ${MIN_REST}))` }}>
      <div className="flex h-8 min-w-0 shrink-0 items-center gap-2 px-2">
        <h3 className="min-w-0 flex-1 truncate text-xs font-normal">{title}</h3>
        {actions}
      </div>
      <div className="min-h-0 flex-1 overflow-x-hidden overflow-y-auto px-2 pb-2">{details}</div>
    </section>
  </> : null;
  // In a panel the tree takes its full height in the panel's one scroller, and the details go
  // to the panel's foot — which may not be mounted yet (`null`) for the one commit before it is.
  if (reference !== undefined) return <div className="flex flex-col">
    {children}
    {reference && pane ? createPortal(pane, reference) : null}
  </div>;
  return <div ref={container} className="flex min-h-0 flex-1 flex-col overflow-hidden">
    <div className="flex min-h-0 flex-1 flex-col overflow-hidden">{children}</div>
    {pane}
  </div>;
}
