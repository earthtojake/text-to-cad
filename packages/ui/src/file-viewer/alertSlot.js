import { createContext, useContext } from "react";

// The viewer shows one alert card at a time. A file's own card (`renderers/kit/status/ViewerAlertCard.jsx`, drawn by the
// view, its dismissal `useAlertDismissal`) says it is on screen here, and the file viewer (`FileViewer.tsx`) holds a
// host's card (a failed update's) back while it is: the file's wins, and the host's waits behind it. Outside a file
// viewer nothing listens.
//
// Importing this module has no environmental effects.

/**
 * Says a file's card is on screen: called as it shows, it returns the call that says it has gone.
 * @type {import("react").Context<(() => () => void) | null>}
 */
export const ViewerAlertSlotContext = createContext(/** @type {(() => () => void) | null} */ (null));

/** The file viewer's ear for a file's card, or null where there is none. */
export const useViewerAlertSlot = () => useContext(ViewerAlertSlotContext);
