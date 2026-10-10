import { useCallback, useEffect, useMemo, useRef } from "react";
import { normalizeToolStack } from "../tools/toolStackLayout.js";
import { fileViewsEqual } from "./fileView.js";
import { attachLiveBinding } from "./liveBinding.js";

// What every view's frame does for its host that is not about what it draws, one hook each, shared
// by the 3D views' shell (`useRendererShell.js`) and the flat pictures' (`usePlaneShell.js`).

const VIEW_SAVE_DELAY_MS = 180;

/**
 * The file's view (`fileView.js`), written through the host soon after a change (`schedule`) and
 * once more as the view unmounts, and never after: a host that drops the view of a file it left
 * must not see it written again by a change that lands later. A record equal to the last written is
 * not written again.
 *
 * @param {{ onStateChange?: (record: object) => void, record: () => object, written?: object | null }} options
 *   `record` is read when the view is written, never at render. `written`: the record the host
 *   already holds, which is not written back to it unchanged.
 * @returns {{ schedule: () => void, flush: () => void }}
 */
export function useFileViewWriter({ onStateChange, record, written = null }) {
  const onStateChangeRef = useRef(onStateChange);
  onStateChangeRef.current = onStateChange;
  const recordRef = useRef(record);
  recordRef.current = record;
  const writtenRef = useRef(written);
  const timer = useRef(0);
  const closed = useRef(false);
  const flush = useCallback(() => {
    window.clearTimeout(timer.current);
    timer.current = 0;
    if (closed.current) return;
    const next = recordRef.current();
    if (fileViewsEqual(writtenRef.current, next)) return;
    writtenRef.current = next;
    onStateChangeRef.current?.(next);
  }, []);
  const schedule = useCallback(() => {
    if (closed.current) return;
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(flush, VIEW_SAVE_DELAY_MS);
  }, [flush]);
  useEffect(() => {
    closed.current = false;
    return () => { flush(); closed.current = true; };
  }, [flush]);
  return useMemo(() => ({ schedule, flush }), [schedule, flush]);
}

/**
 * The tool stack's layout, the tab's (`services.preferences.toolStack`): the sizes of the panels a
 * person can size, the folded panels, the closed tree. A change is a patch over the layout as it last
 * stood (or a function of it), so two panels written back in one turn both land.
 *
 * @param {{ preferences?: { toolStack?: object }, onPreferenceChange(patch: object): void }} services
 */
export function useToolStackLayout(services) {
  const toolStack = useMemo(() => normalizeToolStack(services.preferences?.toolStack), [services.preferences?.toolStack]);
  const toolStackRef = useRef(toolStack);
  toolStackRef.current = toolStack;
  const { onPreferenceChange } = services;
  const changeToolStack = useCallback((patch) => {
    const next = normalizeToolStack({ ...toolStackRef.current, ...(typeof patch === "function" ? patch(toolStackRef.current) : patch) });
    toolStackRef.current = next;
    onPreferenceChange({ toolStack: next });
  }, [onPreferenceChange]);
  return { toolStack, changeToolStack };
}

/**
 * A host's own capture request (`services.captureRequest`) is the view's snapshot, acknowledged,
 * once per request, as soon as the view is `ready` for it.
 *
 * @param {{ services: { captureRequest?: { key: string | number } | null, acknowledgeCommand?: (kind: string, key: string | number) => void },
 *   ready: boolean, capture: () => void }} options
 */
export function useCaptureRequest({ services, ready, capture }) {
  const captureRef = useRef(capture);
  captureRef.current = capture;
  const key = services.captureRequest?.key ?? null;
  const applied = useRef(null);
  const { acknowledgeCommand } = services;
  useEffect(() => {
    if (key === null || applied.current === key || !ready) return;
    applied.current = key;
    acknowledgeCommand?.("captureRequest", key);
    captureRef.current();
  }, [key, ready, acknowledgeCommand]);
}

/**
 * The live command surface (`liveBinding.ts`), attached while the host hands a binding over: the
 * runtime is read when a command arrives, never at render.
 *
 * @param {{ binding?: object | null, runtime: { current: object }, commands?: string[], declined?: Record<string, string>,
 *   ready: () => Promise<void> }} options
 *   `commands`: the names this view adds. `declined`: the host commands it answers in words. A new set
 *   of names attaches again.
 */
export function useLiveSurface({ binding, runtime, commands = [], declined = {}, ready }) {
  const names = [...commands].sort().join("\n");
  const declinedRef = useRef(declined);
  declinedRef.current = declined;
  useEffect(() => {
    if (!binding) return undefined;
    return attachLiveBinding(binding, () => runtime.current, {
      commands: names ? names.split("\n") : [], declined: declinedRef.current || {}, ready
    });
  }, [binding, names, ready, runtime]);
}
