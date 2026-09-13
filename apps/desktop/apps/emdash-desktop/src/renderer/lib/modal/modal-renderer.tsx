import { Dialog as DialogPrimitive } from '@base-ui/react/dialog';
import { Dialog } from '@emdash/ui/react/primitives';
import { reaction } from 'mobx';
import { observer } from 'mobx-react-lite';
import { useCallback, useEffect, useLayoutEffect, useMemo, useRef } from 'react';
import { modalScope } from '@core/features/workbench/contributions/scopes';
import { modalCatalog } from '@core/manifests/browser/modal-catalog';
import { confirmRegistry } from '@core/primitives/keybindings/browser';
import {
  ModalHostContext,
  type ModalHostController,
  type ModalPosition,
  type ModalSize,
} from '@core/primitives/modals/react';
import { modalStore, type ModalStackEntry } from '@core/primitives/modals/react/modal-store';
import { cn } from '@core/primitives/styling/browser/cn';
import { disabled, enabled, hidden, type ViewScopeImpl } from '@core/primitives/view-scopes/api';
import { scopes } from '@core/primitives/view-scopes/browser';
import { useViewScope, ViewScopeInstanceProvider } from '@core/primitives/view-scopes/react';

type RuntimeModalEntry = {
  // The catalog erases each component's props at this renderer boundary.
  // oxlint-disable-next-line typescript/no-explicit-any
  readonly component: React.ComponentType<any>;
  readonly size?: ModalSize;
  readonly position?: ModalPosition;
  readonly ignoreOutsidePressAfterWindowBlur?: boolean;
};

const SIZE_CLASSES: Record<ModalSize, string> = {
  xs: 'sm:max-w-xs',
  sm: 'sm:max-w-sm',
  md: 'sm:max-w-lg',
  lg: 'sm:max-w-2xl',
};

const POSITION_CLASSES: Record<ModalPosition, string> = {
  center: 'top-1/2 -translate-y-1/2',
  top: 'top-[15%] translate-y-0',
};

export const ModalRenderer = observer(function ModalRenderer() {
  // Restore focus to the element captured when the first modal in a flow opens.
  useEffect(
    () =>
      reaction(
        () => modalStore.isOpen,
        (isOpen) => {
          if (!isOpen) {
            const el = modalStore.consumePreviousFocus();
            if (!el) return;
            requestAnimationFrame(() => {
              if (el.isConnected) el.focus();
            });
          }
        }
      ),
    []
  );

  const topEntry = modalStore.topEntry;

  return (
    <>
      {modalStore.stack.map((entry) => (
        <ModalDialog key={entry.key} entry={entry} isTop={entry.key === topEntry?.key} />
      ))}
    </>
  );
});

