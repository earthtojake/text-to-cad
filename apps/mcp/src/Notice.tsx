import { english, resolveLocale, translator } from '@cad/ui/i18n';
import type { Ref } from 'react';
import { OPEN_IN_VIEWER, unreachableKey } from './host/unreachable.js';
import type { Refusal } from './host/server';

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

/** A whole-page message: why CAD cannot show anything, and what to do about it (`notice.css`). */
export default function Notice({ title, message, details, t = english }: { title: string; message: string; details?: string; t?: Translate }) {
  return <div className="cad-notice" role="alert">
    <div className="cad-notice-body">
      <h1 className="cad-notice-title">{title}</h1>
      <p className="cad-notice-line cad-notice-muted">{message}</p>
      {details && <details className="w-full text-tiny cad-notice-muted"><summary className="cursor-pointer">{t('alert.details')}</summary><pre className="mt-2 whitespace-pre-wrap break-all select-text">{details}</pre></details>}
    </div>
  </div>;
}

/**
 * What a card that cannot reach CAD's server says (`Connection.tsx`), and nothing else: no home, no
 * library, nothing the host or the server said. Its chat carries none of its calls (`host/channel.ts`),
 * or the server refused them for their capability (`refused`: none, or one from before CAD restarted,
 * which asks for the model to be shown again). `page` is the CAD Viewer's page of what the card was
 * asked to show, from its launch, where the engine gave one; `open` follows it through the host, where
 * the host opens links, and returns false where it does not (the link then opens as an ordinary one,
 * in a new window). Said in `t`'s language, in the look the shell's notice has too (`notice.css`).
 */
export function Unreachable({ page, model, refused = null, open, t = english, ref }: {
  page: string | null; model: boolean; refused?: Refusal | null; open?: (url: string) => boolean; t?: Translate; ref?: Ref<HTMLDivElement>;
}) {
  const message = t(unreachableKey(Boolean(page), model, refused));
  return <div ref={ref} className="cad-notice" role="alert" data-cad-unreachable="">
    <div className="cad-notice-body">
      <p className="cad-notice-line">{message}</p>
      {page ? <a href={page} target="_blank" rel="noopener noreferrer" className="cad-notice-button"
        onClick={event => { if (open?.(page)) event.preventDefault(); }}>{t(OPEN_IN_VIEWER)}</a> : null}
    </div>
  </div>;
}
