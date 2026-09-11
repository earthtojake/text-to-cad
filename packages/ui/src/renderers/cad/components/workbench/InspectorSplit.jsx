import { useRef, useState } from 'react';
import { ChevronRight } from 'lucide-react';
import { cn } from '@hardcore/ui/utils';

/** Shared tree/details layout; resizing changes only the space given to inspection. */
export default function InspectorSplit({ children, details, title, titleTooltip, actions, label = 'Selection details' }) {
  const [collapsed, setCollapsed] = useState(false);
  const [ratio, setRatio] = useState(0.32);
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
      {!collapsed && <div role="separator" tabIndex={0} aria-label="Resize selection details" aria-orientation="horizontal"
        aria-valuemin={20} aria-valuemax={65} aria-valuenow={Math.round(ratio * 100)}
        onKeyDown={event => {
          if (!['ArrowUp', 'ArrowDown', 'Home', 'End'].includes(event.key)) return;
          event.preventDefault();
          resize(event.key === 'Home' ? 0.2 : event.key === 'End' ? 0.65 : ratio + (event.key === 'ArrowUp' ? 0.05 : -0.05));
        }}
        onPointerDown={event => { event.preventDefault(); event.currentTarget.setPointerCapture(event.pointerId); }}
        onPointerMove={drag}
        onPointerUp={event => { if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId); }}
        className="relative z-10 h-px shrink-0 cursor-row-resize touch-none bg-sidebar-border/70 before:absolute before:inset-x-0 before:-top-1 before:h-2 hover:bg-ring focus-visible:bg-ring focus-visible:outline-none" />}
      <section aria-label={label} className={cn('flex min-h-0 shrink-0 flex-col overflow-hidden', collapsed && 'border-t border-sidebar-border/70')}
        style={collapsed ? undefined : { flexBasis: `${ratio * 100}%` }}>
        <div className="flex min-w-0 shrink-0 items-center pr-2">
        <button type="button" aria-label={collapsed ? 'Show selection details' : 'Hide selection details'} aria-expanded={!collapsed}
          onClick={() => setCollapsed(value => !value)} className="flex h-9 min-w-0 flex-1 items-center gap-1.5 px-2 text-left text-xs hover:bg-sidebar-accent/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring">
          <ChevronRight className={cn('size-3.5 shrink-0 text-muted-foreground', !collapsed && 'rotate-90')} aria-hidden="true" />
          <span className="min-w-0 flex-1 truncate" title={titleTooltip ?? (typeof title === 'string' ? title : undefined)}>{title}</span>
        </button>
        {actions}
        </div>
        <div hidden={collapsed} className="min-h-0 flex-1 overflow-x-hidden overflow-y-auto px-2 pb-2">{details}</div>
      </section>
    </>}
  </div>;
}
