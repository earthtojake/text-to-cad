import { useCallback, useContext, useEffect, useRef, useState, type ReactNode } from 'react';
import { ArrowDownToLine } from 'lucide-react';
import { toast } from 'sonner';
import { ExportRequestError, exportPause, type ExportJob, type ExportRequest, type ExportService } from '@text-to-cad/core/client';
import type { DownloadPort, ExportRecord } from '../host/types.js';
import { ViewerElementContext } from '../host/context.js';
import { Button } from '../primitives/button.jsx';
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from '../primitives/dropdown-menu.jsx';
import { Toaster } from '../primitives/sonner.jsx';
import { TooltipHint } from '../primitives/tooltip.jsx';
import { FLOATING_SURFACE_CLASS } from '../lib/floatingSurface.js';
import { NAVBAR_CONTROL_CLASS } from '../lib/navbarRow.js';
import { cn } from '../lib/utils.js';
import { useI18n } from '../i18n/index.js';
import { useViewerMobile } from '../file-viewer/responsive.js';
import { ExportContext, type ExportView } from './context.js';
import { exportChoices, type ExportChoice } from './formats.js';
import { useControlUsage } from '../usage/controls.js';

type Translate = ReturnType<typeof useI18n>['t'];
const message = (error: unknown) => error instanceof Error ? error.message : String(error);
// A refusal (4xx) is the export's answer; a dropped connection or a 5xx is asked again.
const retryable = (error: unknown) => !(error instanceof ExportRequestError) || error.status >= 500;
const running = (job: ExportJob) => job.state === 'queued' || job.state === 'running' || job.state === 'cancelling';

/**
 * One export, as a browser download is: its toast says it is being prepared ("Preparing
 * bracket.step…", spinning) while the job is queued or running, and also while the connection is
 * down and asked again; once the file is ready it is handed to the browser (whose own downloads
 * decide where it goes, and say so) and the toast goes that moment, with no success toast of its
 * own; or the toast is the engine's one-line reason, kept until dismissed. A request made from the menu learns
 * its session's epoch first and is kept with it (`onRequest`), so a reload reconnects to its job
 * by it, and a server restarted since refuses it rather than running it again.
 */
async function runExport({ record, service, downloads, t, signal, onRequest }: {
  record: ExportRecord; service: ExportService; downloads: DownloadPort; t(): Translate; signal: AbortSignal;
  onRequest(request: ExportRequest): void;
}) {
  const id = record.request.requestId;
  let request = record.request;
  // The page's name for the file while it is made (a queued job's is a placeholder); then the
  // ready job's, the one its Content-Disposition gives every browser.
  toast.loading(t()('export.preparing', { name: record.filename }), { id });
  const fail = (reason: string) => toast.error(reason || t()('export.failed'), { id, duration: Infinity, closeButton: true });
  let job: ExportJob | null = null;
  let failures = 0;
  for (;;) {
    try {
      if (!request.epoch) {
        request = { ...request, epoch: await service.epoch(signal) };
        if (signal.aborted) return;
        onRequest(request);
      }
      job = job ? await service.status(job.id, job.sequence, signal) : await service.create(request, signal);
      if (signal.aborted) return;
      failures = 0;
      if (running(job)) continue;
      const name = job.filename || record.filename;
      if (job.state === 'ready') {
        downloads.save(service.fileUrl(job.id), name);
        toast.dismiss(id);
      } else if (job.fetched) {
        // A request kept across a reload whose file the browser had already fetched whole.
        toast.dismiss(id);
      } else fail(job.error || job.stage);
      return;
    } catch (failure) {
      if (signal.aborted) return;
      if (!retryable(failure)) { fail(message(failure)); return; }
      // The toast keeps spinning: the job may still be running, and the poll resumes on its own.
      await exportPause(Math.min(1000 * 2 ** failures++, 10000), signal);
    }
  }
}

const GUTTER = 16;
/**
 * A toast as small as a menu item: one line of the menu's text (`text-tiny`, regular weight), its
 * padding, a 14px icon, and as wide as its text above Sonner's narrow-screen layout (a window up to
 * 600px, where Sonner spans its toasts across the screen). Sonner's own stylesheet is unlayered, so
 * each of these is `!important` to win over it; `primitives/sonner.jsx` stays shadcn's.
 */
const TOAST_CLASSES = {
  toast: 'gap-1.5! px-2.5! py-1.5! text-tiny! min-[601px]:w-max! min-[601px]:max-w-[calc(100vw-2rem)]!',
  title: 'font-normal! leading-4!',
  icon: 'size-3.5! [&_svg]:size-3.5!',
};