const ModalDialog = observer(function ModalDialog({
  entry,
  isTop,
}: {
  entry: ModalStackEntry;
  isTop: boolean;
}) {
  const runtimeEntry = modalCatalog.byId(entry.id) as RuntimeModalEntry | undefined;
  const Component = runtimeEntry?.component;
  const ignoreNextOutsidePressRef = useRef(false);
  const implementation = {
    'modal.close': () => ({
      availability: () =>
        entry.closeGuardActive ? disabled('This dialog cannot be closed yet') : enabled,
      execute: () => modalStore.dismissEntry(entry.key, 'passive'),
    }),
    'app.confirm': () => ({
      availability: () => (confirmRegistry.current?.isEnabled() ? enabled : hidden),
      execute: () => confirmRegistry.current?.trigger(),
    }),
  } satisfies ViewScopeImpl<typeof modalScope>;
  const { attachRef, instance } = useViewScope(modalScope(), implementation);

  // Activate the capture explicitly: the focus-based activation races the
  // data-view-scope attribute (Base UI moves initial focus before the second
  // render stamps it), leaving Escape dead until a click inside the popup.
  // Every mounted entry stays in the capture order so closing the top modal
  // reveals the one beneath without replacing the underlying logical scope.
  useLayoutEffect(() => {
    if (!instance) return;
    return scopes.activateCapture(instance);
  }, [instance]);

  const completeModal = useCallback(
    (result: unknown) => modalStore.completeEntry(entry.key, result),
    [entry.key]
  );
  const dismissModal = useCallback(() => modalStore.dismissEntry(entry.key), [entry.key]);
  const setCloseGuard = useCallback(
    (active: boolean) => modalStore.setEntryCloseGuard(entry.key, active),
    [entry.key]
  );
  const hasActiveCloseGuard = entry.closeGuardActive;
  const hostController = useMemo<ModalHostController>(
    () => ({
      complete: completeModal,
      dismiss: dismissModal,
      setCloseGuard,
      hasActiveCloseGuard,
    }),
    [completeModal, dismissModal, hasActiveCloseGuard, setCloseGuard]
  );

  useEffect(() => {
    ignoreNextOutsidePressRef.current = false;
  }, [entry.key]);

  useEffect(() => {
    const handleWindowBlur = () => {
      if (isTop && runtimeEntry?.ignoreOutsidePressAfterWindowBlur) {
        ignoreNextOutsidePressRef.current = true;
      }
    };

    window.addEventListener('blur', handleWindowBlur);
    return () => window.removeEventListener('blur', handleWindowBlur);
  }, [isTop, runtimeEntry?.ignoreOutsidePressAfterWindowBlur]);

  const handleOpenChange = (
    open: boolean,
    eventDetails: DialogPrimitive.Root.ChangeEventDetails
  ) => {
    if (!isTop || open || entry.closing) return;
    if (eventDetails.reason === 'escape-key') return;
    const isOutsidePress = eventDetails.reason === 'outside-press';
    if (
      isOutsidePress &&
      runtimeEntry?.ignoreOutsidePressAfterWindowBlur &&
      ignoreNextOutsidePressRef.current
    ) {
      ignoreNextOutsidePressRef.current = false;
      return;
    }

    if (entry.closeGuardActive && isOutsidePress) return;
    ignoreNextOutsidePressRef.current = false;
    modalStore.dismissEntry(entry.key, 'passive');
  };

  const handleOpenChangeComplete = (open: boolean) => {
    if (!open) modalStore.removeEntry(entry.key);
  };

  const popupRef = useRef<HTMLDivElement>(null);
  const attachPopupRef = useCallback(
    (element: HTMLDivElement | null) => {
      popupRef.current = element;
      attachRef(element);
    },
    [attachRef]
  );

  const initialFocus = useCallback(() => {
    const target = popupRef.current?.querySelector<HTMLElement>('[data-autofocus]');
    if (!target) return true;
    if (target instanceof HTMLInputElement || target instanceof HTMLTextAreaElement) {
      requestAnimationFrame(() => target.select());
    }
    return target;
  }, []);

  if (!Component || !runtimeEntry) return null;

  return (
    <Dialog.Root
      open={!entry.closing}
      onOpenChange={handleOpenChange}
      onOpenChangeComplete={handleOpenChangeComplete}
    >
      <Dialog.Portal>
        <Dialog.Overlay />
        <DialogPrimitive.Popup
          ref={attachPopupRef}
          finalFocus={false}
          initialFocus={initialFocus}
          data-slot="dialog-content"
          onPointerDownCapture={() => {
            if (runtimeEntry.ignoreOutsidePressAfterWindowBlur) {
              ignoreNextOutsidePressRef.current = false;
            }
          }}
          className={cn(
            'surface-elevated fixed left-1/2 z-50 flex max-h-[calc(100dvh-2rem)] w-full max-w-[calc(100%-2rem)] -translate-x-1/2 flex-col overflow-hidden rounded-xl bg-(--em-surface) text-sm ring-1 ring-foreground/10 duration-100 outline-none data-open:animate-in data-open:fade-in-0 data-open:zoom-in-95 data-closed:animate-out data-closed:fade-out-0 data-closed:zoom-out-95',
            POSITION_CLASSES[runtimeEntry.position ?? 'center'],
            SIZE_CLASSES[runtimeEntry.size ?? 'md']
          )}
        >
          <ViewScopeInstanceProvider instance={instance}>
            <ModalHostContext.Provider value={{ id: entry.id, controller: hostController }}>
              <Component {...entry.args} />
            </ModalHostContext.Provider>
          </ViewScopeInstanceProvider>
        </DialogPrimitive.Popup>
      </Dialog.Portal>
    </Dialog.Root>
  );
});
