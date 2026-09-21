import { lazy, Suspense, type ReactNode } from 'react';

export interface EmptyCadBackdropProps {
  colorScheme?: 'light' | 'dark';
  children?: ReactNode;
}

// The backdrop is the HOST's (it is what a host shows when there is no file to show), so it
// lives beside the file viewer and is built out of the kit alone: `ShellViewport` with a
// null scene. Nothing here reaches into a family slice — the host's empty state must not
// load a renderer to draw a stage with no model in it.
const EmptyCadStage = lazy(() => import('./EmptyCadStage.js'));

/** The empty CAD stage, loaded only when a host displays it. */
export function EmptyCadBackdrop({ children, ...props }: EmptyCadBackdropProps) {
  return <div className="relative h-full w-full" data-cad-empty-stage>
    <Suspense fallback={null}><EmptyCadStage {...props} /></Suspense>
    {children}
  </div>;
}
