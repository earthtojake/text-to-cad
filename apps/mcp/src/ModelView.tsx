import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { createHttpPromptFiles, type CadClient } from '@text-to-cad/core/client';
import { unavailablePromptContext } from '@text-to-cad/core/prompt';
import { CadViewer, createCadFileActions, createCadFileSource, normalizePath } from '@text-to-cad/ui/cad-viewer';
import type { AppSetting, ColorSchemeSetting, LanguageSetting } from '@text-to-cad/ui/file-viewer';
import type { ViewerHost, ViewerLinks } from '@text-to-cad/ui/host';
import type { ModelLibrarySource } from '@text-to-cad/ui/library';
import type { TabStore } from '@text-to-cad/ui/tab-store';
import type { Bridge } from './host/bridge';
import { frameClipboard } from './host/clipboard';
import type { LiveRegistry } from './host/live';
import { createChatPromptContext, type ChatReach } from './host/prompt';
import type { Launch } from './host/server';
import type { ViewSync } from './host/sync';
import { TUNNEL_ORIGIN } from './host/tunnel';

// The most steps a view's history keeps: the oldest go first.
const HISTORY_LIMIT = 100;

export interface ViewReporter {
  /** This view now shows `model` (absolute), or nothing. */
  showing(model: string | null): void;
}

/**
 * One view: the shared CAD viewer over this host — the model a launch names, by its absolute path,
 * or with none, the home (the library, and Open). A view browses from its model's folder, shows
 * what is opened in place, and adds what it shows to the library. Everything differs by data —
 * what a Quick Edit can do in the chat, whether the view has a home — never by where the view is.
 * Codex's file handler (`surface: file`, `alone`) shows its file alone: the host's own file tree is
 * its navigation.
 */
