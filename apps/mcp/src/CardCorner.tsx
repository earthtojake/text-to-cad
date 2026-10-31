import type { ReactNode } from 'react';

/**
 * The file handler's corner: what this host adds to the one view that has no navbar (`chrome: "bare"`,
 * Codex's file handler), at the top-right of the viewport — the column that holds the host's notice
 * and Quick Edit under it (`ViewportTopRight`). Full size first, where the host offers it, then the
 * update button while this install is behind. Gone in Preview, as the rest of the column is. Only
 * its controls take presses: the model under the rest of its width stays reachable. Every other
 * view carries these in its navbar.
 */
export function CardCorner({ fullSize = null, update = null }: { fullSize?: ReactNode; update?: ReactNode }) {
  if (!fullSize && !update) return null;
  return <div className="pointer-events-none flex w-full flex-col items-end gap-2" data-card-corner="">
    {fullSize ? <div className="pointer-events-auto">{fullSize}</div> : null}
    {update ? <div className="pointer-events-auto">{update}</div> : null}
  </div>;
}
