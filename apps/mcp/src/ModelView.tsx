import { useCallback, useEffect, useMemo, useRef, useState, useSyncExternalStore } from 'react';
import { ArrowLeft, FileText } from 'lucide-react';
import { createCadClient } from '@text-to-cad/core/client';
import { unavailablePromptContext, type ResourceRef } from '@text-to-cad/core/prompt';
import { FileViewer } from '@text-to-cad/ui/file-viewer';
import { EmptyCadBackdrop } from '@text-to-cad/ui/file-viewer/empty';
import { MissingFileAlert, ViewerLoadingOverlay } from '@text-to-cad/ui/file-viewer/presentation';
import type { ViewerHost } from '@text-to-cad/ui/host';
import { EmptyState } from '@text-to-cad/ui/navigation';
import { Button } from '@text-to-cad/ui/primitives/button';
import { createDxfRenderer } from '@text-to-cad/ui/renderers/dxf';
import { createGlbRenderer } from '@text-to-cad/ui/renderers/glb';
import { createMeshRenderer } from '@text-to-cad/ui/renderers/mesh';
import { createRobotRenderer } from '@text-to-cad/ui/renderers/robot';
import { createStepRenderer } from '@text-to-cad/ui/renderers/step';
import { useTabViewerState, type TabStore } from '@text-to-cad/ui/tab-store';
import type { Bridge } from './host/bridge';
import { frameClipboard } from './host/clipboard';
import { absolutePath, catalogPath, createCatalogSource, createFileActions, relativePath } from './host/files';
import { scaledPng, type LiveRegistry } from './host/live';
import { createComposerPromptContext } from './host/prompt';
import type { Launch, Root, Server } from './host/server';
import { createTunnelFetch, encodeBase64, TUNNEL_ORIGIN } from './host/tunnel';

export interface ViewReporter {
  /** This view now shows `model` (absolute), or nothing; `resolvePath` turns its references into paths. */
  showing(model: string | null, resolvePath: (resource: ResourceRef) => string): void;
}

/**
 * One model, one root: the shared FileViewer over this host. Everything differs by data --
 * the root it browses, whether it browses at all, where Add to prompt goes -- never by where
 * the view is.
 */
