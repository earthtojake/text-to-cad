import { cn } from '@hardcore/ui/utils';
import { designFeatureLabel as featureLabel, designFeatureTitle as title, designFeatureValue as number } from '../../workbench/designFeatureTree.js';

const measurement = value => value.toLocaleString(undefined, { maximumFractionDigits: 2 });

/** Read-only operation inputs and measured result geometry for the selected row. */
export default function StepDesignProperties({ selected, selectedParameter, selectionRequest, measurements, inspection, geometrySelection, onSelectParameter, onInspectParameter, inspect }) {
  if (selected.type === 'model') return null;
  return <section aria-label="Feature properties" className="max-h-[32%] min-w-0 shrink-0 overflow-x-hidden overflow-y-auto border-t border-sidebar-border/70 px-3 py-2.5">
      <h3 className="mb-2 text-xs [overflow-wrap:anywhere]">{featureLabel(selected)}</h3>
      {selected.parameters?.length ? <div className="mb-3 space-y-1 text-xs"><h4 className="mb-1 text-micro text-muted-foreground">{selected.type === 'sketch' ? 'Sketch inputs' : ['parameter', 'parameters'].includes(selected.type) ? 'Parameters' : 'Operation inputs'}</h4>{selected.parameters.map((param, i) => <button key={`${param.name}:${i}`} type="button"
        aria-label={`Highlight ${title(param.name)}`} aria-pressed={selected.type === 'parameter' ? selectionRequest > 0 : selectedParameter === i}
        title={param.expression} className={cn('flex w-full min-w-0 flex-wrap items-baseline justify-between gap-x-3 gap-y-1 rounded px-1.5 py-1.5 text-left hover:bg-sidebar-accent/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sidebar-ring', selectedParameter === i && 'bg-sidebar-accent text-sidebar-accent-foreground')}
        onClick={() => {
          if (selected.type === 'parameters') {
            onSelectParameter(i);
          } else { onInspectParameter(i); }
        }}>
        <span className="max-w-full shrink-0 text-muted-foreground [overflow-wrap:anywhere]">{title(param.name)}</span><span className={cn("min-w-0 max-w-full tabular-nums [overflow-wrap:anywhere]", typeof param.value === "number" ? "ml-auto text-right" : "basis-full text-left")}>{param.value == null ? param.expression : number(param.value)}</span>
      </button>)}</div> : !selected.type.startsWith('geometry-') && <p className="text-xs text-muted-foreground">{selected.type === 'imported' ? 'This STEP contains geometry, not an authored feature history.' : selected.type === 'part' ? selected.children.filter(child => !child.type.startsWith('geometry-')).length ? `${selected.children.filter(child => !child.type.startsWith('geometry-')).length} source operations` : 'No individual source operations linked.' : selected.type === 'group' ? `${selected.children.length} items` : 'No static parameter values available.'}</p>}
      {(measurements.size || measurements.area !== null || measurements.radii.length > 0) && <div className="mb-3" aria-label="Associated geometry measurements">
        <h4 className="mb-1.5 text-micro text-muted-foreground">{selected.type.startsWith('geometry-') ? 'Face measurements' : 'Result geometry'}</h4>
        <dl className="space-y-1.5 text-xs">
          {measurements.size && <div><dt className="text-muted-foreground" title="Bounding size along the model’s X, Y and Z axes">Overall size · X × Y × Z</dt><dd className="mt-0.5 tabular-nums">{measurements.size.map(measurement).join(' × ')} mm</dd></div>}
          {measurements.size && <div className="flex flex-wrap gap-1" aria-label="Preview bounding dimensions">{['X', 'Y', 'Z'].map((axis, i) => <button key={axis} type="button"
            aria-label={`Show ${axis} extent`} aria-pressed={inspection?.kind === 'axis' && inspection.value === i}
            disabled={measurements.size[i] < 1e-6} title={`Show the measured ${axis} bounding extent`}
            className={cn('rounded border border-sidebar-border/60 px-2 py-1 tabular-nums hover:bg-sidebar-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-40', inspection?.kind === 'axis' && inspection.value === i && 'bg-sidebar-accent')}
            onClick={() => inspect('axis', i)}>{axis} · {measurement(measurements.size[i])} mm</button>)}</div>}
          {measurements.area !== null && <div className="flex flex-wrap justify-between gap-x-2 gap-y-1"><dt className="shrink-0 text-muted-foreground">Face area</dt><dd className="max-w-full tabular-nums [overflow-wrap:anywhere]">{measurement(measurements.area)} mm²</dd></div>}
          {measurements.radii.length > 0 && <div><dt className="text-muted-foreground" title="Radii of linked cylindrical or spherical faces">Surface {measurements.radii.length === 1 ? 'radius' : 'radii'}</dt><dd className="mt-1 flex flex-wrap gap-1 tabular-nums">{measurements.radii.map(radius => <button key={radius} type="button" aria-label={`Highlight faces with radius ${measurement(radius)} mm`} aria-pressed={inspection?.kind === 'radius' && inspection.value === radius}
            className={cn('rounded border border-sidebar-border/60 px-2 py-1 hover:bg-sidebar-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring', inspection?.kind === 'radius' && inspection.value === radius && 'bg-sidebar-accent')}
            onClick={() => inspect('radius', radius)}>{measurement(radius)} mm</button>)}</dd></div>}
        </dl>
      </div>}

      {(geometrySelection.partIds.length > 0 || geometrySelection.faceIds.length > 0) && <p className="mt-3 text-micro text-muted-foreground">{geometrySelection.partIds.length ? `${geometrySelection.partIds.length} associated ${geometrySelection.partIds.length === 1 ? 'part' : 'parts'}` : `${geometrySelection.faceIds.length} associated ${geometrySelection.faceIds.length === 1 ? 'face' : 'faces'}`}</p>}
    </section>;
}
