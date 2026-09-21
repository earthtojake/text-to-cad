import { lazy, Suspense, type ReactNode } from 'react';

export interface EmptyCadBackdropProps {
  colorScheme?: 'light' | 'dark';
  children?: ReactNode;
}

// The backdrop is the HOST's (it is what a host shows when there is no file to
// show), so it lives beside the file viewer rather than inside a renderer. Its
// stage is still the STEP renderer's viewport with nothing in it; rebuilding it
// on `ShellViewport` with a null scene is what removes this one edge into the
// slice, and belongs with the slice's move onto the shell.
const EmptyCadStage = lazy(() => import('../renderers/step/components/EmptyCadStage.js'));

/** The original empty CAD stage, loaded only when a host displays it. */
export function EmptyCadBackdrop({ children, ...props }: EmptyCadBackdropProps) {
  return <div className="relative h-full w-full" data-cad-empty-stage>
    <Suspense fallback={null}><EmptyCadStage {...props} /></Suspense>
    {children}
  </div>;
}
