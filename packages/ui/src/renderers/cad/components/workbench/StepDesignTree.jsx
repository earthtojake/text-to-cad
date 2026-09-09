import { useEffect, useMemo, useState } from 'react';
import { Box, ChevronRight, Circle, Eye, EyeOff, Focus, Layers, PencilRuler, Plus, RotateCw, Scissors, SquareRoundCorner, Variable, X } from 'lucide-react';
import { ScrollArea } from '@hardcore/ui/primitives/scroll-area';
import { Button } from '@hardcore/ui/primitives/button';
import { cn } from '@hardcore/ui/utils';
import { resolveDesignFeatureLinks, designFeatureSelection } from '../../workbench/designFeatureSelection.js';
import { groupDesignFeatures, sourceParameterNode } from '../../workbench/designFeatureTree.js';
import { designFeatureMeasurements } from '../../workbench/designFeatureMeasurements.js';
const EMPTY = [];
const measurement = value => value.toLocaleString(undefined, { maximumFractionDigits: 2 });

const title = value => String(value || '').replace(/_/g, ' ').replace(/([a-z])([A-Z])/g, '$1 $2');
const number = value => typeof value === 'number' ? value.toLocaleString(undefined, { maximumFractionDigits: 5 }) : String(value);
const iconFor = type => ({ sketch: PencilRuler, revolve: RotateCw, hole: Circle, fillet: SquareRoundCorner, chamfer: Scissors, pattern: Layers, parameters: Variable, parameter: Variable, group: Layers })[type] || Box;

function flatten(nodes, expanded, depth = 0) {
  return nodes.flatMap(node => [{ ...node, depth }, ...(expanded.has(node.id) ? flatten(node.children || [], expanded, depth + 1) : [])]);
}

