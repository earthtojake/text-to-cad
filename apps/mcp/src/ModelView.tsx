import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { createHttpAttachmentStore } from '@text-to-cad/core/client';
import { unavailablePromptContext, type ResourceRef } from '@text-to-cad/core/prompt';
import { CadViewer, createCadFileActions, createCadFileSource, normalizePath } from '@text-to-cad/ui/cad-viewer';
import type { AppSetting, ViewerFeatures } from '@text-to-cad/ui/file-viewer';
import type { ViewerHost, ViewerLinks } from '@text-to-cad/ui/host';
import type { ModelLibrarySource } from '@text-to-cad/ui/library';
import type { TabStore } from '@text-to-cad/ui/tab-store';
import type { Bridge } from './host/bridge';
import { frameClipboard } from './host/clipboard';
import type { LiveRegistry } from './host/live';
import { createChatPromptContext, type ChatReach } from './host/prompt';
import type { Launch, Server } from './host/server';
import type { ViewSync } from './host/sync';
import { createTunnelClient, createTunnelFetch, encodeBase64, TUNNEL_ORIGIN } from './host/tunnel';

export interface ViewReporter {
  /** This view now shows `model` (absolute), or nothing; `resolvePath` turns its references into paths. */
  showing(model: string | null, resolvePath: (resource: ResourceRef) => string): void;
}

// A reference names a file by its absolute path, a URL as it is.
const resolvePath = (resource: ResourceRef) => resource.kind === 'url' ? resource.url : resource.path;

/**
 * One view: the shared CAD viewer over this host — the model a launch names, by its absolute path,
 * or with none, the home (the library, and Open). A view browses from its model's folder. Everything
 * differs by data — what a Quick Edit can do in the chat, whether the view has a home — never by
 * where the view is. Codex's file handler (`surface: file`) shows its file alone: the host's own file
 * tree is its navigation.
 */
