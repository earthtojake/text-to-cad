import { useMemo, useState } from 'react';
import { Check, ChevronRight, Circle, Copy, ScanSearch, SquareMousePointer } from 'lucide-react';
import { recognizeStepFeatures } from '@hardcore/core/lib/step/recognizeFeatures.js';
import { Button } from '@hardcore/ui/primitives/button';
import { cn } from '@hardcore/ui/utils';
import { useHostReference } from '../../file-view/hostReference.js';

const number = value => Number(value).toLocaleString(undefined, { maximumFractionDigits: 3 });

/** A part-local, transient read-only layer above the complete geometry tree. */
export default function StepFeatureGroups({ target, runtime, selectedReferenceIds = [], disabled, loading, error, onRequestTopology, onSelect, onCopy }) {
  const host = useHostReference();
  const [request, setRequest] = useState(null);
  const [expanded, setExpanded] = useState(new Set());
  const [feedback, setFeedback] = useState('');
  const [copyFailed, setCopyFailed] = useState(false);
  const result = useMemo(() => request && runtime ? recognizeStepFeatures(runtime, { partId: request.partId }) : null, [request, runtime]);
  const references = runtime?.referenceMap;
  const selected = new Set(selectedReferenceIds);
  const active = result?.groups.find(group => group.faceIds.length === selected.size && group.faceIds.every(id => selected.has(id)));
  const waiting = request && (!result || result.status === 'unavailable');
  const copy = async (group, toPrompt) => {
    setCopyFailed(false);
    try {
      await onCopy(group, { toPrompt });
      setFeedback(toPrompt ? 'Added to prompt' : 'Copied reference');
    } catch (failure) { setCopyFailed(true); setFeedback(failure instanceof Error ? failure.message : 'Could not copy reference'); }
  };
  return <section aria-label="Recognized features" className="border-b border-sidebar-border/60 px-2 py-2">
    <div className="flex min-w-0 flex-wrap items-center justify-between gap-1">
      <span className="text-micro text-sidebar-foreground/55">Features</span>
      <Button variant="ghost" size="sm" className="h-7 gap-1.5 px-2 text-xs" disabled={disabled || !target} title={target ? `Recognize hole and slot walls in ${target.label}` : 'Select one part to recognize its features'} onClick={() => {
        setRequest(target); setExpanded(new Set()); setFeedback(''); onRequestTopology(target);
      }}><ScanSearch className="size-3.5" aria-hidden="true" />Recognize features</Button>
    </div>
    {!request && <p className="py-1 text-micro text-sidebar-foreground/50">{target ? 'Find hole and slot walls without changing the model.' : 'Select one part to find hole and slot walls.'}</p>}
    {request && <div className="truncate py-1 text-micro text-sidebar-foreground/50" title={request.label}>{request.label} · Read-only</div>}
    <div role="status" className="text-micro text-sidebar-foreground/55">
      {waiting ? (error || (loading ? 'Loading this part’s faces…' : 'No face topology available for this part.')) : result?.status === 'too-large' ? 'This part exceeds the recognition limit. Its geometry tree is still available.' : result?.status === 'ready' && !result.groups.length ? 'No supported holes or slots found. All faces are still available below.' : null}
    </div>
    <div className="space-y-px" aria-label="Detected face groups">
      {result?.groups.map(group => {
        const open = expanded.has(group.id), isSelected = active?.id === group.id;
        return <div key={group.id}>
          <div className={cn('flex min-w-0 items-center rounded-md hover:bg-sidebar-accent/50', isSelected && 'bg-sidebar-accent text-sidebar-accent-foreground')}>
            <button type="button" className="grid size-7 shrink-0 place-items-center rounded-sm focus-visible:ring-2 focus-visible:ring-sidebar-ring" aria-label={`${open ? 'Collapse' : 'Expand'} ${group.label}`} aria-expanded={open} onClick={() => setExpanded(current => { const next = new Set(current); if (open) next.delete(group.id); else next.add(group.id); return next; })}>
              <ChevronRight className={cn('size-3.5 text-current/60', open && 'rotate-90')} aria-hidden="true" />
            </button>
            <button type="button" className="flex h-7 min-w-0 flex-1 items-center gap-2 rounded-sm text-left text-xs focus-visible:ring-2 focus-visible:ring-sidebar-ring" aria-label={`Select ${group.label}, ${group.faceIds.length} wall ${group.faceIds.length === 1 ? 'face' : 'faces'}`} aria-pressed={isSelected} disabled={disabled} onClick={() => { setFeedback(''); onSelect(group.faceIds); }}>
              <Circle className={cn('size-3.5 shrink-0 text-current/60', group.kind === 'slot' && 'scale-x-125 scale-y-75')} aria-hidden="true" />
              <span className="truncate">{group.label}</span><span className="ml-auto shrink-0 pr-2 text-micro text-current/45">{group.faceIds.length} {group.faceIds.length === 1 ? 'face' : 'faces'}</span>
            </button>
          </div>
          {open && <div className="ml-3.5 border-l border-sidebar-border/60 pl-3.5">
            {group.faceIds.map(id => <button key={id} type="button" className="block h-7 w-full truncate rounded-md px-2 text-left text-xs text-sidebar-foreground/65 hover:bg-sidebar-accent/50 focus-visible:ring-2 focus-visible:ring-sidebar-ring" title={references?.get(id)?.summary} disabled={disabled} onClick={() => onSelect([id])}>{references?.get(id)?.label || id}</button>)}
          </div>}
        </div>;
      })}
    </div>
    {active && <div className="mt-2 rounded-md border border-sidebar-border/60 p-2" aria-label={`${active.label} details`}>
      <div className="mb-1 flex items-center gap-2 text-xs"><span>{active.label}</span><span className="ml-auto text-micro text-sidebar-foreground/45">Measured</span></div>
      <dl className="space-y-1 text-xs">{active.dimensions.map(d => <div key={d.label} className="flex items-baseline justify-between gap-2"><dt className="text-sidebar-foreground/55">{d.label}</dt><dd className="tabular-nums">{number(d.value)} mm</dd></div>)}</dl>
      <p className="mt-2 text-micro text-sidebar-foreground/50">Selects wall faces; excludes rims and end faces.</p>
      <div className="mt-2 flex flex-wrap gap-1">
        <Button variant="ghost" size="sm" className="h-7 gap-1.5 px-2 text-xs" disabled={disabled} onClick={() => copy(active,false)}><Copy className="size-3.5" aria-hidden="true" />Copy reference</Button>
        {host && <Button variant="ghost" size="sm" className="h-7 gap-1.5 px-2 text-xs" disabled={disabled} onClick={() => copy(active,true)}><SquareMousePointer className="size-3.5" aria-hidden="true" />Add to prompt</Button>}
      </div>
    </div>}
    {feedback && <p role="status" className="mt-1 flex items-center gap-1 text-micro text-sidebar-foreground/65">{!copyFailed && <Check className="size-3" aria-hidden="true" />}{feedback}</p>}
  </section>;
}
