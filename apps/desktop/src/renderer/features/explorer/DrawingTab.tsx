import { Component, lazy, Suspense } from 'react';
import type { ReactNode } from 'react';
import type { Project } from '@shared/types';

const DrawingSurface = lazy(() => import('./drawing/DrawingSurface'));
export interface DrawingTabProps { sessionId: string; tabId: string; project: Project; root: string | null; title: string }

class DrawingBoundary extends Component<{ children: ReactNode }, { error: string | null }> {
  override state = { error: null as string | null };
  static getDerivedStateFromError(error: unknown) {
    return { error: error instanceof Error ? error.message : 'The drawing could not be opened.' };
  }
  override render() {
    if (this.state.error) return <div className="p-4 text-muted-foreground" role="alert">{this.state.error}</div>;
    return this.props.children;
  }
}

export function DrawingTab(props: DrawingTabProps) {
  return <DrawingBoundary><Suspense fallback={<div className="p-4 text-muted-foreground">Opening drawing…</div>}>
    <DrawingSurface {...props} />
  </Suspense></DrawingBoundary>;
}
