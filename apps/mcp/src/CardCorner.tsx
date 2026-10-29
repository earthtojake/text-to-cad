import { useId, type ReactNode } from 'react';
import { UpdateCard, type UpdateNotice as Notice, type UpdateStart } from '@text-to-cad/ui/update';

/**
 * The file handler's corner: what this host adds to the one view that has no navbar (`chrome: "bare"`,
 * Codex's file handler), at the top-right of the viewport — the column that holds the host's notice
 * and Quick Edit under it (`ViewportTopRight`). Full size first, where the host offers it, then the
 * update notice while this install is behind. Gone in Preview, as the rest of the column is. Only
 * its controls take presses: the model under the rest of its width stays reachable. Every other
 * view carries these in its navbar.
 */
export function CardCorner({ fullSize = null, update = null }: { fullSize?: ReactNode; update?: ReactNode }) {
  if (!fullSize && !update) return null;
  return <div className="pointer-events-none flex w-full flex-col items-end gap-2" data-card-corner="">
    {fullSize ? <div className="pointer-events-auto">{fullSize}</div> : null}
    {update ? <div className="pointer-events-auto w-full">{update}</div> : null}
  </div>;
}

/**
 * A newer text-to-cad, as a notice in the file handler's corner rather than the navbar's blue button: the update
 * card itself (`UpdateCard`: the install command, Send to agent where the host takes messages, else Copy
 * command, and Manual installation; or, where the engine updates itself, its failure and Try again, whose
 * run it follows), while it leaves the person something to do or a run it
 * started is under way (`onRun`), until the person closes it for this view. Always open, it reads the
 * notice again as the window regains focus, and every two seconds while its run is under way.
 */
export function UpdateNotice({ notice, send, copy, onLink, onClose, update, onRun }: {
  notice: Notice; send?: (prompt: string) => Promise<void>; copy(prompt: string): Promise<void>; onLink(url: string): void; onClose(): void;
  update?: UpdateStart; onRun?(running: boolean): void;
}) {
  const id = useId();
  return <section aria-labelledby={`${id}-title`} aria-describedby={`${id}-text`} data-update-notice="">
    <UpdateCard id={id} notice={notice} send={send} copy={copy} onLink={onLink} onClose={onClose} update={update} onRun={onRun} />
  </section>;
}
