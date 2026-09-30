import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { createCadClient } from '@text-to-cad/core/client';
import { unavailablePromptContext, type ResourceRef } from '@text-to-cad/core/prompt';
import { CadViewer, createCadFileActions, createCatalogFileSource, normalizeCatalogPath, pathUnderRoot, referencePath, rootPath } from '@text-to-cad/ui/cad-viewer';
import type { ViewerHost, ViewerLinks } from '@text-to-cad/ui/host';
import type { ModelLibrarySource } from '@text-to-cad/ui/library';
import type { TabStore } from '@text-to-cad/ui/tab-store';
import type { Bridge } from './host/bridge';
import { frameClipboard } from './host/clipboard';
import { createFilesystemSource } from './host/files';
import type { LiveRegistry } from './host/live';
import { createComposerPromptContext } from './host/prompt';
import type { Launch, Root, Server } from './host/server';
import { createTunnelFetch, encodeBase64, TUNNEL_ORIGIN } from './host/tunnel';

export interface ViewReporter {
  /** This view now shows `model` (absolute), or nothing; `resolvePath` turns its references into paths. */
  showing(model: string | null, resolvePath: (resource: ResourceRef) => string): void;
}

/**
 * One root's view: the shared CAD viewer over this host — the model a launch names, or with none,
 * the home (the library, and the root's explorer where the launch browses). Everything differs by
 * data — the root it browses, whether it browses at all, where Add to prompt goes — never by where
 * the view is.
 */
export default function ModelView({ launch, root: launchedRoot, sequence, bridge, server, tabStore, live, links, colorScheme, platform, reporter, onLaunch, onHome, compact = false, composer = true }: {
  launch: Launch; root: Root; sequence: number; bridge: Bridge; server: Server; tabStore: TabStore; live: LiveRegistry; links: ViewerLinks;
  colorScheme: 'light' | 'dark'; platform: string; reporter: ViewReporter;
  /** Show what the server launched: a model, possibly under another root. */
  onLaunch(launch: Launch): void;
  /** Show this view's home. */
  onHome(): void;
  /** Shown small, inline in the chat: the renderer draws the model, not its tools. */
  compact?: boolean;
  /** Add to prompt reaches the host's composer; without one, the viewer offers no prompt action. */
  composer?: boolean;
}) {
  // Every launch carries its own root object; the same folder must keep its client and catalog.
  const root = useMemo(() => launchedRoot, [launchedRoot.kind, launchedRoot.path]);
  const tunnel = useMemo(() => createTunnelFetch(server, root), [server, root]);
  const client = useMemo(() => createCadClient({
    origin: TUNNEL_ORIGIN, fetch: tunnel,
    shouldPoll: () => document.visibilityState !== 'hidden',
  }), [tunnel]);
  useEffect(() => () => client.dispose(), [client]);
  const sourceId = `local-fs:${root.path}`;
  const global = root.kind === 'global';
  // The file on screen, as the root names it; '' is the home.
  const launched = () => (launch.model && pathUnderRoot(root.path, launch.model)) || '';
  const [file, setFile] = useState(launched);
  const showing = useRef(file);
  showing.current = file;
  // A project browses its catalog; a filesystem is read a folder at a time.
  const source = useMemo(() => global
    ? createFilesystemSource(client, root, tunnel, { id: sourceId, explore: launch.explore, showing: () => showing.current || null })
    : createCatalogFileSource(client, { id: sourceId, rootName: root.name, browse: launch.explore }), [client, root, tunnel, sourceId, launch.explore, global]);
  const resolvePath = useCallback((resource: ResourceRef) => referencePath(resource, { workspaceId: sourceId, root: root.path }), [root, sourceId]);
  const composerContext = useMemo(() => composer ? createComposerPromptContext(bridge, { resolvePath }) : null, [composer, bridge, resolvePath]);
  useEffect(() => () => composerContext?.dispose(), [composerContext]);
  const promptContext = composerContext ?? unavailablePromptContext;
  // The file menu: its paths, and Reveal in the desktop's file manager (the server is on this machine).
  const fileActions = useMemo(() => createCadFileActions({
    root: root.path, platform, clipboard: frameClipboard,
    // A path relative to a whole filesystem is its absolute path, less the first slash.
    relative: !global,
    reveal: path => server.reveal(root, path),
  }), [root, platform, server, global]);

  useEffect(() => { setFile(launched()); }, [launch, root, sequence]);
  const model = file ? rootPath(root.path, file) : null;
  useEffect(() => { reporter.showing(model, resolvePath); }, [reporter, model, resolvePath]);

  const opened = useRef(onLaunch);
  opened.current = onLaunch;
  // The models opened before, from every view and the web viewer; Open Model picks one from disk
  // with the desktop's chooser. Opening switches this same view to the model.
  const library = useMemo<ModelLibrarySource>(() => ({
    list: () => server.recents(),
    change: (action, entry) => server.recents({ action, path: entry.path }),
    thumbnail: name => server.thumbnails([name]).then(found => found[name] ? `data:image/png;base64,${found[name]}` : null),
    open: entry => server.launch(entry.path).then(next => opened.current(next)),
    pick: () => server.pickModel().then(result => { if (result.launch) opened.current(result.launch); }),
  }), [server]);
  const home = useRef(onHome);
  home.current = onHome;
  // Showing another file: from the home, the server launches it (and remembers it, and says which
  // root it is under); from a model, it is this root's, shown in place.
  const show = useCallback((next: string) => {
    if (!next) { home.current(); return; }
    if (!showing.current) { void server.launch(rootPath(root.path, next)).then(launchedModel => opened.current(launchedModel), error => console.error(error)); return; }
    setFile(next);
  }, [server, root]);
  const host = useMemo<Omit<ViewerHost, 'navigation'>>(() => ({
    files: source, fileActions, clipboard: frameClipboard, promptContext, links,
    environment: compact ? { colorScheme, platform, compact } : { colorScheme, platform },
  }), [source, fileActions, promptContext, links, colorScheme, platform, compact]);

  return <CadViewer client={client} host={host} tabStore={tabStore} live={live} file={file} onShow={show}
    // A filesystem's catalog holds only the file on screen: what its explorer lists is the filesystem's.
    accept={global ? path => normalizeCatalogPath(path) || null : undefined}
    rootPath={root.path} library={library}
    onThumbnail={async (png, pictured) => server.recents({ action: 'thumbnail', path: rootPath(root.path, pictured), png: encodeBase64(new Uint8Array(await png.arrayBuffer())) })} />;
}
