// The React half of viewerOrigin.js. Kept apart from the URL helpers so those
// stay importable from plain Node (the unit suite) and from anything that must
// not pull React in.
//
// No JSX here on purpose: this module is loaded directly by `node --test`.
import { createContext, createElement, useContext } from "react";

import { normalizeViewerOrigin } from "./viewerOrigin.js";

const ViewerOriginContext = createContext("");

export function ViewerOriginProvider({ origin = "", children }) {
  return createElement(
    ViewerOriginContext.Provider,
    { value: normalizeViewerOrigin(origin) },
    children,
  );
}

// The origin every backend URL in this subtree is built against. "" — the
// default, and what the standalone viewer always passes — means same origin.
export function useViewerOrigin() {
  return useContext(ViewerOriginContext);
}

export { ViewerOriginContext };
