import { X } from 'lucide-react';
import { Button } from '@text-to-cad/ui/primitives/button';

/** A line over the view, the model still under it: what stopped working, and what to do about it. */
export function Banner({ message }: { message: string }) {
  // Below the navbar row, so it never sits over its controls.
  return <div className="pointer-events-none absolute inset-x-0 top-12 z-50 flex justify-center px-3">
    <div className="pointer-events-auto max-w-md rounded-md border bg-background/95 px-3 py-2 text-ui text-xs text-foreground shadow-sm" role="alert">{message}</div>
  </div>;
}

/** A whole-page message: why CAD cannot show anything, and what to do about it. */
export default function Notice({ title, message, details }: { title: string; message: string; details?: string }) {
  return <div className="cad-notice text-ui" role="alert">
    <div className="flex max-w-md flex-col items-start gap-3">
      <h1 className="text-base font-medium">{title}</h1>
      <p className="text-muted-foreground">{message}</p>
      {details && <details className="w-full text-tiny text-muted-foreground"><summary className="cursor-pointer">Details</summary><pre className="mt-2 whitespace-pre-wrap break-all select-text">{details}</pre></details>}
    </div>
  </div>;
}

/**
 * The one question CAD asks, once, of everyone who runs it: whether to share anonymous usage
 * statistics. Nothing is sent before a yes, and any answer ends the question (closing it is No
 * thanks); Settings' Analytics section changes it later. It keeps to the top-right corner: the
 * home's, and the viewer's under its navbar.
 */
export function ConsentCard({ placement, policy, onAnswer, onPolicy }: { placement: 'home' | 'viewer'; policy: string; onAnswer(share: boolean): void; onPolicy(url: string): void }) {
  // Top-right: the home has no navbar to keep under; the viewer's card sits below its navbar.
  const corner = placement === 'home' ? 'right-3 top-3' : 'right-3 top-12';
  return <div className={`absolute z-50 w-[calc(100%-1.5rem)] max-w-xs ${corner}`} data-placement={placement}>
    <div className="flex flex-col gap-2 rounded-md border bg-popover p-3 text-ui text-popover-foreground shadow-md" role="dialog" aria-labelledby="cad-consent-title">
      <div className="flex items-center justify-between gap-2">
        <h2 id="cad-consent-title" className="font-medium">Allow Analytics</h2>
        {/* Closing is an answer, No thanks: the card never comes back to ask again. */}
        <Button variant="ghost" size="icon-xs" className="-mr-1" aria-label="Close and don't share" onClick={() => onAnswer(false)}><X aria-hidden="true" /></Button>
      </div>
      <p className="text-xs text-muted-foreground">
        Help improve text-to-cad by sending anonymous usage statistics. We never collect your files, models or
        prompts. Read our{' '}
        {/* A real link, to a new tab; a frame that cannot open one hands it to its host (`ui/open-link`). */}
        <a href={policy} target="_blank" rel="noreferrer" className="text-foreground underline underline-offset-2"
          onClick={event => { event.preventDefault(); onPolicy(policy); }}>Privacy Policy</a>.
      </p>
      <div className="flex justify-end gap-2">
        <Button variant="outline" size="xs" className="font-medium" onClick={() => onAnswer(false)}>No thanks</Button>
        <Button size="xs" className="font-medium" onClick={() => onAnswer(true)}>Allow</Button>
      </div>
    </div>
  </div>;
}