export default function StepDesignTree({ client, file, revision, label, onOpenFile, references = EMPTY, parts = EMPTY, onHighlight, onLoadTopology, onAddToPrompt, partActions }) {
  const [state, setState] = useState({ status: 'loading' });
  const [attempt, setAttempt] = useState(0);
  const [expanded, setExpanded] = useState(new Set(['model', 'parts']));
  const [selectedId, setSelectedId] = useState('model');
  const [selectionRequest, setSelectionRequest] = useState(0);
  const [selectedParameter, setSelectedParameter] = useState(null);
  const selectRow = id => { setSelectedParameter(null); setSelectionRequest(value => value + 1); setSelectedId(id); };
  useEffect(() => {
    const controller = new AbortController();
    setState({ status: 'loading' });
    setExpanded(new Set(['model', 'parts']));
    setSelectedId('model');
    setSelectedParameter(null);
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

  const resolvedLinks = useMemo(() => resolveDesignFeatureLinks(state.geometryLinks, references, parts) || (!state.source ? {
    parts: parts.map(part => part.id), faces: parts.length ? [] : references.filter(ref => ref.selectorType === 'face').map(ref => ref.id), lines: {}, partLines: {},
  } : null), [state.geometryLinks, state.source, references, parts]);
  const parameterNodes = useMemo(() => (state.parameters || []).map(parameter => sourceParameterNode(parameter, state.features || EMPTY)), [state]);
  const roots = useMemo(() => [{ id: 'model', label: label || 'Model', type: 'model', parameters: [], children: [
    ...(parameterNodes.length ? [{ id: 'parameters', label: 'Parameters', type: 'parameters', parameters: state.parameters, children: parameterNodes }] : []),
    ...(state.features?.length ? groupDesignFeatures(state.features, resolvedLinks, parts) : [{ id: 'imported', label: 'Imported geometry', type: 'imported', parameters: [], children: parts.map(part => ({ id: `part:${part.id}`, label: part.name || 'Part', type: 'part', partIds: [part.id], parameters: [], children: [] })) }]),
  ] }], [state, label, parameterNodes, resolvedLinks, parts]);
  const allNodes = useMemo(() => {
    const result = new Map();
    const visit = nodes => nodes.forEach(node => { result.set(node.id, node); visit(node.children || []); });
    visit(roots); return result;
  }, [roots]);
  // Geometry can arrive after the outline. Keep a selected operation visible
  // when verified links move it under its owning part.
  useEffect(() => {
    const parents = new Map();
    allNodes.forEach(node => (node.children || []).forEach(child => parents.set(child.id, node.id)));
    const ancestors = [];
    for (let id = parents.get(selectedId); id; id = parents.get(id)) ancestors.push(id);
    setExpanded(current => ancestors.every(id => current.has(id)) ? current : new Set([...current, ...ancestors]));
  }, [allNodes, selectedId]);
  const selected = allNodes.get(selectedId) || roots[0];
  const parent = [...allNodes.values()].find(node => node.children?.some(child => child.id === selected.id));
  const geometrySelection = useMemo(() => designFeatureSelection(selected, resolvedLinks, parent?.line), [selected, resolvedLinks, parent?.line]);
  const measurements = useMemo(() => designFeatureMeasurements(geometrySelection, references, parts), [geometrySelection, references, parts]);
  useEffect(() => {
    if (state.geometryLinks?.faces?.length) onLoadTopology?.();
  }, [state.geometryLinks, onLoadTopology]);
  useEffect(() => {
    onHighlight?.(selectionRequest ? geometrySelection : null);
    return () => onHighlight?.(null);
  }, [geometrySelection, selectionRequest, onHighlight]);
  const rows = flatten(roots, expanded);
  const runPartAction = (event, action, id) => {
    event.stopPropagation();
    setSelectionRequest(0);
    onHighlight?.(null);
    action?.(id);
  };
  const toggle = id => setExpanded(current => { const next = new Set(current); if (next.has(id)) next.delete(id); else next.add(id); return next; });

  return <div className="flex h-full min-h-0 flex-col" aria-label="Design features" onKeyDown={event => {
    if (event.key === 'Escape') { event.stopPropagation(); setSelectionRequest(0); setSelectedParameter(null); onHighlight?.(null); }
  }}>
    <div className="flex shrink-0 items-center justify-between gap-2 border-b border-sidebar-border/60 px-3 py-2 text-micro text-muted-foreground">
      <span>{state.source ? 'Source operations' : 'Model features'}</span>
      <div className="flex items-center gap-2"><span>Read-only</span><button type="button" aria-label="Refresh source features" title="Refresh source features" disabled={state.status === 'loading'} className="grid size-6 place-items-center rounded hover:bg-sidebar-accent disabled:opacity-40" onClick={() => setAttempt(value => value + 1)}><RotateCw className="size-3" aria-hidden="true" /></button></div>
    </div>
    {partActions?.focusedIds?.length > 0 && <div className="flex shrink-0 items-center justify-between border-b border-sidebar-border/60 px-3 py-1 text-micro text-muted-foreground">
      <span>Isolated view</span><button type="button" disabled={partActions.disabled} onClick={event => runPartAction(event, partActions.onExitAllIsolate)} className="flex items-center gap-1 rounded px-1.5 py-1 hover:bg-sidebar-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"><X className="size-3" aria-hidden="true" />Exit isolate</button>
    </div>}
    {state.status === 'loading' ? <p role="status" className="p-3 text-xs text-muted-foreground">Reading source…</p> : null}
    {state.status === 'error' ? <div role="alert" className="p-3 text-xs text-muted-foreground"><p>{state.error || 'Could not read source features.'}</p><button className="mt-2 underline" onClick={() => setAttempt(value => value + 1)}>Retry</button></div> : null}
    <ScrollArea className="min-h-0 flex-1">
      <div role="tree" aria-label="Features" className="p-1.5">
        {state.status !== 'loading' && rows.map((node, index) => {
          const Icon = iconFor(node.type), hasChildren = Boolean(node.children?.length), open = expanded.has(node.id);
          const partId = node.type === 'part' ? node.partIds[0] : null;
          const hidden = partId && partActions?.hiddenIds?.includes(partId);
          const isolated = partId && partActions?.focusedIds?.includes(partId);
          const selectable = !Array.isArray(partActions?.selectableIds) || partActions.selectableIds.includes(partId);
          const actionClasses = cn('grid size-7 shrink-0 place-items-center rounded-sm text-current/60 hover:bg-sidebar-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-35', selected.id !== node.id && !hidden && !isolated && 'opacity-0 group-hover/feature-row:opacity-100 group-focus-within/feature-row:opacity-100');
          return <div key={node.id} role="treeitem" aria-level={node.depth + 1} aria-expanded={hasChildren ? open : undefined} aria-selected={selected.id === node.id}
            tabIndex={selected.id === node.id ? 0 : -1} title={node.label} aria-label={node.type === 'parameter' ? `${title(node.label)}: ${number(node.parameters[0].value)}` : undefined}
            className={cn('group/feature-row flex h-8 min-w-0 cursor-default items-center gap-1 rounded-md pr-2 text-xs outline-none hover:bg-sidebar-accent/50 focus-visible:ring-2 focus-visible:ring-sidebar-ring', selected.id === node.id && 'bg-sidebar-accent text-sidebar-accent-foreground')}
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
            <Icon className="mr-1 size-3.5 shrink-0 text-current/60" aria-hidden="true" /><span className={cn('min-w-0 flex-1 truncate', hidden && 'opacity-50')}>{title(node.label)}</span>{node.type === 'parameter' && <span className="shrink-0 text-muted-foreground tabular-nums">{number(node.parameters[0].value)}</span>}
            {partId && partActions && <>
              {!isolated && <button type="button" className={actionClasses} aria-label={`Isolate ${title(node.label)}`} title="Isolate" disabled={partActions.disabled || !selectable || !partActions.onIsolate} onClick={event => runPartAction(event, partActions.onIsolate, partId)}><Focus className="size-3.5" aria-hidden="true" /></button>}
              <button type="button" className={actionClasses} aria-label={isolated ? `Exit isolate for ${title(node.label)}` : `${hidden ? 'Show' : 'Hide'} ${title(node.label)}`} title={isolated ? 'Exit isolate' : hidden ? 'Show' : 'Hide'} disabled={partActions.disabled || !(isolated ? partActions.onExitIsolate : partActions.onToggleVisibility)} onClick={event => runPartAction(event, isolated ? partActions.onExitIsolate : partActions.onToggleVisibility, partId)}>
                {isolated ? <X className="size-3.5" aria-hidden="true" /> : hidden ? <EyeOff className="size-3.5" aria-hidden="true" /> : <Eye className="size-3.5" aria-hidden="true" />}
              </button>
            </>}
          </div>;
        })}
      </div>
    </ScrollArea>
    {selected.type !== 'model' && <section aria-label="Feature properties" className="max-h-[32%] shrink-0 overflow-y-auto border-t border-sidebar-border/70 px-3 py-2.5">
      <h3 className="mb-2 text-xs">{title(selected.label)}</h3>
      {(measurements.size || measurements.area !== null || measurements.radii.length > 0) && <div className="mb-3" aria-label="Associated geometry measurements">
        <h4 className="mb-1.5 text-micro text-muted-foreground">Associated geometry</h4>
        <dl className="space-y-1.5 text-xs">
          {measurements.size && <div><dt className="text-muted-foreground" title="Bounding size along the model’s X, Y and Z axes">Overall size · X × Y × Z</dt><dd className="mt-0.5 tabular-nums">{measurements.size.map(measurement).join(' × ')} mm</dd></div>}
          {measurements.area !== null && <div className="flex justify-between gap-2"><dt className="text-muted-foreground">Face area</dt><dd className="tabular-nums">{measurement(measurements.area)} mm²</dd></div>}
          {measurements.radii.length > 0 && <div><dt className="text-muted-foreground" title="Radii of linked cylindrical or spherical faces">Surface {measurements.radii.length === 1 ? 'radius' : 'radii'}</dt><dd className="mt-0.5 tabular-nums">{measurements.radii.slice(0, 6).map(measurement).join(', ')}{measurements.radii.length > 6 ? '…' : ''} mm</dd></div>}
        </dl>
      </div>}
      {selected.parameters?.length ? <div className="space-y-1 text-xs"><h4 className="mb-1 text-micro text-muted-foreground">Source parameters</h4>{selected.parameters.map((param, i) => <button key={`${param.name}:${i}`} type="button"
        aria-label={`Highlight ${title(param.name)}`} aria-pressed={selected.type === 'parameter' ? selectionRequest > 0 : selectedParameter === i}
        title={param.expression} className={cn('flex w-full items-baseline justify-between gap-3 rounded px-1.5 py-1.5 text-left hover:bg-sidebar-accent/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sidebar-ring', selectedParameter === i && 'bg-sidebar-accent text-sidebar-accent-foreground')}
        onClick={() => {
          if (selected.type === 'parameters') {
            setExpanded(current => new Set([...current, 'parameters']));
            selectRow(parameterNodes[i].id);
          } else { setSelectedParameter(i); setSelectionRequest(value => value + 1); }
        }}>
        <span className="min-w-0 break-words text-muted-foreground">{title(param.name)}</span><span className="min-w-0 break-words text-right tabular-nums">{param.value == null ? param.expression : number(param.value)}</span>
      </button>)}</div> : <p className="text-xs text-muted-foreground">{selected.type === 'imported' ? 'This STEP contains geometry, not an authored feature history.' : selected.type === 'part' ? selected.children.length ? `${selected.children.length} source operations` : 'No individual source operations linked.' : selected.type === 'group' ? `${selected.children.length} items` : 'No static parameter values available.'}</p>}
      {(selected.line || selected.type === 'parameter' || selected.type === 'part') && <p className="mt-3 text-micro text-muted-foreground">{geometrySelection?.partIds.length ? `${geometrySelection.partIds.length} associated ${geometrySelection.partIds.length === 1 ? "part" : "parts"}` : geometrySelection?.faceIds.length ? `${geometrySelection.faceIds.length} associated ${geometrySelection.faceIds.length === 1 ? "face" : "faces"}` : state.geometryLinks ? 'No matching geometry available' : 'Rebuild this model to link its geometry'}</p>}
    </section>}
    {onAddToPrompt && selected.type !== 'model' && selected.type !== 'parameters' && <div className="shrink-0 border-t border-sidebar-border/60 px-3 py-2">
      <Button type="button" variant="outline" size="sm" className="h-7 w-full gap-1.5 text-xs"
        disabled={!geometrySelection.faceIds.length && !geometrySelection.partIds.length}
        title={geometrySelection.faceIds.length || geometrySelection.partIds.length ? 'Add this feature’s linked geometry to the prompt' : 'No linked geometry available to add'}
        onClick={() => onAddToPrompt(geometrySelection, title(selected.label))}>
        <Plus className="size-3.5" aria-hidden="true" />Add to prompt
      </Button>
    </div>}
    <div className="shrink-0 border-t border-sidebar-border/60 px-3 py-2 text-micro text-muted-foreground">
      {state.source ? <><button className="max-w-full truncate text-left underline-offset-2 hover:underline" title={state.source} onClick={() => onOpenFile?.(state.source)}>{state.source.split('/').pop()}</button></> : <p>{state.status === 'ambiguous' ? 'Multiple source candidates. No feature history was assumed.' : state.status === 'loading' ? 'Reading matching source without running it.' : 'No source feature history available.'}</p>}
    </div>
  </div>;
}
