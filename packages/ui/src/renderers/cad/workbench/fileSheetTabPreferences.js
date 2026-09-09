import { createContext, useContext } from 'react';

// Persistence is injected. Each sheet keeps the original per-mount arrangement.
export const FileSheetTabPreferencesContext = createContext({ store: {}, update() {} });
export const useFileSheetTabPreferences = () => useContext(FileSheetTabPreferencesContext);
