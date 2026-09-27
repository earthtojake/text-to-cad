import { createContext, useCallback, useContext, useLayoutEffect, useState } from "react";

// Measure the complete file surface, not the scene left after a sidebar opens.
export const VIEWER_MOBILE_BREAKPOINT = 720;
export const ViewerMobileContext = createContext(false);
export const useViewerMobile = () => useContext(ViewerMobileContext);

/**
 * Whether the element is narrower than the viewer breakpoint, through a `ResizeObserver`:
 * the one fact about its width the viewer lays out on. It changes state only when it
 * crosses the breakpoint, so a window resize or a panel drag does not re-render what the
 * element contains. `false` until the first measurement.
 *
 * Returns a callback ref: the element is often not in the first render.
 * @returns {[(element: HTMLElement | null) => void, boolean]}
 */
export function useViewerMobileMeasure() {
  const [element, setElement] = useState(null);
  const [mobile, setMobile] = useState(false);
  const ref = useCallback(next => setElement(next), []);
  useLayoutEffect(() => {
    if (!element) return undefined;
    const measure = () => {
      const width = element.getBoundingClientRect().width;
      setMobile(width > 0 && width < VIEWER_MOBILE_BREAKPOINT);
    };
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    return () => observer.disconnect();
  }, [element]);
  return [ref, mobile];
}
