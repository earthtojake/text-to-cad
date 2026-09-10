import { useEffect, useRef, useState } from 'react';
import { Download, X } from 'lucide-react';
import { Button } from '@hardcore/ui/primitives/button';
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from '@hardcore/ui/primitives/dropdown-menu';
import { exportReconstruction, downloadExport, videoMimeType } from '../../workbench/reconstructionExport.js';

export default function ReconstructionExport({ data, label, viewRef, onStart }) {
  const running = useRef(null), [progress, setProgress] = useState(null), [error, setError] = useState('');
  useEffect(() => () => { running.current?.abort(); }, []);
  async function start(format) {
    if (running.current) return;
    const controller = new AbortController(); running.current = controller;
    onStart(); setError(''); setProgress({ format, done: 0, total: data.steps.length });
    try {
      const result = await exportReconstruction({ data, label, format, camera: viewRef.current?.camera.clone(), signal: controller.signal,
        onProgress: (done, total) => { if (!controller.signal.aborted) setProgress({ format, done, total }); } });
      if (!controller.signal.aborted) downloadExport(result);
    } catch (e) { if (!controller.signal.aborted) setError(e.message || 'Export failed. Try again.'); }
    finally { if (running.current === controller) { running.current = null; if (!controller.signal.aborted) setProgress(null); } }
  }
  const cancel = () => { running.current?.abort(); running.current = null; setProgress(null); };
  return <div className="flex max-w-full flex-wrap items-center justify-end gap-2">
    {error && <span role="alert" className="max-w-64 text-xs text-destructive">{error}</span>}
    {progress ? <><span role="status" className="text-xs tabular-nums text-muted-foreground">Exporting {progress.format === 'gif' ? 'GIF' : 'video'} · {progress.done}/{progress.total}</span><Button size="icon" variant="ghost" aria-label="Cancel export" onClick={cancel}><X className="size-4" /></Button></> :
      <DropdownMenu><DropdownMenuTrigger asChild><Button size="sm" variant="ghost"><Download className="size-4" />Export</Button></DropdownMenuTrigger><DropdownMenuContent align="end">
        <DropdownMenuItem onSelect={() => void start('gif')}>Animated GIF</DropdownMenuItem>
        <DropdownMenuItem disabled={!videoMimeType()} onSelect={() => void start('video')}>Video</DropdownMenuItem>
      </DropdownMenuContent></DropdownMenu>}
  </div>;
}
