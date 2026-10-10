import { useCallback, useEffect, useMemo, useRef, useState, useSyncExternalStore, type CSSProperties } from 'react';
import { unavailablePromptContext } from '@text-to-cad/core/prompt';
import type { CadWorkspaceService } from '@text-to-cad/core/client';
import { FileViewer } from '../file-viewer/FileViewer.js';
import type { FileViewerState } from '../file-viewer/types.js';
import { createLiveRegistry, type LiveRegistry } from '../host/liveRegistry.js';
import type { ViewerHost } from '../host/types.js';
import { THUMBNAIL_SIZE } from '../library/thumbnails.js';
import { createDxfRenderer } from '../renderers/dxf/index.js';
import { createGlbRenderer } from '../renderers/glb/index.js';
import { createMeshRenderer } from '../renderers/mesh/index.js';
import { createPlotRenderer } from '../renderers/plot/index.js';
import { createRobotRenderer } from '../renderers/robot/index.js';
import { createStepRenderer } from '../renderers/step/index.js';
import type { CadPreferenceSource } from '../renderers/workspace/index.js';
import { createCadFileSource } from './catalog.js';

/** The six CAD renderers over one client, reading the tab's preferences, bound to one live registry. */
export function cadRenderers(client: CadWorkspaceService, preferences: CadPreferenceSource, live: LiveRegistry['binding']) {
  return [
    createStepRenderer({ client, preferences, live }),
    createDxfRenderer({ client, preferences, live }),
    createPlotRenderer({ client, preferences, live }),
    createGlbRenderer({ client, preferences, live }),
    createMeshRenderer({ client, preferences, live }),
    createRobotRenderer({ client, preferences, live }),
  ];
}

/** A model to picture: the client that reads it, its absolute path, and where its picture is kept. */
export interface ModelPictureSource {
  client: CadWorkspaceService;
  file: string;
  keep(png: Blob): Promise<unknown>;
}

// Out of sight: behind the page and invisible, at the picture's own size, so the view draws as it
// would on screen and nothing of it is seen or reached.
const OUT_OF_SIGHT: CSSProperties = {
  position: 'fixed', left: 0, top: 0, width: THUMBNAIL_SIZE.width, height: THUMBNAIL_SIZE.height,
  opacity: 0, pointerEvents: 'none', zIndex: -1, overflow: 'hidden',
};
const NOT_SAVED: FileViewerState = {};
// A model that has not settled by then is not a cheap one to picture: it keeps its placeholder.
const SETTLE_WITHIN_MS = 30_000;

/**
 * A model drawn out of sight for its library card: a viewer of its own — its own renderers over the
 * model's client, its own live binding (never the host's, which an agent reads), no chrome, nothing
 * of its state kept — whose picture is taken once the view settles, as a view on screen pictures
 * its file (`useModelThumbnail`), and kept where the source says. `onDone` hears whether it was.
 */
export function OffscreenPicture({ source, host, preferences, onDone }: {
  source: ModelPictureSource;
  host: Pick<ViewerHost, 'clipboard' | 'environment'>;
  preferences: CadPreferenceSource;
  onDone(kept: boolean): void;
}) {
  const live = useMemo(() => createLiveRegistry(), []);
  const renderers = useMemo(() => cadRenderers(source.client, preferences, live.binding), [source.client, preferences, live]);
  const files = useMemo(() => createCadFileSource(source.client, { id: `picture:${source.file}` }), [source]);
  const viewerHost = useMemo<ViewerHost>(() => ({
    files, clipboard: host.clipboard, promptContext: unavailablePromptContext, navigation: { openFile() {} },
    environment: { ...host.environment, compact: true },
  }), [files, host.clipboard, host.environment]);
  const [state, setState] = useState(NOT_SAVED);
  const finished = useRef(false);
  const latest = useRef(onDone);
  latest.current = onDone;
  const finish = useCallback((kept: boolean) => {
    if (finished.current) return;
    finished.current = true;
    latest.current(kept);
  }, []);
  const controller = useSyncExternalStore(live.subscribe, live.current, live.current);
  useEffect(() => {
    if (!controller) return undefined;
    let current = true;
    controller.thumbnail(THUMBNAIL_SIZE)
      .then(png => (current ? source.keep(png).then(() => finish(true)) : undefined))
      .catch(() => { if (current) finish(false); });
    return () => { current = false; };
  }, [controller, source, finish]);
  useEffect(() => {
    const timer = setTimeout(() => finish(false), SETTLE_WITHIN_MS);
    return () => clearTimeout(timer);
  }, [finish]);
  return <div aria-hidden="true" inert data-offscreen-picture="" style={OUT_OF_SIGHT}>
    <FileViewer file={source.file} host={viewerHost} renderers={renderers} state={state} onStateChange={setState}
      onError={() => finish(false)} />
  </div>;
}
