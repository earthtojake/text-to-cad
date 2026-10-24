import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { ArrowDownToLine, X, Check, CircleAlert } from 'lucide-react';
import { ExportRequestError, exportPause, type ExportJob, type ExportOption, type ExportRequest, type ExportService, type ExportSource } from '@text-to-cad/core/client';
import type { DownloadPort, ExportRecord } from '../host/types.js';
import { Button } from '../primitives/button.jsx';
import { Spinner } from '../primitives/spinner.js';
import { Popover, PopoverContent, PopoverTrigger } from '../primitives/popover.jsx';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../primitives/select.jsx';
import { TooltipHint } from '../primitives/tooltip.jsx';
import { NAVBAR_CONTROL_CLASS } from '../lib/navbarRow.js';
import { useI18n } from '../i18n/index.js';
import { useViewerMobile } from '../file-viewer/responsive.js';
import { ExportContext, type ExportView } from './context.js';

const active = (job: ExportJob | null) => !job || ['queued', 'running', 'cancelling'].includes(job.state);
const message = (error: unknown) => error instanceof Error ? error.message : String(error);
const retryable = (error: unknown) => !(error instanceof ExportRequestError) || error.status >= 500;
// What the toast says is the job's state in the page's language; the server's stage is English.
const STATE_TEXT: Record<ExportJob['state'], string> = {
  queued: 'export.queued', running: 'export.running', cancelling: 'export.cancelling', cancelled: 'export.cancelled',
  failed: 'export.failed', expired: 'export.expired', ready: 'export.downloaded',
};

