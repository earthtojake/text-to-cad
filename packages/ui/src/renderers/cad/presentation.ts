import type { ComponentType } from 'react';
import Overlay from './components/workbench/ViewerLoadingOverlay.js';
import Toast from './components/workbench/StatusToast.js';

export { default as MissingFileAlert } from './components/workbench/MissingFileAlert.js';
export type { MissingFileAlertProps } from './components/workbench/MissingFileAlert.js';

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
export const ViewerLoadingOverlay = Overlay as ComponentType<ViewerLoadingOverlayProps>;

export interface StatusToastProps {
  copyStatus?: string;
  screenshotStatus?: string;
  persistenceStatus?: string;
  motionErrorStatus?: string;
  previewMode?: boolean;
  onClear?: () => void;
}
export const StatusToast = Toast as ComponentType<StatusToastProps>;