export default function ModelView({ launch, root: launchedRoot, sequence, bridge, server, tabStore, live, colorScheme, platform, reporter, onHome, compact = false, composer = true }: {
  launch: Launch; root: Root; sequence: number; bridge: Bridge; server: Server; tabStore: TabStore; live: LiveRegistry;
  colorScheme: 'light' | 'dark'; platform: string; reporter: ViewReporter; onHome?: () => void;
  /** Shown small, inline in the chat: the renderer draws the model, not its tools. */
  compact?: boolean;
  /** Add to prompt reaches the host's composer; without one, the viewer offers no prompt action. */
  composer?: boolean;
}) {
  // Every launch carries its own root object; the same folder must keep its client and catalog.
  const root = useMemo(() => launchedRoot, [launchedRoot.kind, launchedRoot.path]);
  const client = useMemo(() => createCadClient({
    origin: TUNNEL_ORIGIN, fetch: createTunnelFetch(server, root),
    shouldPoll: () => document.visibilityState !== 'hidden',
  }), [server, root]);
  useEffect(() => () => client.dispose(), [client]);
  const sourceId = `local-fs:${root.path}`;
  const source = useMemo(() => createCatalogSource(client, root, { id: sourceId, explore: launch.explore }), [client, root, sourceId, launch.explore]);
  const resolvePath = useCallback((resource: ResourceRef) => {
    if (resource.kind === 'url') return resource.url;
    if (resource.workspaceId !== sourceId) throw new Error('This reference belongs to another folder.');
    return absolutePath(root, resource.path);
  }, [root, sourceId]);
  const composerContext = useMemo(() => composer ? createComposerPromptContext(bridge, { resolvePath }) : null, [composer, bridge, resolvePath]);
  useEffect(() => () => composerContext?.dispose(), [composerContext]);
  const promptContext = composerContext ?? unavailablePromptContext;
  const fileActions = useMemo(() => createFileActions(root, frameClipboard, platform), [root, platform]);
  const preferences = tabStore.settings;
  const renderers = useMemo(() => [
    createStepRenderer({ client, preferences, live: live.binding }),
    createDxfRenderer({ client, preferences, live: live.binding }),
    createGlbRenderer({ client, preferences, live: live.binding }),
    createMeshRenderer({ client, preferences, live: live.binding }),
    createRobotRenderer({ client, preferences, live: live.binding }),
  ], [client, preferences, live]);
  const catalog = useSyncExternalStore(client.subscribe, client.getSnapshot, client.getSnapshot);
  const { state, onStateChange, setPanel } = useTabViewerState(tabStore, source.id);

  // The file on screen, as the catalog names it (relative to the root).
  const [file, setFile] = useState(() => (launch.model && relativePath(root, launch.model)) || '');
  useEffect(() => { setFile((launch.model && relativePath(root, launch.model)) || ''); }, [launch, root, sequence]);
  const model = file ? absolutePath(root, file) : null;
  useEffect(() => { reporter.showing(model, resolvePath); }, [reporter, model, resolvePath]);
  useEffect(() => {
    const refresh = () => { if (document.visibilityState !== 'hidden') void client.refresh({ markRefreshing: false }).catch(() => {}); };
    document.addEventListener('visibilitychange', refresh);
    return () => document.removeEventListener('visibilitychange', refresh);
  }, [client]);
  useThumbnail(server, live, model);

  const open = useCallback((path: string, options?: { panel?: string }) => {
    const entry = client.getSnapshot().entries.find(candidate => catalogPath(candidate) === path);
    if (!entry) return;
    setFile(catalogPath(entry));
    setPanel(options?.panel ?? null);
  }, [client, setPanel]);
  const host = useMemo<ViewerHost>(() => ({
    files: source, fileActions, clipboard: frameClipboard, promptContext,
    navigation: { openFile: open }, environment: compact ? { colorScheme, platform, compact } : { colorScheme, platform },
  }), [source, fileActions, promptContext, open, colorScheme, platform, compact]);

  const selected = catalog.entries.find(entry => catalogPath(entry) === file);
  const navigationPath = !launch.explore ? null : selected ? catalogPath(selected) : catalog.hydrated ? file || null : null;
  const empty = <div className="pointer-events-auto absolute inset-0 z-10 bg-background">
    <EmptyState icon={FileText} title="No model open" description={launch.explore ? 'Pick one from the files, or ask the agent to show one.' : 'Ask the agent to show a model.'} />
  </div>;
  const leading = onHome ? <Button variant="ghost" size="icon-sm" aria-label="Back to CAD home" onClick={onHome}><ArrowLeft aria-hidden="true" /></Button> : undefined;
  return <FileViewer file={file || null} host={host} renderers={renderers} state={state} onStateChange={onStateChange}
    leading={leading} navigationPath={navigationPath} onError={error => console.error(error)}
    presentation={{
      empty: <div className="relative h-full">{empty}</div>,
      loading: <div className="relative h-full"><ViewerLoadingOverlay viewerLoading /></div>,
      error: () => <div className="relative h-full">{catalog.error ? empty : <EmptyCadBackdrop colorScheme={colorScheme}><MissingFileAlert missingFileRef={file} rootPath={root.path} /></EmptyCadBackdrop>}</div>,
    }} />;
}

/** Keep a small picture of each model this view shows, for the home page's recents. */
function useThumbnail(server: Server, live: LiveRegistry, model: string | null) {
  const taken = useRef(new Set<string>());
  const controller = useSyncExternalStore(live.subscribe, live.current, live.current);
  useEffect(() => {
    if (!controller || !model || taken.current.has(model)) return;
    let cancelled = false;
    const attempt = async (tries: number) => {
      if (cancelled) return;
      const state = controller.readState();
      if (state.loading || state.active === false) {
        if (tries > 0) setTimeout(() => void attempt(tries - 1), 750);
        return;
      }
      taken.current.add(model);
      try {
        const png = await scaledPng(await controller.capture(), 360);
        if (!cancelled) await server.recents({ action: 'thumbnail', path: model, png: encodeBase64(new Uint8Array(await png.arrayBuffer())) });
      } catch { /* a thumbnail is a nicety */ }
    };
    const timer = setTimeout(() => void attempt(40), 1500);
    return () => { cancelled = true; clearTimeout(timer); };
  }, [controller, model, server]);
}

