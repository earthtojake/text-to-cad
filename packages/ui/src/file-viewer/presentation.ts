import { createElement } from 'react';
import Overlay from '../renderers/kit/status/ViewerLoadingOverlay.js';
import { resolveViewportTheme } from '@cad/core/lib/viewportTheme.js';

export interface CadArtifactProgress {
  phase: string;
  label: string;
  detail: string;
  index: number;
  count: number;
  done: number;
  total: number | null;
  determinate: boolean;
  updatedAt: number;
}
export interface ViewerLoadingOverlayProps {
  viewerLoading: boolean;
  progress?: CadArtifactProgress | null;
  /** The viewport's Background, the tab's (`viewportBackground`: "light" or "dark"): what the cover is drawn on. */
  background?: string | null;
}
/**
 * The original CAD loading artwork, available before loading the renderer, drawn on the viewport's Background as the
 * person has it (the view's own cover and its picture are on it too), its words, mark and bar in that scheme's ink.
 */
export function ViewerLoadingOverlay({ viewerLoading, progress, background = null }: ViewerLoadingOverlayProps) {
  const { scheme } = resolveViewportTheme(background ?? undefined);
  return createElement('div', { className: `contents ${scheme}`, 'data-viewport-scheme': scheme },
    createElement(Overlay, { loading: { opening: viewerLoading, headline: "Opening model", progress }, operationKey: "preparing-document" }));
}
