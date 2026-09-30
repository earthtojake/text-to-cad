import { useCallback, useEffect, useRef } from "react";

/**
 * The view's "tell me once you have settled", for whatever waits on it (a library card's picture).
 *
 * `whenSettled()` resolves once `settled()` is true: at once when it already is, otherwise after the
 * render that makes it so. It is never a timer: the renderer's own state says when the file is
 * whole and drawn, and every change to that state is a render of the component calling this. A
 * view that unmounts first rejects whatever still waits.
 *
 * @param {() => boolean} settled Read after each render, and only while something waits.
 * @returns {() => Promise<void>}
 */
export function useWhenSettled(settled) {
  const check = useRef(settled);
  check.current = settled;
  const waiters = useRef([]);
  useEffect(() => {
    if (waiters.current.length === 0 || !check.current()) return;
    for (const waiter of waiters.current.splice(0)) waiter.resolve();
  });
  useEffect(() => () => {
    for (const waiter of waiters.current.splice(0)) waiter.reject(new Error("This viewer is inactive."));
  }, []);
  return useCallback(() => new Promise((resolve, reject) => {
    if (check.current()) resolve();
    else waiters.current.push({ resolve, reject });
  }), []);
}
