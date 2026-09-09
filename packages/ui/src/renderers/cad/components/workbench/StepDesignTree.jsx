import { useEffect, useMemo, useState } from 'react';
import { Box, ChevronRight, Circle, Layers, PencilRuler, RotateCw, Scissors, SquareRoundCorner, Variable } from 'lucide-react';
import { ScrollArea } from '@hardcore/ui/primitives/scroll-area';
import { cn } from '@hardcore/ui/utils';
import { resolveDesignFeatureLinks, designFeatureSelection } from '../../workbench/designFeatureSelection.js';
const EMPTY = [];

const title = value => String(value || '').replace(/_/g, ' ').replace(/([a-z])([A-Z])/g, '$1 $2');
const number = value => typeof value === 'number' ? value.toLocaleString(undefined, { maximumFractionDigits: 5 }) : String(value);
const iconFor = type => ({ sketch: PencilRuler, revolve: RotateCw, hole: Circle, fillet: SquareRoundCorner, chamfer: Scissors, pattern: Layers, parameters: Variable })[type] || Box;

function flatten(nodes, expanded, depth = 0) {
  return nodes.flatMap(node => [{ ...node, depth }, ...(expanded.has(node.id) ? flatten(node.children || [], expanded, depth + 1) : [])]);
}

export default function StepDesignTree({ client, file, revision, label, onOpenFile, references = EMPTY, parts = EMPTY, onHighlight, onLoadTopology }) {
  const [state, setState] = useState({ status: 'loading' });
  const [attempt, setAttempt] = useState(0);
  const [expanded, setExpanded] = useState(new Set(['model']));
  const [selectedId, setSelectedId] = useState('model');
  const [selectionRequest, setSelectionRequest] = useState(0);
  const selectRow = id => { setSelectionRequest(value => value + 1); setSelectedId(id); };
  useEffect(() => {
    const controller = new AbortController();
    setState({ status: 'loading' });
    setExpanded(new Set(['model']));
    setSelectedId('model');
    setSelectionRequest(0);
    if (!client?.requestDesignOutline || !file) {
      setState({ status: 'unavailable' });
      return () => controller.abort();
    }
    client.requestDesignOutline(file, { signal: controller.signal }).then(result => {
      if (!controller.signal.aborted) setState(result);
    }).catch(error => {
      if (!controller.signal.aborted) setState({ status: 'error', error: error.message });
    });
    return () => controller.abort();
  }, [client, file, revision, attempt]);

  const roots = useMemo(() => [{ id: 'model', label: label || 'Model', type: 'model', parameters: [], children: [
    ...(state.parameters?.length ? [{ id: 'parameters', label: 'Parameters', type: 'parameters', parameters: state.parameters, children: [] }] : []),
    ...(state.features?.length ? state.features : [{ id: 'imported', label: 'Imported geometry', type: 'imported', parameters: [], children: [] }]),
  ] }], [state, label]);
  const allNodes = useMemo(() => {
    const result = new Map();
    const visit = nodes => nodes.forEach(node => { result.set(node.id, node); visit(node.children || []); });
    visit(roots); return result;
  }, [roots]);
  const selected = allNodes.get(selectedId) || roots[0];
  const resolvedLinks = useMemo(() => resolveDesignFeatureLinks(state.geometryLinks, references, parts), [state.geometryLinks, references, parts]);
  const parent = [...allNodes.values()].find(node => node.children?.some(child => child.id === selected.id));
  const geometrySelection = useMemo(() => designFeatureSelection(selected, resolvedLinks, parent?.line), [selected, resolvedLinks, parent?.line]);
  useEffect(() => {
    if (state.geometryLinks?.faces?.length) onLoadTopology?.();
  }, [state.geometryLinks, onLoadTopology]);
  useEffect(() => {
    onHighlight?.(selectionRequest ? geometrySelection : null);
    return () => onHighlight?.(null);
  }, [geometrySelection, selectionRequest, onHighlight]);
  const rows = flatten(roots, expanded);
  const toggle = id => setExpanded(current => { const next = new Set(current); if (next.has(id)) next.delete(id); else next.add(id); return next; });

  return <div className="flex h-full min-h-0 flex-col" aria-label="Design features" onKeyDown={event => {
    if (event.key === 'Escape') { event.stopPropagation(); setSelectionRequest(0); onHighlight?.(null); }
  }}>
    <div className="flex shrink-0 items-center justify-between gap-2 border-b border-sidebar-border/60 px-3 py-2 text-micro text-muted-foreground">
      <span>{state.source ? 'Source operations' : 'Model features'}</span>
      <div className="flex items-center gap-2"><span>Read-only</span><button type="button" aria-label="Refresh source features" title="Refresh source features" disabled={state.status === 'loading'} className="grid size-6 place-items-center rounded hover:bg-sidebar-accent disabled:opacity-40" onClick={() => setAttempt(value => value + 1)}><RotateCw className="size-3" aria-hidden="true" /></button></div>
    </div>
    {state.status === 'loading' ? <p role="status" className="p-3 text-xs text-muted-foreground">Reading source…</p> : null}
    {state.status === 'error' ? <div role="alert" className="p-3 text-xs text-muted-foreground"><p>{state.error || 'Could not read source features.'}</p><button className="mt-2 underline" onClick={() => setAttempt(value => value + 1)}>Retry</button></div> : null}
    <ScrollArea className="min-h-0 flex-1">
      <div role="tree" aria-label="Features" className="p-1.5">
        {state.status !== 'loading' && rows.map((node, index) => {
          const Icon = iconFor(node.type), hasChildren = Boolean(node.children?.length), open = expanded.has(node.id);
          return <div key={node.id} role="treeitem" aria-level={node.depth + 1} aria-expanded={hasChildren ? open : undefined} aria-selected={selected.id === node.id}
            tabIndex={selected.id === node.id ? 0 : -1} title={node.label}
            className={cn('flex h-8 min-w-0 cursor-default items-center gap-1 rounded-md pr-2 text-xs outline-none hover:bg-sidebar-accent/50 focus-visible:ring-2 focus-visible:ring-sidebar-ring', selected.id === node.id && 'bg-sidebar-accent text-sidebar-accent-foreground')}
            style={{ paddingLeft: 4 + Math.min(node.depth, 6) * 16 }}
            onClick={() => selectRow(node.id)}
            onKeyDown={event => {
              if (event.target !== event.currentTarget) return;
              const elements = event.currentTarget.parentElement.querySelectorAll('[role="treeitem"]');
              const next = event.key === 'ArrowDown' ? index + 1 : event.key === 'ArrowUp' ? index - 1 : event.key === 'Home' ? 0 : event.key === 'End' ? rows.length - 1 : null;
              if (next !== null) { event.preventDefault(); const target = Math.max(0, Math.min(rows.length - 1, next)); selectRow(rows[target].id); elements[target]?.focus(); }
              if ((event.key === 'ArrowRight' && hasChildren && !open) || (event.key === 'ArrowLeft' && hasChildren && open)) { event.preventDefault(); toggle(node.id); }
              else if (event.key === 'ArrowRight' && hasChildren && open) { event.preventDefault(); selectRow(rows[index + 1].id); elements[index + 1]?.focus(); }
              else if (event.key === 'ArrowLeft' && node.depth > 0) { event.preventDefault(); const parentIndex = rows.findLastIndex((row, i) => i < index && row.depth < node.depth); selectRow(rows[parentIndex].id); elements[parentIndex]?.focus(); }
              if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); selectRow(node.id); if (hasChildren) toggle(node.id); }
            }}>
            {hasChildren ? <button type="button" tabIndex={-1} aria-label={`${open ? 'Collapse' : 'Expand'} ${node.label}`} className="grid size-6 shrink-0 place-items-center rounded-sm hover:bg-sidebar-accent" onClick={event => { event.stopPropagation(); selectRow(node.id); toggle(node.id); }}>
              <ChevronRight className={cn('size-3.5 text-current/50', open && 'rotate-90')} aria-hidden="true" />
            </button> : <span className="size-6 shrink-0" />}
            <Icon className="mr-1 size-3.5 shrink-0 text-current/60" aria-hidden="true" /><span className="min-w-0 truncate">{title(node.label)}</span>
          </div>;
        })}
      </div>
    </ScrollArea>
    {selected.type !== 'model' && <section aria-label="Feature properties" className="max-h-[32%] shrink-0 overflow-y-auto border-t border-sidebar-border/70 px-3 py-2.5">
      <h3 className="mb-2 text-xs">{title(selected.label)}</h3>
      {selected.parameters?.length ? <dl className="space-y-2 text-xs">{selected.parameters.map((param, i) => <div key={`${param.name}:${i}`} className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
        <dt className="text-muted-foreground">{title(param.name)}</dt><dd title={param.expression} className="max-w-full break-words text-right tabular-nums">{param.value == null ? param.expression : number(param.value)}</dd>
      </div>)}</dl> : <p className="text-xs text-muted-foreground">{selected.type === 'imported' ? 'This STEP contains geometry, not an authored feature history.' : selected.type === 'model' ? 'Select an operation to inspect its parameters.' : 'No static parameter values available.'}</p>}
      {selected.line && <p className="mt-3 text-micro text-muted-foreground">{geometrySelection?.partIds.length ? `${geometrySelection.partIds.length} associated ${geometrySelection.partIds.length === 1 ? "part" : "parts"}` : geometrySelection?.faceIds.length ? `${geometrySelection.faceIds.length} associated ${geometrySelection.faceIds.length === 1 ? "face" : "faces"}` : state.geometryLinks ? 'No matching geometry available' : 'Rebuild this model to link its geometry'}</p>}
    </section>}
    <div className="shrink-0 border-t border-sidebar-border/60 px-3 py-2 text-micro text-muted-foreground">
      {state.source ? <><button className="max-w-full truncate text-left underline-offset-2 hover:underline" title={state.source} onClick={() => onOpenFile?.(state.source)}>{state.source.split('/').pop()}</button></> : <p>{state.status === 'ambiguous' ? 'Multiple source candidates. No feature history was assumed.' : state.status === 'loading' ? 'Reading matching source without running it.' : 'No source feature history available.'}</p>}
    </div>
  </div>;
}
