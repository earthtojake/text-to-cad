import { cn } from '@hardcore/ui/utils';

const measurement = value => value.toLocaleString(undefined, { maximumFractionDigits: 2 });

/** Measured properties of the selected STEP geometry. */
export default function StepGeometryProperties({ measurements, inspection, inspect }) {
  return <div className="min-w-0 px-1 text-xs">
      {(measurements.size || measurements.area !== null || measurements.radii.length > 0) && <div className="mb-3" aria-label="Associated geometry measurements">
        <h4 className="mb-1.5 text-micro text-muted-foreground">Measurements</h4>
        <dl className="space-y-1.5 text-xs">
          {measurements.size && <div className="flex flex-wrap gap-1" aria-label="Preview bounding dimensions" title="Bounding size along the model’s X, Y and Z axes">{['X', 'Y', 'Z'].map((axis, i) => <button key={axis} type="button"
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

    </div>;
}