export default function ModelView({ launch, sequence, alone = false, bridge, client, tunnel, tabStore, live, links, colorScheme, theme, locale, language, platform, reporter, sync, chat, appSettings, update, fullSize, openInBrowser }: {
  launch: Launch; sequence: number; bridge: Bridge; tabStore: TabStore; live: LiveRegistry; links: ViewerLinks;
  /**
   * The view shows the one file its host opened, and nothing else (Codex's file handler): no home,
   * no explorer, no history, and no link to another file. The view's, from the launch that opened
   * it; nothing shown later changes it.
   */
  alone?: boolean;
  /** The CAD client over `cad_http`: the viewer's routes, the library, Open and Reveal among them. */
  client: CadClient;
  /** Its fetch, for the files a Quick Edit makes. */
  tunnel: typeof fetch;
  colorScheme: 'light' | 'dark'; platform: string; reporter: ViewReporter;
  /** The person's theme, the app menu's Theme rows. */
  theme?: ColorSchemeSetting;
  /** The language the view reads in, and the person's choice of it: the app menu's Language row. */
  locale?: string;
  language?: LanguageSetting;
  /** The view's one call each second: it carries what this view's client would otherwise poll for. */
  sync: ViewSync;
  /** What the chat takes from a Quick Edit: context for the next message, a message now, or neither (Copy Prompt alone). */
  chat: ChatReach;
  /** This app's on/off settings, in the app menu: analytics. */
  appSettings?: readonly AppSetting[];
  /** The update button, first in the navbar and on the home, while this install is behind. */
  update?: ReactNode;
  /** Inline, the card's way to full size, where the host can show it so: in the navbar, before the view's controls and Open in browser, over a file and on the home. */
  fullSize?: ReactNode;
  /** The view's page in the person's browser, where the engine gives one: last in the navbar, over every file and on the home. */
  openInBrowser?: ReactNode;
}) {
  // Codex's file handler shows its file alone: the host's own file tree is its navigation, so it
  // has neither the home nor the explorer (a source that cannot list or search offers none).
  const homed = !alone;
  const source = useMemo(() => {
    const { list, search, ...alone } = createCadFileSource(client);
    return homed ? { ...alone, list, search } : alone;
  }, [client, homed]);
  // The view's own history, as a browser keeps a tab's: what it showed — files, by absolute path,
  // and the home ('') — the agent's shows and the person's own moves alike. Back and Forward walk
  // them; a move after a Back drops what was ahead, and showing what is already on screen adds
  // nothing.
  const launched = () => normalizePath(launch.model || '');
  const [history, setHistory] = useState(() => ({ entries: [launched()], index: 0 }));
  const file = history.entries[history.index] ?? '';
  const navigate = useCallback((next: string) => setHistory(current => {
    if (current.entries[current.index] === next) return current;
    const entries = [...current.entries.slice(0, current.index + 1), next].slice(-HISTORY_LIMIT);
    return { entries, index: entries.length - 1 };
  }), []);
  const back = useCallback(() => setHistory(current => current.index > 0 ? { ...current, index: current.index - 1 } : current), []);
  const forward = useCallback(() => setHistory(current =>
    current.index < current.entries.length - 1 ? { ...current, index: current.index + 1 } : current), []);
  const showing = useRef(file);
  showing.current = file;
  // A Quick Edit's views, annotation and pictures are made by the server, which is on this machine.
  const promptFiles = useMemo(() => createHttpPromptFiles({ origin: TUNNEL_ORIGIN, fetch: tunnel }), [tunnel]);
  const chatContext = useMemo(() => chat.queue || chat.send ? createChatPromptContext(bridge, { reach: chat }) : null,
    [chat.queue, chat.send, bridge]);
  useEffect(() => () => chatContext?.dispose(), [chatContext]);
  const promptContext = chatContext ?? unavailablePromptContext;
  // The file menu: its path, and Reveal in the desktop's file manager (the server is on this machine).
  const fileActions = useMemo(() => createCadFileActions({ platform, clipboard: frameClipboard, reveal: path => client.reveal(path) }), [platform, client]);

  // The agent's show of a file is a step in the view's history, as a person's is.
  useEffect(() => { navigate(launched()); }, [launch, sequence]);
  useEffect(() => sync.watch({
    file: () => showing.current || null, revision: () => client.getSnapshot().catalogRevision,
    refresh: next => client.refresh({ ...(next ? { file: next } : {}), markRefreshing: false }),
  }), [sync, client]);
  useEffect(() => { reporter.showing(file || null); }, [reporter, file]);

  // Every other view has the home: the models opened before, from every view and the web viewer,
  // and Open with the desktop's chooser where there is one. What it opens is shown in place.
  // The home's first list came with its launch: the cards draw at once, and later reads ask.
  const seeded = useRef(launch.recents ?? null);
  const library = useMemo<ModelLibrarySource | undefined>(() => homed ? {
    list: () => {
      const first = seeded.current;
      seeded.current = null;
      return first ? Promise.resolve(first) : client.recents();
    },
    change: (action, entry) => client.changeRecents({ action, path: entry.path }),
    thumbnail: name => client.thumbnail(name),
    open: async entry => { navigate(normalizePath(entry.path)); },
    ...(launch.pick ? { pick: async () => { const picked = await client.pick(); if (picked) navigate(normalizePath(picked)); } } : {}),
  } : undefined, [client, homed, launch.pick, navigate]);
  // Back and Forward, wherever the view can go elsewhere: not a file handler's, which shows its file alone.
  const viewerHistory = useMemo(() => homed ? {
    canGoBack: history.index > 0, canGoForward: history.index < history.entries.length - 1, back, forward,
  } : undefined, [homed, history, back, forward]);
  const host = useMemo<Omit<ViewerHost, 'navigation'>>(() => ({
    files: source, fileActions, clipboard: frameClipboard, promptContext, promptFiles, links,
    // A Quick Edit copied, queued or sent, counted by the CAD app's server for its telemetry.
    usage: { used: feature => { if (feature === 'quickEdit') client.reportActivity({ quickEdit: true }); } },
    environment: { colorScheme, locale, platform },
  }), [client, source, fileActions, promptContext, promptFiles, links, colorScheme, locale, platform]);

  // The file on screen joins the library every CAD view shares, with its picture.
  return <CadViewer client={client} host={host} tabStore={tabStore} live={live} file={file} onShow={navigate}
    onShown={path => { if (path) void client.changeRecents({ action: 'open', path }).catch(() => {}); }}
    library={library} appSettings={appSettings} colorScheme={theme} language={language} update={update} fullSize={fullSize} openInBrowser={openInBrowser} history={viewerHistory}
    onThumbnail={(png, pictured) => client.keepThumbnail(png, pictured)} />;
}
