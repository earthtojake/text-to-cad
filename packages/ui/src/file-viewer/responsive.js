import { createContext, useContext } from "react";

// Measure the complete file surface, not the scene left after a sidebar opens.
export const VIEWER_MOBILE_BREAKPOINT = 720;
export const ViewerMobileContext = createContext(false);
export const useViewerMobile = () => useContext(ViewerMobileContext);
