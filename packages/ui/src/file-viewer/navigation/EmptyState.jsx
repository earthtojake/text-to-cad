import { cn } from "@cad/ui/utils";
import { Button } from "@cad/ui/primitives/button";

/**
 * The one status screen, used by every full-area state in both apps: a file that is not there, one that would not
 * open, CAD not running, a link that no longer works, the page's first answer not coming (`docs/viewer-ux.md`,
 * "Loading and status screens").
 *
 * Quiet, as the loading indicator it stands in the place of (`loading/LoadingStep.jsx`): no icon, no tinted tile,
 * nothing decorative. One 22rem column centred in the area, left-aligned on one line: the title in the chrome's text,
 * the explanation 4px under it in the muted ink (wide enough that a two-sentence explanation wraps into two lines,
 * `text-pretty` keeping a last word from standing alone), then, 12px under it, the action as a small quiet button
 * (`StatusAction`), its box on the same line as the text. In the app's theme: a page state has no viewport to take a
 * Background from.
 *
 * @param {object} props
 * @param {string} props.title
 * @param {string} [props.description]
 * @param {import("react").ReactNode} [props.action] A `StatusAction`.
 * @param {string} [props.className]
 */
export function EmptyState({ title, description, action, className }) {
  return (
    <div className={cn("flex h-full min-h-0 items-center justify-center px-8", className)} data-status-screen="">
      <div className="flex w-[22rem] max-w-full flex-col items-start text-left text-ui">
        <p className="text-foreground" data-status-title="">{title}</p>
        {description ? <p className="mt-1 text-pretty text-muted-foreground [overflow-wrap:anywhere]">{description}</p> : null}
        {action ? <div className="mt-3">{action}</div> : null}
      </div>
    </div>
  );
}

/**
 * A status screen's action: a small quiet button, the panel's 28px in the chrome's text, with a hairline border and
 * no shadow so it reads as a button on a page with nothing else on it, and nothing more.
 * @param {import("react").ButtonHTMLAttributes<HTMLButtonElement>} props
 */
export function StatusAction({ className, ...props }) {
  return <Button type="button" variant="outline" size="xs" className={cn("h-control px-2.5 text-ui font-normal shadow-none", className)} {...props} />;
}
