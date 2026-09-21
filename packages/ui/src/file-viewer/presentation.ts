import { createElement, type ComponentType } from 'react';
import Overlay from '../renderers/kit/status/ViewerLoadingOverlay.js';
import Toast from '../renderers/kit/status/StatusToast.js';

export { default as MissingFileAlert } from '../renderers/kit/status/MissingFileAlert.js';
export type { MissingFileAlertProps } from '../renderers/kit/status/MissingFileAlert.js';

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
  previewMode?: boolean;
  progress?: CadArtifactProgress | null;
}
/** The original CAD loading artwork, available before loading the renderer. */
export function ViewerLoadingOverlay({ viewerLoading, previewMode, progress }: ViewerLoadingOverlayProps) {
  return createElement(Overlay, { loading: { opening: viewerLoading, headline: "Opening model", progress }, previewMode, operationKey: "preparing-document" });
}

export interface StatusToastProps {
  copyStatus?: string;
  screenshotStatus?: string;
  previewMode?: boolean;
  onClear?: () => void;
}
export const StatusToast = Toast as ComponentType<StatusToastProps>;
