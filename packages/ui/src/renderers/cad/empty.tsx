import { lazy, Suspense, type ReactNode } from 'react';

export interface EmptyCadBackdropProps {
  colorScheme?: 'light' | 'dark';
  children?: ReactNode;
}

const EmptyCadStage = lazy(() => import('./components/EmptyCadStage.js'));

/** The original empty CAD stage, loaded only when a host displays it. */
export function EmptyCadBackdrop({ children, ...props }: EmptyCadBackdropProps) {
  return <div className="relative h-full w-full" data-cad-empty-stage>
    <Suspense fallback={null}><EmptyCadStage {...props} /></Suspense>
    {children}
  </div>;
}
