import { useEffect, useRef, useState } from 'react';
import { Check, Layers, Pause, Play, RotateCw, SkipBack, SkipForward, SquareDashed } from 'lucide-react';
import { Dialog, DialogContent, DialogDescription, DialogTitle } from '@hardcore/ui/primitives/dialog';
import { Button } from '@hardcore/ui/primitives/button';
import { cn } from '@hardcore/ui/utils';
import ReconstructionViewport from './ReconstructionViewport.jsx';
import ReconstructionExport from './ReconstructionExport.jsx';
import { requestReconstruction } from '../../workbench/reconstructionClient.js';
import { loadAssemblyPlayback } from '../../workbench/reconstructionAssembly.js';

function Playback({ data, label }) {
  const viewRef = useRef(null);
  const [frame, setFrame] = useState(data.steps.length - 1), [playing, setPlaying] = useState(false), [original, setOriginal] = useState(false);
  const selectedRow = useRef(null), last = data.steps.length - 1, step = data.steps[frame];
  const choose = index => { setPlaying(false); setOriginal(false); setFrame(index); };
  useEffect(() => {
    if (!playing) return;
    if (frame === last) { setPlaying(false); return; }
    const timer = setTimeout(() => setFrame(n => n + 1), 1000);
    return () => clearTimeout(timer);
  }, [playing, frame, last]);
  useEffect(() => { selectedRow.current?.scrollIntoView({ block: 'nearest' }); }, [frame]);
  useEffect(() => {
    const pause = () => { if (document.hidden) setPlaying(false); };
    document.addEventListener('visibilitychange', pause);
    return () => document.removeEventListener('visibilitychange', pause);
  }, []);
  return <>
    <div className="flex min-h-0 flex-1 flex-col overflow-hidden sm:flex-row">
      <div className="relative min-h-48 min-w-0 flex-1 bg-muted/20">
        <ReconstructionViewport {...{ data, frame, original, viewRef }} />
        <div className="absolute left-3 top-3 flex rounded-md border bg-popover p-0.5 text-xs" aria-label="Compare geometry">
          {['Reconstruction', 'Original STEP'].map((label, i) => <button key={label} type="button" aria-pressed={original === !!i} onClick={() => { setOriginal(!!i); setPlaying(false); }} className={cn('rounded px-2 py-1.5', original === !!i && 'bg-accent')}>{label}</button>)}
        </div>
        <span className="absolute bottom-3 left-3 text-xs text-muted-foreground">{original ? 'Original STEP' : `${frame + 1} / ${data.steps.length} · ${step.label}`}</span>
      </div>
      <div className="flex min-h-0 flex-col border-t sm:w-64 sm:shrink-0 sm:border-l sm:border-t-0">
        <div className="space-y-1 border-b px-3 py-2 text-xs"><div className="flex items-center gap-1.5"><Check className="size-3.5 shrink-0" />{data.tracks ? `${data.verified} components with verified playback` : 'Final geometry matches'}</div>{data.tracks && <p className="text-micro text-muted-foreground">{data.staticParts > 0 ? `${data.staticParts} ${data.staticParts === 1 ? "component stays" : "components stay"} as finished geometry. ` : ''}Other parts appear faintly while each sequence plays.</p>}</div>
        <ol className="min-h-0 flex-1 overflow-auto p-1" aria-label="Verified build sequence">
          {data.steps.map((item, i) => {
            const Icon = item.kind === 'sketch' ? SquareDashed : item.kind === 'revolve' ? RotateCw : Layers;
            return <li key={item.id} ref={i === frame ? selectedRow : null}><button type="button" aria-current={i === frame ? 'step' : undefined} onClick={() => choose(i)} className={cn('flex w-full items-center gap-2 rounded px-2 py-2 text-left text-xs hover:bg-accent/50', i === frame && 'bg-accent')}><span className="w-4 text-micro text-muted-foreground">{i + 1}</span><Icon className="size-3.5 shrink-0" />{item.label}</button></li>;
          })}
        </ol>
        <div className="max-h-40 space-y-2 overflow-auto border-t p-3 text-xs">
          <p>{step.label}</p>
          {!!step.dependsOn.length && <div className="flex flex-wrap gap-1"><span className="text-muted-foreground">Inputs</span>{step.dependsOn.map(id => { const i = data.steps.findIndex(s => s.id === id); return <button key={id} className="rounded border px-1.5 py-0.5 hover:bg-accent" onClick={() => choose(i)}>{data.steps[i].label}</button>; })}</div>}
          {step.measurements.map(([label, value, unit]) => <div className="flex justify-between gap-2" key={label}><span className="text-muted-foreground">{label}</span><span>{value.toLocaleString(undefined, { maximumFractionDigits: 3 })} {unit}</span></div>)}
        </div>
      </div>
    </div>
    <div className="flex flex-wrap items-center gap-2 border-t px-3 py-2">
      <Button size="icon" variant="ghost" aria-label="Previous step" disabled={frame === 0} onClick={() => choose(frame - 1)}><SkipBack className="size-4" /></Button>
      <Button size="sm" variant="outline" onClick={() => { setOriginal(false); if (frame === last) setFrame(0); setPlaying(value => !value); }}>{playing ? <Pause className="size-4" /> : <Play className="size-4" />}{playing ? 'Pause' : frame === last ? 'Replay' : 'Play'}</Button>
      <Button size="icon" variant="ghost" aria-label="Next step" disabled={frame === last} onClick={() => choose(frame + 1)}><SkipForward className="size-4" /></Button>
      <input className="min-w-0 flex-1 accent-current" type="range" aria-label="Build step" min={0} max={last} value={frame} onChange={e => choose(Number(e.target.value))} />
      <ReconstructionExport {...{ data, label, viewRef }} onStart={() => setPlaying(false)} />
    </div>
  </>;
}

export default function ReconstructionPreview({ target, file, component, recipe, assembly, label, onClose }) {
  const [data, setData] = useState(null), [error, setError] = useState('');
  const [progress, setProgress] = useState('Rebuilding and verifying this part…');
  useEffect(() => {
    const controller = new AbortController();
    const request = assembly
      ? loadAssemblyPlayback({ ...assembly, target, file, signal: controller.signal, onProgress: setProgress })
      : requestReconstruction({ target, file, component, recipe, signal: controller.signal });
    request
      .then(result => { if (!controller.signal.aborted) setData(result); })
      .catch(e => { if (!controller.signal.aborted) setError(e.message); });
    return () => controller.abort();
  }, [target, file, component, recipe, assembly]);
  return <Dialog open onOpenChange={open => { if (!open) onClose(); }}>
    <DialogContent className="flex h-[min(760px,90vh)] w-[min(1100px,94vw)] max-w-none flex-col gap-0 overflow-hidden p-0 sm:max-w-none">
      <div className="shrink-0 space-y-1 border-b px-4 py-3 pr-10"><DialogTitle className="text-sm">Build sequence · {label}</DialogTitle><DialogDescription className="text-xs">{assembly ? 'Verified part sequences in assembly order. Original build history and dependencies between parts are unknown.' : 'A new sequence reconstructed from STEP geometry—not the original build history.'}</DialogDescription></div>
      {data ? <Playback data={data} label={label} /> : <div className="grid flex-1 place-items-center p-6 text-center text-sm text-muted-foreground"><p role={error ? 'alert' : 'status'}>{error || progress}</p></div>}
    </DialogContent>
  </Dialog>;
}