/** Where the toasts start: under the viewer's navbar (its top where it has none), by the gutter. */
function useBelowNavbar(mobile: boolean) {
  const viewer = useContext(ViewerElementContext);
  const [top, setTop] = useState(GUTTER);
  useEffect(() => {
    const element = viewer?.current;
    if (!element) return;
    const measure = () => {
      const bar = element.querySelector('[data-viewer-navbar]');
      setTop(Math.round(bar ? bar.getBoundingClientRect().bottom : element.getBoundingClientRect().top) + GUTTER);
    };
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    const bar = element.querySelector('[data-viewer-navbar]');
    if (bar) observer.observe(bar);
    return () => observer.disconnect();
  }, [viewer, mobile]);
  return top;
}

/** The exports' toasts, at the view's top right under its navbar. Rendered inside the viewer, so it
 * reads the viewer's own width (`useViewerMobile`), its navbar and its host's colour scheme. */
function ExportToaster() {
  const { t } = useI18n();
  const top = useBelowNavbar(useViewerMobile());
  const offset = { top, right: GUTTER, left: GUTTER };
  return <Toaster position="top-right" offset={offset} mobileOffset={offset}
    toastOptions={{ closeButtonAriaLabel: t('export.dismiss'), classNames: TOAST_CLASSES }} />;
}

export function ExportControls({ service, downloads, file, children }: {
  service?: ExportService; downloads?: DownloadPort; file: string;
  children(slots: { navbar: ReactNode; overlay: ReactNode }): ReactNode;
}) {
  const { t } = useI18n();
  const [source, setSource] = useState<ExportView | null>(null);
  const [open, setOpen] = useState(false);
  const translate = useRef(t); translate.current = t;
  // The exports still under way, kept in the tab so that a reload picks each up again; one leaves
  // as its file is handed over or it fails.
  const pending = useRef(new Map<string, ExportRecord>());
  const runs = useRef(new Set<AbortController>());
  const keep = useCallback(() => { downloads?.remember?.([...pending.current.values()]); }, [downloads]);
  const start = useCallback((record: ExportRecord) => {
    if (!service || !downloads) return;
    const controller = new AbortController();
    runs.current.add(controller);
    pending.current.set(record.request.requestId, record);
    keep();
    void runExport({ record, service, downloads, t: () => translate.current, signal: controller.signal,
      onRequest: request => { pending.current.set(request.requestId, { ...record, request }); keep(); } })
      .catch(() => {})
      .finally(() => {
        runs.current.delete(controller);
        if (controller.signal.aborted) return;
        pending.current.delete(record.request.requestId);
        keep();
      });
  }, [service, downloads, keep]);
  useEffect(() => {
    for (const record of downloads?.restore?.() || []) start(record);
    const live = runs.current;
    return () => { for (const controller of live) controller.abort(); live.clear(); };
  }, [downloads, start]);
  const displayed = source?.file === file ? source : null;
  // What the file on screen saves as, known from its kind: the menu has nothing to wait for.
  const choices = displayed ? exportChoices(displayed) : [];
  const usage = useControlUsage();
  const begin = (choice: ExportChoice) => {
    if (!displayed) return;
    usage.used(`export_${choice.format}`);
    // The document as its code built it, at the revision on screen: never a selection or a pose.
    const request: ExportRequest = { requestId: crypto.randomUUID(), epoch: '', source: { doc: displayed.doc, revision: displayed.revision }, format: choice.format };
    const stem = (displayed.name.split('::').pop() || 'model').replace(/\.[^.]+$/, '').replace(/[<>:"/\\|?*\u0000-\u001f]/g, '_').slice(0, 100);
    start({ request, filename: (stem || 'model') + choice.extension });
  };
  const enabled = Boolean(service && downloads);
  const label = t('export.button');
  // A dropdown of the formats, the file menu's own: a choice closes it and starts that export.
  const navbar = enabled && choices.length ? <DropdownMenu modal={false} open={open} onOpenChange={setOpen}>
    <TooltipHint content={label} side="bottom" disabled={open}>
      <DropdownMenuTrigger asChild><Button type="button" variant="ghost" size="icon-xs" aria-label={label} className={NAVBAR_CONTROL_CLASS} data-export-menu="">
        <ArrowDownToLine className="size-3.5" />
      </Button></DropdownMenuTrigger>
    </TooltipHint>
    {/* Closes with no exit animation, so a quick second press always reaches the button. */}
    <DropdownMenuContent align="end" sideOffset={6} collisionPadding={8} aria-label={label}
      className={cn(FLOATING_SURFACE_CLASS, 'data-[state=closed]:animate-none!')}>
      {choices.map(choice => <DropdownMenuItem key={choice.format} onSelect={() => begin(choice)} data-export-format={choice.format}>{choice.label}</DropdownMenuItem>)}
    </DropdownMenuContent>
  </DropdownMenu> : null;
  const overlay = enabled ? <ExportToaster /> : null;
  return <ExportContext.Provider value={enabled ? setSource : null}>{children({ navbar, overlay })}</ExportContext.Provider>;
}
