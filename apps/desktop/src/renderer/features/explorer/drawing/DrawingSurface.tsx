import { MAX_DRAWING_BYTES, parseDrawingScene } from '@hardcore/core/drawing';
import { createPromptContext } from '@hardcore/core/prompt';
import { DrawingEditor } from '@hardcore/ui/drawing';
import type { DrawingController } from '@hardcore/ui/drawing';
import { Download, ImagePlus, Upload } from 'lucide-react';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { toast } from 'sonner';
import { Button } from '@renderer/components/ui/button';
import { useResolvedTheme } from '@renderer/hooks/use-theme';
import { getDrawingScene, retainDrawingScene, setDrawingScene } from '@renderer/state/drawings';
import { useExplorer } from '@renderer/state/explorer';
import type { DrawingTabProps } from '../DrawingTab';
import { createDesktopPromptContext } from '../host/promptContext';

const errorMessage = (error: unknown) => error instanceof Error ? error.message : String(error);
export default function DrawingSurface({ tabId, project, root, title }: DrawingTabProps) {
  const theme = useResolvedTheme();
  const [initialScene] = useState(() => getDrawingScene(tabId));
  const controller = useRef<DrawingController | null>(null);
  const release = useRef<(() => void) | null>(null);
  const input = useRef<HTMLInputElement>(null);
  const [hasContent, setHasContent] = useState(false);
  const [adding, setAdding] = useState(false);
  const prompt = useMemo(() => createDesktopPromptContext(project.id, root, JSON.stringify(['desktop', project.id, root])), [project.id, root]);
  const ready = useCallback((next: DrawingController | null) => {
    release.current?.();
    release.current = null;
    controller.current = next;
    if (next) release.current = retainDrawingScene(tabId, () => next.serialize());
  }, [tabId]);
  useEffect(() => () => { release.current?.(); release.current = null; }, []);

  const addToPrompt = () => {
    const drawing = controller.current;
    if (!drawing || adding) return;
    setAdding(true);
    try {
      // Start encoding, then synchronously bind delivery to the current draft.
      // The context identifies the live editable tab so the agent can save it.
      const context = createPromptContext([
        { id: 'drawing-description', kind: 'text', text: `Drawing: ${title} (temporary drawing tab ${tabId}).` },
        { id: 'drawing-image', kind: 'attachment', name: `${title.replace(/[^\p{L}\p{N}._-]/gu, '_') || 'Drawing'}.png`,
          mimeType: 'image/png', content: drawing.exportPng() },
      ]);
      void prompt.deliver(context).then(result => {
        if (result.status === 'added') toast.success('Drawing added to prompt');
        else if (result.status === 'failed' || result.status === 'cancelled') toast.error(result.message ?? 'Could not add drawing.');
      }).catch(error => toast.error(errorMessage(error))).finally(() => setAdding(false));
    } catch (error) { setAdding(false); toast.error(errorMessage(error)); }
  };
  const saveCopy = async () => {
    if (!controller.current) return;
    try {
      const scene = JSON.stringify(parseDrawingScene(controller.current.serialize()));
      const saved = await window.hardcore.dialogs.saveDrawing({ projectId: project.id, ...(root ? { root } : {}), title, scene });
      if (saved) toast.success('Drawing copy saved');
    } catch (error) { toast.error(errorMessage(error)); }
  };
  const importFile = async (file: File) => {
    try {
      if (file.size > MAX_DRAWING_BYTES) throw new Error('Drawing documents must be at most 20 MiB.');
      const scene = JSON.stringify(parseDrawingScene(await file.text()));
      // An import is a new temporary tab, leaving the current sketch intact.
      if (useExplorer.getState().projectId !== project.id) return;
      const next = useExplorer.getState().open('drawing', { root, title: file.name.replace(/\.excalidraw$/i, '').slice(0, 200) || 'Drawing' });
      if (next) setDrawingScene(next.id, scene);
    } catch (error) { toast.error(errorMessage(error)); }
  };
  return <section className="flex h-full min-h-0 flex-col" aria-label="Drawing" data-drawing-tab={tabId}>
    <header className="flex h-10 shrink-0 items-center gap-2 border-b px-3">
      <span className="min-w-0 truncate">{title}</span>
      <span className="text-[11px] text-muted-foreground" title="Discarded when this tab closes or the app restarts">Temporary</span>
      <div className="ml-auto flex shrink-0 items-center gap-1">
        <Button size="icon-xs" variant="ghost" aria-label="Open drawing file" title="Open drawing file" onClick={() => input.current?.click()}><Upload className="size-3.5" /></Button>
        <Button size="icon-xs" variant="ghost" aria-label="Save drawing copy" title="Save drawing copy" disabled={!hasContent} onClick={() => void saveCopy()}><Download className="size-3.5" /></Button>
        <Button size="sm" variant="secondary" className="h-7 gap-1.5" disabled={!hasContent || adding} onClick={addToPrompt}>
          <ImagePlus className="size-3.5" />{adding ? 'Adding…' : 'Add to prompt'}
        </Button>
      </div>
      <input className="hidden" ref={input} type="file" accept=".excalidraw,application/json" aria-label="Drawing file"
        onChange={event => { const file = event.target.files?.[0]; event.target.value = ''; if (file) void importFile(file); }} />
    </header>
    <div className="min-h-0 flex-1"><DrawingEditor initialScene={initialScene} theme={theme} name={title}
      onReady={ready} onContentChange={setHasContent} onSaveCopy={() => void saveCopy()} onOpenFile={() => input.current?.click()}
      onImportFile={file => void importFile(file)} /></div>
  </section>;
}
