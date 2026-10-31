import { english, resolveLocale, translator } from '@text-to-cad/ui/i18n';

type Translate = (key: string, params?: Record<string, unknown>) => string;

/**
 * The language a notice outside the viewer reads in, before the person's own setting is known: the
 * host's locale (`hostLocale`), else the frame's browser languages (`resolveLocale`).
 */
export function noticeTranslator(hostLocale?: string): Translate {
  const languages = typeof navigator === 'undefined' ? [] : (navigator.languages ?? [navigator.language]);
  return translator(resolveLocale([hostLocale, ...languages]));
}

/** A line over the view, the model still under it: what stopped working, and what to do about it. */
export function Banner({ message }: { message: string }) {
  // Below the tool strip's row at the top centre, so it never sits over its tools.
  return <div className="pointer-events-none absolute inset-x-0 top-12 z-50 flex justify-center px-3">
    <div className="pointer-events-auto max-w-md rounded-md border bg-background/95 px-3 py-2 text-ui text-xs text-foreground shadow-sm" role="alert">{message}</div>
  </div>;
}

/** A whole-page message: why CAD cannot show anything, and what to do about it. */
export default function Notice({ title, message, details, t = english }: { title: string; message: string; details?: string; t?: Translate }) {
  return <div className="cad-notice text-ui" role="alert">
    <div className="flex max-w-md flex-col items-start gap-3">
      <h1 className="text-base font-medium">{title}</h1>
      <p className="text-muted-foreground">{message}</p>
      {details && <details className="w-full text-tiny text-muted-foreground"><summary className="cursor-pointer">{t('alert.details')}</summary><pre className="mt-2 whitespace-pre-wrap break-all select-text">{details}</pre></details>}
    </div>
  </div>;
}

/**
 * What a card whose chat carries none of its calls to the engine says (`host/channel.ts`), and
 * nothing else: no home, no library, nothing the host said. `page` is the CAD Viewer's page of what
 * the card was asked to show, from its launch, where the engine gave one; `open` follows it through
 * the host, where the host opens links, and returns false where it does not (the link then opens as
 * an ordinary one, in a new window). Said in `t`'s language.
 */
export function Unreachable({ page, model, open, t = english }: { page: string | null; model: boolean; open?: (url: string) => boolean; t?: Translate }) {
  const message = t(page ? (model ? 'cad.unreachable.openModel' : 'cad.unreachable.openViewer')
    : (model ? 'cad.unreachable.askModel' : 'cad.unreachable.askViewer'));
  return <div className="cad-notice text-ui" role="alert" data-cad-unreachable="">
    <div className="flex max-w-md flex-col items-start gap-3">
      <p className="text-foreground">{message}</p>
      {page ? <a href={page} target="_blank" rel="noopener noreferrer"
        className="rounded-md border px-3 py-1.5 text-xs font-medium text-foreground hover:bg-muted"
        onClick={event => { if (open?.(page)) event.preventDefault(); }}>{t('cad.openInViewer')}</a> : null}
    </div>
  </div>;
}
