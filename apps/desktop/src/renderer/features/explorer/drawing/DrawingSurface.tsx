import { createPromptContext } from '@hardcore/core/prompt';
import { DrawingEditor } from '@hardcore/ui/drawing';
import type { DrawingController } from '@hardcore/ui/drawing';
import { ImagePlus } from 'lucide-react';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { toast } from 'sonner';
import { Button } from '@renderer/components/ui/button';
import { getDrawingScene, retainDrawingScene } from '@renderer/state/drawings';
import { renameDrawingTab } from '@renderer/state/explorer';
import type { DrawingTabProps } from '../DrawingTab';
import { createDesktopPromptContext } from '../host/promptContext';

const errorMessage = (error: unknown) => error instanceof Error ? error.message : String(error);
export default function DrawingSurface({ tabId, project, root, title }: DrawingTabProps) {
  const [initialScene] = useState(() => getDrawingScene(tabId));
  const controller = useRef<DrawingController | null>(null);
  const release = useRef<(() => void) | null>(null);
  const [hasContent, setHasContent] = useState(false);
  const [adding, setAdding] = useState(false);
  const [nameEdit, setNameEdit] = useState({ source: title, value: title });
  const draftName = nameEdit.source === title ? nameEdit.value : title;
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
      // The sketch is visual context for the prompt.
      const context = createPromptContext([
        { id: 'drawing-description', kind: 'text', text: `Drawing: ${title}.` },
        { id: 'drawing-image', kind: 'attachment', name: `${title.replace(/[^\p{L}\p{N}._-]/gu, '_') || 'Drawing'}.png`,
          mimeType: 'image/png', content: drawing.exportPng() },
      ]);
      void prompt.deliver(context).then(result => {
        if (result.status === 'added') toast.success('Drawing added to prompt');
        else if (result.status === 'failed' || result.status === 'cancelled') toast.error(result.message ?? 'Could not add drawing.');
      }).catch(error => toast.error(errorMessage(error))).finally(() => setAdding(false));
    } catch (error) { setAdding(false); toast.error(errorMessage(error)); }
  };
  return <section className="flex h-full min-h-0 flex-col" aria-label="Drawing" data-drawing-tab={tabId}>
    <header className="flex h-10 shrink-0 items-center gap-2 border-b px-3">
      <input aria-label="Drawing name" className="min-w-0 flex-1 rounded bg-transparent px-1 py-0.5 text-ui outline-none hover:bg-muted focus:bg-muted focus:ring-1 focus:ring-ring"
        value={draftName} maxLength={200} onChange={event => setNameEdit({ source: title, value: event.target.value })}
        onBlur={() => {
          const name = draftName.trim() || title;
          setNameEdit({ source: name, value: name });
          try { renameDrawingTab(tabId, project.id, name); }
          catch (error) { toast.error(errorMessage(error)); }
        }} onKeyDown={event => {
          if (event.key === 'Enter') event.currentTarget.blur();
          if (event.key === 'Escape') { setNameEdit({ source: title, value: title }); event.stopPropagation(); }
        }} />
      <div className="ml-auto flex shrink-0 items-center gap-1">
        <Button size="sm" variant="secondary" className="h-7 gap-1.5" disabled={!hasContent || adding} onClick={addToPrompt}>
          <ImagePlus className="size-3.5" />{adding ? 'Adding…' : 'Add to prompt'}
        </Button>
      </div>
    </header>
    <div className="min-h-0 flex-1"><DrawingEditor initialScene={initialScene} name={title}
      onReady={ready} onContentChange={setHasContent} /></div>
  </section>;
}
