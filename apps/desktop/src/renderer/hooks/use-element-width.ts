import { useCallback, useLayoutEffect, useState } from "react";

/**
 * The width of an element, kept current through a `ResizeObserver`.
 *
 * Panes here are resized by drag handles, not by the window, so `resize`
 * events say nothing; the element is the only thing that knows its own
 * width. `0` until the first measurement — a caller that lays out on the
 * number should treat zero as "not yet".
 *
 * Returns a callback ref rather than taking a ref object: the element it
 * measures is often not in the first render (a spinner comes first), and an
 * effect keyed on a ref object never sees the element arrive.
 */
export function useElementWidth(): [ref: (element: HTMLElement | null) => void, width: number] {
  const [element, setElement] = useState<HTMLElement | null>(null);
  const [width, setWidth] = useState(0);
  const ref = useCallback((next: HTMLElement | null) => setElement(next), []);

  useLayoutEffect(() => {
    if (!element) {
      return;
    }
    const measure = () => {
      const next = Math.round(element.getBoundingClientRect().width);
      setWidth((current) => (current === next ? current : next));
    };
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    return () => observer.disconnect();
  }, [element]);

  return [ref, width];
}