/** Each toast owns one job subscription and hands its file to the browser once; siblings never cancel each other. */
function ExportToast({ attempt, service, downloads, reveal, onDelivered, onRemove, onActivity, onExportAgain }: {
  attempt: ExportRecord; service: ExportService; downloads: DownloadPort; reveal: number;
  onDelivered(): void; onRemove(): void; onActivity(id: string, busy: boolean): void; onExportAgain(): void;
}) {
  const { t } = useI18n();
  // A phone's buttons are its 36px touch tiles (`docs/settings-ui.md`, Mobile); a desktop's the menu's.
  const mobile = useViewerMobile();
  const button = mobile ? { size: 'default' as const, className: 'px-3 text-tiny' } : { size: 'xs' as const, className: 'text-tiny' };
  const [job, setJob] = useState<ExportJob | null>(null);
  const [error, setError] = useState('');
  const [fatal, setFatal] = useState(false);
  const [connection, setConnection] = useState('');
  const [hidden, setHidden] = useState(false);
  const [now, setNow] = useState(Date.now());
  const cancelWanted = useRef(false);
  // A file is handed to the browser once by itself; again only when the person asks.
  const delivered = useRef(attempt.delivered);
  const latestJob = useRef(job); latestJob.current = job;
  const latest = useRef({ downloads, onDelivered }); latest.current = { downloads, onDelivered };
  useEffect(() => { setHidden(false); }, [reveal]);
  const expired = job?.state === 'expired' || (job?.state === 'ready' && now / 1000 >= job.expiresAt);
  useEffect(() => {
    if (job?.state === 'ready' && !expired) {
      const timer = setTimeout(() => setNow(Date.now()), Math.max(0, job.expiresAt * 1000 - Date.now()) + 50);
      return () => clearTimeout(timer);
    }
    if (!active(job) || fatal) return;
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [job, expired, fatal]);

  const deliver = useCallback((ready: ExportJob) => {
    delivered.current = true;
    // The server's name for the file: the one its Content-Disposition gives every browser.
    latest.current.downloads.save(service.fileUrl(ready.id), ready.filename || attempt.filename);
    latest.current.onDelivered();
  }, [service, attempt.filename]);

  useEffect(() => {
    const controller = new AbortController();
    const { signal } = controller;
    (async () => {
      let found: ExportJob | null = null;
      let failures = 0;
      for (;;) {
        try {
          found = found ? await service.status(found.id, found.sequence, signal) : await service.create(attempt.request, signal);
          if (signal.aborted) return;
          failures = 0; setConnection(''); setJob(found);
          if (cancelWanted.current && active(found) && found.state !== 'cancelling') {
            found = await service.cancel(found.id);
            if (signal.aborted) return;
            setJob(found);
          }
          if (!active(found)) {
            if (found.state !== 'ready') return;
            if (!delivered.current && !cancelWanted.current) deliver(found);
            // Ready, its status waits for the file to go: fetched whole by the browser, or past its
            // window (`cadgen/viewer/exports.py`). Then Download again becomes Export again.
          }
        } catch (failure) {
          if (signal.aborted) return;
          if (!retryable(failure)) { setError(message(failure)); setFatal(true); setConnection(''); return; }
          setConnection(t('export.reconnecting'));
          await exportPause(Math.min(1000 * 2 ** failures++, 10000), signal);
        }
      }
    })().catch(() => {});
    return () => controller.abort();
  }, [service, attempt.request, deliver, t]);

  const cancel = async () => {
    cancelWanted.current = true;
    setConnection(t('export.cancelRequested'));
    const found = latestJob.current;
    if (!found || !active(found)) return;
    try { setJob(await service.cancel(found.id)); setConnection(''); }
    catch (failure) { setError(t('export.cancelError', { message: message(failure) })); }
  };
  // In the press itself, so the browser counts it as the person's own download.
  const again = () => { if (job?.state === 'ready' && !expired) deliver(job); };
  const remove = async () => {
    if (job && !fatal) {
      try { await service.release(job.id); } catch (failure) {
        if (!(failure instanceof ExportRequestError && failure.status === 404)) { setError(message(failure)); return; }
      }
    }
    onRemove();
  };
  const busy = active(job) && !fatal;
  useEffect(() => { onActivity(attempt.request.requestId, busy); }, [onActivity, attempt.request.requestId, busy]);
  if (hidden) return null;
  const failure = error || job?.error;
  const title = !job ? (failure ? t('export.failed') : t('export.submitting'))
    : t(job.fetched ? 'export.fetched' : expired ? 'export.expired' : STATE_TEXT[job.state]);
  const seconds = Math.max(0, Math.floor(((job?.finishedAt || now / 1000) - (job?.createdAt || now / 1000))));
  const ready = job?.state === 'ready' && !expired;
  return <section className="rounded-lg border border-border bg-popover p-3 text-tiny text-popover-foreground shadow-lg" aria-label={t('export.toast', { name: job?.filename || attempt.filename })} data-export-toast="">
    <div className="flex items-start gap-2">
      {failure ? <CircleAlert className="mt-0.5 size-4 shrink-0 text-destructive" /> : busy ? <Spinner className="mt-0.5 size-4 shrink-0" />
        : ready ? <Check className="mt-0.5 size-4 shrink-0" /> : <ArrowDownToLine className="mt-0.5 size-4 shrink-0 text-muted-foreground" />}
      <div className="min-w-0 flex-1"><p className="truncate">{job?.filename || attempt.filename}</p><p className="mt-1 text-muted-foreground" role="status" aria-live="polite">{title}{busy ? ` · ${seconds}s` : ''}</p></div>
      <Button variant="ghost" size={mobile ? 'icon' : 'icon-xs'} aria-label={t('export.dismiss')} onClick={() => setHidden(true)}><X /></Button>
    </div>
    {connection ? <p className="mt-2">{connection}</p> : null}
    {failure ? <p className="mt-2 break-words text-destructive" role="alert">{failure}</p> : null}
    {ready ? <p className="mt-2 text-muted-foreground">{t('export.until', { time: new Date(job.expiresAt * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) })}</p> : null}
    <div className="mt-2 flex justify-end gap-2">
      {busy ? <Button {...button} variant="outline" disabled={job?.state === 'cancelling'} onClick={() => { void cancel(); }}>{t('export.cancel')}</Button> : null}
      {ready ? <Button {...button} onClick={again}>{t('export.again')}</Button> : null}
      {expired ? <Button {...button} onClick={onExportAgain}>{t('export.exportAgain')}</Button> : null}
      {!busy ? <Button {...button} variant="ghost" onClick={() => { void remove(); }}>{t('export.remove')}</Button> : null}
    </div>
  </section>;
}

/** Where the toasts stand: under the navbar at the view's top-right on a desktop; at a phone's
 * bottom, the view's width less its margins, where a thumb reaches them. Rendered inside the
 * viewer, so it reads the viewer's own width (`useViewerMobile`). */
function ToastStack({ label, children }: { label: string; children: ReactNode }) {
  const mobile = useViewerMobile();
  return <div className={`pointer-events-none absolute inset-x-2 z-40 flex max-h-[calc(100%-1rem)] flex-col overflow-y-auto ${mobile ? 'bottom-2 items-stretch' : 'top-2 items-end'}`}
    aria-label={label} data-export-stack={mobile ? 'bottom' : 'top'}>
    <div className={`pointer-events-auto flex max-w-full flex-col gap-2 ${mobile ? 'w-full' : 'w-80'}`}>{children}</div>
  </div>;
}

export function ExportControls({ service, downloads, file, children }: {
  service?: ExportService; downloads?: DownloadPort; file: string;
  children(slots: { navbar: ReactNode; overlay: ReactNode }): ReactNode;
}) {
  const { t } = useI18n();
  const [source, setSource] = useState<ExportView | null>(null);
  const [snapshot, setSnapshot] = useState<ExportView | null>(null);
  const [open, setOpen] = useState(false);
  const [format, setFormat] = useState('step');
  const [options, setOptions] = useState<{ epoch: string; formats: ExportOption[] } | null>(null);
  const [error, setError] = useState('');
  const [reveal, setReveal] = useState(0);
  const [activity, setActivity] = useState<Record<string, boolean>>({});
  const reportActivity = useCallback((id: string, busy: boolean) => setActivity(old => old[id] === busy ? old : { ...old, [id]: busy }), []);
  const [attempts, setAttempts] = useState<ExportRecord[]>(() => downloads?.restore?.() || []);
  useEffect(() => { downloads?.remember?.(attempts); }, [attempts, downloads]);
  // The document as its code built it: the file holds what the code made, never a selection or a pose.
  const spec = useMemo<ExportSource | null>(() => snapshot ? { doc: snapshot.doc, revision: snapshot.revision } : null, [snapshot]);
  useEffect(() => {
    setOptions(null); setError('');
    if (!open || !spec || !service) return;
    const controller = new AbortController();
    service.options(spec, controller.signal).then(value => { if (!controller.signal.aborted) setOptions(value); }, failure => { if (!controller.signal.aborted) setError(message(failure)); });
    return () => controller.abort();
  }, [open, spec, service]);
  const selected = options?.formats.find(row => row.format === format);
  useEffect(() => {
    if (options && (!selected || selected.reason)) setFormat(options.formats.find(row => !row.reason)?.format || 'step');
  }, [options, selected]);
  const displayed = source?.file === file ? source : null;
  const changeOpen = (next: boolean) => {
    if (next) { setSnapshot(displayed); setReveal(n => n + 1); }
    setOpen(next);
  };
  const begin = () => {
    if (!selected || selected.reason || !spec || !snapshot || !options) return;
    // The exact displayed revision, as the menu showed it.
    const request: ExportRequest = { requestId: crypto.randomUUID(), epoch: options.epoch, source: spec, format: selected.format };
    const stem = (snapshot.name.split('::').pop() || 'model').replace(/\.[^.]+$/, '').replace(/[<>:"/\\|?*\u0000-\u001f]/g, '_').slice(0, 100);
    const filename = (stem || 'model') + selected.extension;
    setAttempts(old => [...old, { request, filename, delivered: false }]);
    setReveal(n => n + 1); setOpen(false);
  };
  const enabled = Boolean(service && downloads);
  const label = t('export.button');
  const navbar = enabled && (displayed || attempts.length) ? <Popover open={open} onOpenChange={changeOpen}>
    <TooltipHint content={label} side="bottom" disabled={open}>
      <PopoverTrigger asChild><Button type="button" variant="ghost" size="icon-xs" aria-label={label} className={NAVBAR_CONTROL_CLASS} data-export-menu="">
        {attempts.some(row => activity[row.request.requestId]) ? <Spinner className="size-3.5" /> : <ArrowDownToLine className="size-3.5" />}
      </Button></PopoverTrigger>
    </TooltipHint>
    <PopoverContent align="end" className="w-72 space-y-3 p-3 text-tiny" aria-label={t('export.heading')}>
      <p className="text-muted-foreground">{t('export.heading')}</p>
      {snapshot ? <>
        <p className="text-muted-foreground">{snapshot.preview ? t('export.preview') + ' ' : ''}{t('export.geometry')}</p>
        {options ? <label className="block space-y-1"><span>{t('export.format')}</span><Select value={format} onValueChange={setFormat}><SelectTrigger size="sm" className="text-tiny" aria-label={t('export.format')}><SelectValue /></SelectTrigger><SelectContent>{options.formats.filter(row => !row.reason).map(row => <SelectItem key={row.format} value={row.format}>{row.format === 'original' ? t('export.original') : row.label}</SelectItem>)}</SelectContent></Select></label>
          : !error ? <p role="status" className="flex items-center gap-2 text-muted-foreground"><Spinner className="size-3" />{t('export.checking')}</p> : null}
        {options ? <Button className="w-full text-tiny" size="sm" disabled={!selected || Boolean(selected.reason)} onClick={begin}>{t('export.start')}</Button> : null}
      </> : <p className="text-muted-foreground">{t('export.open')}</p>}
      {error ? <p role="alert" className="text-destructive">{error}</p> : null}
      {attempts.length ? <Button size="xs" variant="outline" className="text-tiny" onClick={() => { setReveal(n => n + 1); setOpen(false); }}>{t('export.show', { count: attempts.length })}</Button> : null}
    </PopoverContent>
  </Popover> : null;
  const overlay = enabled && attempts.length ? <ToastStack label={t('export.jobs')}>
    {attempts.map(attempt => <ExportToast key={attempt.request.requestId} attempt={attempt} service={service!} downloads={downloads!} reveal={reveal} onActivity={reportActivity}
      onDelivered={() => setAttempts(old => old.map(row => row.request.requestId === attempt.request.requestId ? { ...row, delivered: true } : row))}
      onRemove={() => setAttempts(old => old.filter(row => row.request.requestId !== attempt.request.requestId))}
      // The file is gone (downloaded, or past its window): the same export run again, in its place.
      onExportAgain={() => setAttempts(old => old.map(row => row.request.requestId === attempt.request.requestId
        ? { request: { ...row.request, requestId: crypto.randomUUID() }, filename: row.filename, delivered: false } : row))} />)}
  </ToastStack> : null;
  return <ExportContext.Provider value={enabled ? setSource : null}>{children({ navbar, overlay })}</ExportContext.Provider>;
}
