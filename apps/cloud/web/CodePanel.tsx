import { useEffect, useState } from 'react';
import { FileCode2 } from 'lucide-react';
import { fetchBuildFile, fetchBuildFiles, type BuildFile } from './host/buildApi.ts';

const TEXT_KINDS = new Set(['other', 'urdf', 'srdf', 'sdf']);

/**
 * The build's source, beside the viewer: every file the build was made from and wrote, and the
 * text of the one picked. Read from the server's build API; a server without it says so.
 */
export default function CodePanel({ id }: { id: string }) {
  const [files, setFiles] = useState<BuildFile[] | null | undefined>(undefined);
  const [picked, setPicked] = useState('');
  const [content, setContent] = useState<{ path: string; text: string | null } | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    fetchBuildFiles(id, controller.signal).then(found => {
      if (controller.signal.aborted) return;
      setFiles(found);
      // The model's source first (what the build was made from), then any other text.
      const first = found?.find(file => file.kind === 'other' && /\.py$/i.test(file.path)) ?? found?.find(file => TEXT_KINDS.has(file.kind) && /\.(?:py|txt|md|json|urdf|srdf|sdf|xml|toml|yaml|yml)$/i.test(file.path)) ?? found?.find(file => TEXT_KINDS.has(file.kind));
      if (first) setPicked(first.path);
    }).catch(() => { if (!controller.signal.aborted) setFiles(null); });
    return () => controller.abort();
  }, [id]);
  useEffect(() => {
    if (!picked) return undefined;
    const controller = new AbortController();
    setContent(null);
    fetchBuildFile(id, picked, controller.signal).then(text => { if (!controller.signal.aborted) setContent({ path: picked, text }); })
      .catch(() => { if (!controller.signal.aborted) setContent({ path: picked, text: null }); });
    return () => controller.abort();
  }, [id, picked]);
  return <aside className="flex h-full w-80 shrink-0 flex-col border-l border-border bg-background text-ui" data-cloud-code="">
    <div className="flex h-8 shrink-0 items-center gap-1.5 border-b border-border px-3 text-tiny text-muted-foreground"><FileCode2 className="size-3.5" aria-hidden="true" />Source</div>
    {files === undefined ? <div className="px-3 py-2 text-tiny text-muted-foreground">Reading the build’s files…</div>
      : files === null ? <div className="px-3 py-2 text-tiny text-muted-foreground">This build’s source files are not available here.</div>
      : <>
        <ul className="max-h-48 shrink-0 overflow-auto border-b border-border py-1" role="listbox" aria-label="Build files">
          {files.map(file => <li key={file.path}>
            <button type="button" role="option" aria-selected={file.path === picked} disabled={!TEXT_KINDS.has(file.kind)}
              className="w-full truncate px-3 py-0.5 text-left text-tiny text-foreground hover:bg-accent disabled:text-muted-foreground disabled:hover:bg-transparent aria-selected:bg-accent aria-selected:text-accent-foreground"
              onClick={() => setPicked(file.path)}>{file.path}</button>
          </li>)}
        </ul>
        <div className="min-h-0 flex-1 overflow-auto">
          {picked && content?.path === picked ? content.text === null
            ? <div className="px-3 py-2 text-tiny text-muted-foreground">This file cannot be shown.</div>
            : <pre className="m-0 whitespace-pre px-3 py-2 font-mono text-[11px] leading-4 text-foreground" data-cloud-source="">{content.text}</pre>
            : picked ? <div className="px-3 py-2 text-tiny text-muted-foreground">Reading {picked}…</div> : null}
        </div>
      </>}
  </aside>;
}