export default function ModelView({ launch, sequence, bridge, server, tabStore, live, links, colorScheme, platform, reporter, sync, onLaunch, chat, appSettings, features, notice, update, fullSize }: {
  launch: Launch; sequence: number; bridge: Bridge; server: Server; tabStore: TabStore; live: LiveRegistry; links: ViewerLinks;
  colorScheme: 'light' | 'dark'; platform: string; reporter: ViewReporter;
  /** The view's one call each second: it carries what this view's client would otherwise poll for. */
  sync: ViewSync;
  /** Show what the server launched: a model, or the home. */
  onLaunch(launch: Launch): void;
  /** What the chat takes from a Quick Edit: context for the next message, a message now, or neither (Copy Prompt alone). */
  chat: ChatReach;
  /** This app's on/off settings, in the app menu: analytics and Quick edit. */
  appSettings?: readonly AppSetting[];
  /** The features the person left on (in the app menu): Quick edit. */
  features?: ViewerFeatures;
  /** The analytics question, which the viewer asks once a model is on screen. */
  notice?: ReactNode;
  /** The update button, first in the navbar and on the home, while this install is behind. */
  update?: ReactNode;
  /** Inline, the card's way to full size, where the host can show it so: last in the navbar and on the home. */
  fullSize?: ReactNode;
}) {
  const tunnel = useMemo(() => createTunnelFetch(server), [server]);
  // The client polls nothing: the view's sync says when the file's catalog entry moved, and carries
  // the build feed of a STEP on screen (a call the view makes each second anyway).
  const client = useMemo(() => createTunnelClient(tunnel, {
    pollIntervalMs: 0, editingPreviewFeed: sync.observePreview,
  }), [tunnel, sync]);
  useEffect(() => () => client.dispose(), [client]);
  // Codex's file handler shows its file alone: the host's own file tree is its navigation, so it
  // has neither the home nor the explorer (a source that cannot list or search offers none).
  const homed = launch.surface !== 'file';
  const source = useMemo(() => {
    const { list, search, ...alone } = createCadFileSource(client);
    return homed ? { ...alone, list, search } : alone;
  }, [client, homed]);
  // The file on screen, by its absolute path; '' is the home.
  const launched = () => normalizePath(launch.model || '');
  const [file, setFile] = useState(launched);
  const showing = useRef(file);
  showing.current = file;
  // A copied prompt's sketch is saved by the server, which is on this machine.
  const attachments = useMemo(() => createHttpAttachmentStore({ origin: TUNNEL_ORIGIN, fetch: tunnel }), [tunnel]);
  const chatContext = useMemo(() => chat.queue || chat.send ? createChatPromptContext(bridge, { resolvePath, reach: chat, attachments }) : null,
    [chat.queue, chat.send, chat.sendImages, bridge, attachments]);
  useEffect(() => () => chatContext?.dispose(), [chatContext]);
  const promptContext = chatContext ?? unavailablePromptContext;
  // The file menu: its path, and Reveal in the desktop's file manager (the server is on this machine).
  const fileActions = useMemo(() => createCadFileActions({ platform, clipboard: frameClipboard, reveal: path => server.reveal(path) }), [platform, server]);

  useEffect(() => { setFile(launched()); }, [launch, sequence]);
  useEffect(() => sync.watch({
    file: () => showing.current || null, revision: () => client.getSnapshot().catalogRevision,
    refresh: next => client.refresh({ ...(next ? { file: next } : {}), markRefreshing: false }),
  }), [sync, client]);
  useEffect(() => { reporter.showing(file || null, resolvePath); }, [reporter, file]);

  const opened = useRef(onLaunch);
  opened.current = onLaunch;
  // Every other view has the home: the models opened before, from every view and the web viewer,
  // and Open with the desktop's chooser where there is one.
  // The home's first list came with its launch: the cards draw at once, and later reads ask.
  const seeded = useRef(launch.recents ?? null);
  const library = useMemo<ModelLibrarySource | undefined>(() => homed ? {
    list: () => {
      const first = seeded.current;
      seeded.current = null;
      return first ? Promise.resolve(first) : server.recents();
    },
    change: (action, entry) => server.recents({ action, path: entry.path }),
    thumbnail: name => server.thumbnails([name]).then(found => found[name] ? `data:image/png;base64,${found[name]}` : null),
    open: entry => server.launch(entry.path).then(next => opened.current(next)),
    ...(launch.pick ? { pick: () => server.pickModel().then(result => { if (result.launch) opened.current(result.launch); }) } : {}),
    // A card without a picture has its model drawn out of sight by this view's own client.
    pictureFrom: entry => ({ client, file: normalizePath(entry.path),
      keep: png => png.arrayBuffer().then(bytes => server.recents({ action: 'thumbnail', path: entry.path, png: encodeBase64(new Uint8Array(bytes)) })) }),
  } : undefined, [server, homed, launch.pick, client]);
  // Showing another file: from the home, the server launches it (and remembers it); from a model,
  // it is shown in place. '' is the home.
  const show = useCallback((next: string) => {
    if (!next) { setFile(''); return; }
    if (!showing.current) { void server.launch(next).then(launchedModel => opened.current(launchedModel), error => console.error(error)); return; }
    setFile(next);
  }, [server]);
  const host = useMemo<Omit<ViewerHost, 'navigation'>>(() => ({
    files: source, fileActions, clipboard: frameClipboard, promptContext, attachments, links,
    environment: { colorScheme, platform },
  }), [source, fileActions, promptContext, attachments, links, colorScheme, platform]);

  return <CadViewer client={client} host={host} tabStore={tabStore} live={live} file={file} onShow={show}
    library={library} appSettings={appSettings} features={features} notice={notice} update={update} fullSize={fullSize}
    onThumbnail={async (png, pictured) => server.recents({ action: 'thumbnail', path: pictured, png: encodeBase64(new Uint8Array(await png.arrayBuffer())) })} />;
}
