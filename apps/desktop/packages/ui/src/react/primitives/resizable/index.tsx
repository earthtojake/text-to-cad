'use client';

import { cx } from '@styles/utilities/cx';
import { useRef } from 'react';
import * as ResizablePrimitive from 'react-resizable-panels';
import * as styles from './resizable.css';

export type ResizableGroupProps = ResizablePrimitive.GroupProps;
export type ResizablePanelProps = ResizablePrimitive.PanelProps;
export type ResizableHandleProps = ResizablePrimitive.SeparatorProps & {
  /**
   * `hairline` (default) renders an always-visible 1px line; `ghost` is
   * invisible until hovered, for layouts that draw their own divider.
   */
  variant?: 'hairline' | 'ghost';
};

/**
 * Layout container for resizable panels. Renders panels side by side when
 * `orientation="horizontal"` (default) and stacked when `"vertical"`.
 */
function ResizableGroup(props: ResizableGroupProps) {
  return <ResizablePrimitive.Group data-slot="resizable-group" {...props} />;
}

function ResizablePanel(props: ResizablePanelProps) {
  return <ResizablePrimitive.Panel data-slot="resizable-panel" {...props} />;
}

/**
 * Drag handle between two panels.
 *
 * Restores keyboard focus to the previously-focused element after a pointer
 * drag: the separator receives focus on pointerdown, and without this it
 * would keep focus after the drag, silently stealing it from whatever the
 * user was working in (deliberate behavior carried over from the legacy app
 * kit). Capture-phase focus is used because react-resizable-panels overrides
 * a plain `onFocus` prop with its own internal handler.
 */
function ResizableHandle({
  className,
  variant = 'hairline',
  onFocusCapture,
  onPointerUp,
  onPointerCancel,
  ...props
}: ResizableHandleProps) {
  const previousFocusRef = useRef<HTMLElement | null>(null);

  const restoreFocus = () => {
    previousFocusRef.current?.focus();
    previousFocusRef.current = null;
  };

  return (
    <ResizablePrimitive.Separator
      data-slot="resizable-handle"
      className={cx(styles.handle({ variant }), className)}
      onFocusCapture={(e) => {
        // `document.activeElement` is already the separator by the time focus
        // fires; relatedTarget holds the element that was focused before it.
        if (e.relatedTarget instanceof HTMLElement) {
          previousFocusRef.current = e.relatedTarget;
        }
        onFocusCapture?.(e);
      }}
      onPointerUp={(e) => {
        restoreFocus();
        onPointerUp?.(e);
      }}
      onPointerCancel={(e) => {
        restoreFocus();
        onPointerCancel?.(e);
      }}
      {...props}
    />
  );
}

export const Resizable = {
  Group: ResizableGroup,
  Panel: ResizablePanel,
  Handle: ResizableHandle,
};

// Layout-persistence helper, exposed here so consumers depend on @emdash/ui
// rather than on react-resizable-panels directly. The hook accepts any
// `Storage`-shaped object (including `localStorage`, the library default when
// none is passed); the emdash app always passes an explicit memento-backed
// `LayoutStorage` facade (`createLayoutStorage`) — no localStorage layout
// persistence in app code. Imperative panel handles (`usePanelRef`,
// collapse/expand/resize) are deliberately not re-exported: visibility is
// store-driven conditional rendering via `useCollapsiblePanelBinding`, never
// programmatic panel writes.
export { useDefaultLayout as useResizableDefaultLayout } from 'react-resizable-panels';

export {
  useCollapsiblePanelBinding,
  type CollapsiblePanelBinding,
  type CollapsiblePanelBindingOptions,
  type LayoutStorage,
} from './use-collapsible-panel-binding';
