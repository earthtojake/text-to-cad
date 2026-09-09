import { MinusIcon, PlusIcon, RotateCcwIcon, XIcon } from 'lucide-react';
import * as React from 'react';
import {
  TransformComponent,
  TransformWrapper,
  type ReactZoomPanPinchContentRef,
} from 'react-zoom-pan-pinch';
import { Button } from '@/react/primitives/button';
import { Dialog } from '@/react/primitives/dialog';
import * as styles from './image-viewer.css';

const TOOLBAR_ZOOM_STEP = 0.25;
const WHEEL_ZOOM_STEP = 0.12;
const MIN_ZOOM = 0.5;
const MAX_ZOOM = 64;
const MAX_INITIAL_ZOOM = 12;
const MIN_ZOOM_OUT_FACTOR = 0.5;
const MAX_ZOOM_IN_FACTOR = 10;

interface ZoomBounds {
  minScale: number;
  maxScale: number;
}

const DEFAULT_ZOOM_BOUNDS: ZoomBounds = {
  minScale: MIN_ZOOM,
  maxScale: MAX_ZOOM,
};

export interface ZoomViewerApi {
  /** Re-centers and rescales the content so it fits the viewport. */
  fitToView: (animationTime?: number) => void;
}

export interface ZoomViewerDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Accessible label for the dialog; no visible title is rendered. */
  ariaLabel: string;
  /** Identity of the displayed content; the zoom transform resets when it changes. */
  contentKey: string;
  /**
   * Arbitrary zoomable content. The render-prop form receives the viewer API so
   * async content (e.g. an image load) can trigger a re-fit once it has a size.
   */
  children: React.ReactNode | ((api: ZoomViewerApi) => React.ReactNode);
}

/**
 * Computes the scale at which the content fits the wrapper and centers on it.
 * Returns null when either element has no layout yet.
 */
function fitContentToView(controls: ReactZoomPanPinchContentRef, animationTime = 0): number | null {
  const { wrapperComponent, contentComponent } = controls.instance;
  if (!wrapperComponent || !contentComponent) return null;

  const contentWidth = contentComponent.offsetWidth;
  const contentHeight = contentComponent.offsetHeight;
  if (contentWidth <= 0 || contentHeight <= 0) return null;

  const scale = Math.min(
    MAX_INITIAL_ZOOM,
    Math.max(
      MIN_ZOOM,
      Math.min(
        wrapperComponent.offsetWidth / contentWidth,
        wrapperComponent.offsetHeight / contentHeight
      )
    )
  );

  controls.centerView(scale, animationTime);
  return scale;
}

/** Derives dynamic zoom limits from the fit scale so small and huge content both zoom sensibly. */
function zoomBoundsForFitScale(fitScale: number): ZoomBounds {
  return {
    minScale: Math.max(MIN_ZOOM, fitScale * MIN_ZOOM_OUT_FACTOR),
    maxScale: Math.min(MAX_ZOOM, Math.max(fitScale * MAX_ZOOM_IN_FACTOR, fitScale + 4)),
  };
}

function ToolbarButton({
  label,
  onClick,
  children,
}: {
  label: string;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <Button
      type="button"
      variant="ghost"
      size="xs"
      icon
      aria-label={label}
      title={label}
      className={styles.toolbarButton}
      onClick={onClick}
    >
      {children}
    </Button>
  );
}

const toolbarIconStyle: React.CSSProperties = { width: '1rem', height: '1rem' };

function ZoomToolbar({
  controls,
  onFit,
  onClose,
}: {
  controls: ReactZoomPanPinchContentRef;
  onFit: () => void;
  onClose: () => void;
}) {
  return (
    <div className={styles.toolbarRow}>
      <div className={styles.toolbarGroup}>
        <ToolbarButton label="Zoom in" onClick={() => controls.zoomIn(TOOLBAR_ZOOM_STEP)}>
          <PlusIcon style={toolbarIconStyle} />
        </ToolbarButton>
        <ToolbarButton label="Zoom out" onClick={() => controls.zoomOut(TOOLBAR_ZOOM_STEP)}>
          <MinusIcon style={toolbarIconStyle} />
        </ToolbarButton>
        <ToolbarButton label="Fit to view" onClick={onFit}>
          <RotateCcwIcon style={toolbarIconStyle} />
        </ToolbarButton>
        <ToolbarButton label="Close" onClick={onClose}>
          <XIcon style={toolbarIconStyle} />
        </ToolbarButton>
      </div>
    </div>
  );
}

/**
 * Near-fullscreen dialog that renders arbitrary content (images, inline SVG,
 * pre-rendered diagram markup) inside a pan/zoom surface with a fit-to-view
 * toolbar. Zoom bounds derive from the computed fit scale; the transform is
 * reset on every open via a keyed remount.
 */
export function ZoomViewerDialog({
  open,
  onOpenChange,
  ariaLabel,
  contentKey,
  children,
}: ZoomViewerDialogProps) {
  const [zoomBounds, setZoomBounds] = React.useState<ZoomBounds>(DEFAULT_ZOOM_BOUNDS);
  const [openSession, setOpenSession] = React.useState(0);

  React.useEffect(() => {
    if (!open) return;

    setZoomBounds(DEFAULT_ZOOM_BOUNDS);
    setOpenSession((session) => session + 1);
  }, [open, contentKey]);

  const fitToView = (controls: ReactZoomPanPinchContentRef, animationTime = 0) => {
    const fitScale = fitContentToView(controls, animationTime);
    if (fitScale !== null) setZoomBounds(zoomBoundsForFitScale(fitScale));
  };

  const scheduleInitialFit = (controls: ReactZoomPanPinchContentRef) => {
    // Wait a frame so the dialog and content have layout before measuring.
    window.requestAnimationFrame(() => fitToView(controls));
  };

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Content size="full" aria-label={ariaLabel}>
        <TransformWrapper
          key={`${contentKey}:${openSession}`}
          limitToBounds={false}
          minScale={zoomBounds.minScale}
          maxScale={zoomBounds.maxScale}
          wheel={{ step: WHEEL_ZOOM_STEP }}
          doubleClick={{ mode: 'toggle' }}
          onInit={scheduleInitialFit}
        >
          {(controls) => (
            <>
              <ZoomToolbar
                controls={controls}
                onFit={() => fitToView(controls, 200)}
                onClose={() => onOpenChange(false)}
              />
              <div className={styles.viewerBody}>
                <TransformComponent
                  wrapperClass={styles.transformWrapper}
                  wrapperStyle={{ height: '100%', width: '100%' }}
                  contentStyle={{ height: 'fit-content', width: 'fit-content' }}
                >
                  {typeof children === 'function'
                    ? children({
                        fitToView: (animationTime = 0) => fitToView(controls, animationTime),
                      })
                    : children}
                </TransformComponent>
              </div>
            </>
          )}
        </TransformWrapper>
      </Dialog.Content>
    </Dialog.Root>
  );
}
