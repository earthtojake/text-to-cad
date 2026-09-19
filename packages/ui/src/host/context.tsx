import { createContext, useContext, useSyncExternalStore } from 'react';
import type { RefObject } from 'react';
import type { ViewerHost } from './types.js';

export const ViewerElementContext = createContext<RefObject<HTMLDivElement | null> | null>(null);
export const ViewerHostContext = createContext<ViewerHost | null>(null);
export function useViewerHost(): ViewerHost {
  const host = useContext(ViewerHostContext);
  if (!host) throw new Error('FileViewer requires an explicit ViewerHost. Supply file, clipboard and prompt services from the app.');
  return host;
}
export function usePromptDestination() {
  const { promptContext } = useViewerHost();
  return useSyncExternalStore(promptContext.subscribe, promptContext.getSnapshot, promptContext.getSnapshot);
}
