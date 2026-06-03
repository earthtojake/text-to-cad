import {
  COLOR_SCHEME_STORAGE_KEY,
  THEME_STORAGE_KEY
} from "../ui/colorScheme.js";
import {
  FILE_SESSION_STORAGE_KEY_PREFIX
} from "./fileSessionState.js";

export const CAD_DIRECTORY_STORAGE_EVENT_ACTION = Object.freeze({
  COLOR_SCHEME: "colorScheme",
  THEME: "theme",
  IGNORE: "ignore"
});

export function cadDirectoryStorageEventAction(key) {
  const storageKey = String(key || "");
  if (!storageKey || storageKey.startsWith(FILE_SESSION_STORAGE_KEY_PREFIX)) {
    return CAD_DIRECTORY_STORAGE_EVENT_ACTION.IGNORE;
  }
  if (storageKey === COLOR_SCHEME_STORAGE_KEY) {
    return CAD_DIRECTORY_STORAGE_EVENT_ACTION.COLOR_SCHEME;
  }
  if (storageKey === THEME_STORAGE_KEY) {
    return CAD_DIRECTORY_STORAGE_EVENT_ACTION.THEME;
  }
  return CAD_DIRECTORY_STORAGE_EVENT_ACTION.IGNORE;
}
