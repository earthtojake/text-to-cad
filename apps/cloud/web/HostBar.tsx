import { useEffect, useRef, useState } from 'react';
import { Check, Code2, Download, Link } from 'lucide-react';
import { Button } from '@text-to-cad/ui/primitives/button';
import { TooltipHint } from '@text-to-cad/ui/primitives/tooltip';

/**
 * The page's own row above the viewer, outside it (the viewport's corners are the viewer's): the
 * build's title and id, its status, and what the page can do with the build — show its source
 * (Code), download the file on screen, and copy the file's link. The same tokens as the viewer's
 * chrome; no control appears that does nothing.
 */
export default function HostBar({ title, id, status, fileName, downloadUrl, address, codeOpen, onToggleCode, onCopyLink }: {
  title: string; id: string; status: string;
  /** The file on screen, or '' while none is. */
  fileName: string;
  /** Where the file on screen downloads from, or '' while none is. */
  downloadUrl: string;
  /** The file on screen's address (Copy link), or ''. */
  address: string;
  codeOpen: boolean;
  onToggleCode: () => void;
  onCopyLink: (address: string) => Promise<void>;
}) {
  const [copied, setCopied] = useState(false);
  const timer = useRef(0);
  useEffect(() => () => clearTimeout(timer.current), []);
  const copy = async () => {
    if (!address) return;
    await onCopyLink(address);
    setCopied(true);
    clearTimeout(timer.current);
    timer.current = window.setTimeout(() => setCopied(false), 1600);
  };
  return <div className="flex h-9 shrink-0 items-center gap-2 border-b border-border bg-background px-3 text-ui" data-cloud-host-bar="">
    <span className="min-w-0 truncate font-normal text-foreground" data-build-title="">{title || 'Build'}</span>
    <span className="shrink-0 font-mono text-tiny text-muted-foreground" data-build-id="">{id}</span>
    {status ? <span className="shrink-0 rounded-sm bg-muted px-1.5 py-0.5 text-tiny text-muted-foreground" data-build-status="">{status}</span> : null}
    <span className="min-w-0 flex-1" />
    <TooltipHint content={codeOpen ? 'Hide the build’s source' : 'Show the build’s source'}>
      <Button type="button" variant="ghost" size="xs" aria-label="Code" aria-pressed={codeOpen} className="text-muted-foreground aria-pressed:bg-accent aria-pressed:text-accent-foreground" onClick={onToggleCode}>
        <Code2 aria-hidden="true" />Code
      </Button>
    </TooltipHint>
    {downloadUrl ? <TooltipHint content={`Download ${fileName}`}>
      <Button variant="ghost" size="xs" className="text-muted-foreground" asChild>
        <a href={downloadUrl} download={fileName} target="_blank" rel="noopener" aria-label={`Download ${fileName}`}><Download aria-hidden="true" />Download</a>
      </Button>
    </TooltipHint> : null}
    {address ? <TooltipHint content="Copy this file’s link">
      <Button type="button" variant="ghost" size="xs" aria-label="Copy link" className="text-muted-foreground" onClick={() => { void copy(); }}>
        {copied ? <Check aria-hidden="true" /> : <Link aria-hidden="true" />}{copied ? 'Copied' : 'Copy link'}
      </Button>
    </TooltipHint> : null}
  </div>;
}
