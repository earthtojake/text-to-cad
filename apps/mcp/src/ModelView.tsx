import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { createHttpPromptFiles, libraryRow, projectOf, type CadClient } from '@cad/core/client';
import { unavailablePromptContext } from '@cad/core/prompt';
import { CadViewer, createCadFileActions, createCadFileSource, normalizePath, type CadViewerProps } from '@cad/ui/cad-viewer';
import type { AppSetting, ColorSchemeSetting, LanguageSetting } from '@cad/ui/file-viewer';
import type { HomeLocation, NavigationTarget, ViewerLinks } from '@cad/ui/host';
import type { ModelLibrarySource } from '@cad/ui/library';
import type { TabStore } from '@cad/ui/tab-store';
import type { Bridge } from './host/bridge';
import { frameClipboard } from './host/clipboard';
import type { LiveRegistry } from './host/live';
import { createChatPromptContext, type ChatReach } from './host/prompt';
import { translator } from '@cad/ui/i18n';
import type { Launch } from './host/server';
import type { ViewSync } from './host/sync';
import { TUNNEL_ORIGIN } from './host/tunnel';

// The most steps a view's history keeps: the oldest go first.
const HISTORY_LIMIT = 100;
// A step of a view's history: a file, by its absolute path, or the home ('') at a place on it.
interface Step { file: string; place: HomeLocation }
const RECENTS: HomeLocation = { view: 'recents' };
const samePlace = (a: HomeLocation, b: HomeLocation) => a.view === b.view && (a.view !== 'project' || (b.view === 'project' && a.project === b.project));
const sameStep = (a: Step | undefined, b: Step) => Boolean(a) && a!.file === b.file && (b.file !== '' || samePlace(a!.place, b.place));

export interface ViewReporter {
  /** This view now shows `model` (absolute), or nothing. */
  showing(model: string | null): void;
}

/**
 * One view: the shared viewer over this host — the model a launch names, by its absolute path,
 * or with none, the home (the library, and Open) — under the navbar: its logo (the way home: a
 * button, as a page in an app's frame has no address), the panel's toggle, Back and Forward, the file's name and menus
 * (its ⋯: Copy path, and Open in › Browser and the file manager), and at the right the host's Full size. The links
 * (GitHub, Discord, Send feedback) and Settings (Language, Telemetry, Theme) are the foot of the sidebar, on the home
 * and over a document. A view shows what is opened in place, and adds what it
 * shows to the library. A page in an app's frame has no address of its own: a place on the home (Recents, Pinned, a
 * project's page, Standalone) is a step of the view's history, and a document's Open in browser is its page in the web
 * viewer. Everything differs by data — what a Quick Edit can do in the chat, whether
 * the view has a home — never by where the view is.
 *
 * Codex's file handler (`surface: file`, `alone`) shows its file alone, under the same navbar: the host's own file
 * tree is its navigation, so it has no home, no explorer and no Back or Forward, and no Open in › Browser; its navbar
 * holds the logo, which opens the app's menu there (a view with no home has no foot in its panel), the panel's toggle,
 * the file's name, its ⋯ and Full size where the host offers it.
 */
export default function ModelView({ launch, sequence, alone = false, bridge, client, tunnel, tabStore, live, links, colorScheme, theme, locale, language, platform, reporter, sync, chat, appSettings, fullSize, whatsNew, openInBrowser, engineOrigin }: {
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
  /** What's new, where the view has the page to say it over (a tab): `CadViewerProps.whatsNew`. */
  whatsNew?: { entry: string | null; onDismiss(): void };
  /** Inline, the card's way to full size, where the host can show it so: in the navbar; the corner's in the file handler. */
  fullSize?: ReactNode;
  /**
   * Open a document's page (a file's path, a model's id) in the person's browser, where a launch carried
   * a page: the file menu's Open in › Browser (`fileActions.perform.browser`). Never in the file handler.
   */
  openInBrowser?: (document: string) => void;
  /**
   * The engine's own HTTP origin (the launch's `engine`), where a launch named one: Copy link's
   * address, `<origin>/<id>?token=<fresh link>`, the link asked for through the tunnel. Never the tunnel's.
   */
  engineOrigin?: string;
}) {
  // Codex's file handler shows its file alone: the host's own file tree is its navigation, so it
  // has neither the home nor a project's name (a view with no library has neither).
  const homed = !alone;
  const source = useMemo(() => createCadFileSource(client), [client]);
  // The view's own history, as a browser keeps a tab's: what it showed — files, by absolute path,
  // and the home ('') at each place the person went to on it — the agent's shows and the person's own moves alike.
  // Back and Forward walk them; a move after a Back drops what was ahead, and showing what is already on screen adds
  // nothing.
  const launched = () => normalizePath(launch.model || '');
  const [history, setHistory] = useState<{ entries: Step[]; index: number }>(() => ({ entries: [{ file: launched(), place: RECENTS }], index: 0 }));
  const { file, place } = history.entries[history.index] ?? { file: '', place: RECENTS };
  const navigate = useCallback((next: string, where: HomeLocation = RECENTS) => setHistory(current => {
    const step = { file: next, place: next ? RECENTS : where };
    if (sameStep(current.entries[current.index], step)) return current;
    const entries = [...current.entries.slice(0, current.index + 1), step].slice(-HISTORY_LIMIT);
    return { entries, index: entries.length - 1 };
  }), []);
  const back = useCallback(() => setHistory(current => current.index > 0 ? { ...current, index: current.index - 1 } : current), []);
  const forward = useCallback(() => setHistory(current =>
    current.index < current.entries.length - 1 ? { ...current, index: current.index + 1 } : current), []);
  const showing = useRef(file);
  showing.current = file;
  // A Quick Edit's views, annotation and pictures are made by the server, which is on this machine.
  const promptFiles = useMemo(() => createHttpPromptFiles({ origin: TUNNEL_ORIGIN, fetch: tunnel }), [tunnel]);
  // What the chat's port says to the person, in the view's language as it is when it speaks.
  const sayRef = useRef(translator(locale));
  sayRef.current = translator(locale);
  const chatContext = useMemo(() => chat.queue || chat.send
    ? createChatPromptContext(bridge, { reach: chat, t: (key, params) => sayRef.current(key, params) }) : null,
    [chat.queue, chat.send, bridge]);
  useEffect(() => () => chatContext?.dispose(), [chatContext]);
  const promptContext = chatContext ?? unavailablePromptContext;
  // The file menu: its path, Reveal in the desktop's file manager (the server is on this machine),
  // and, in a view with a home, the document's page in the browser (Open in › Browser).
  const fileActions = useMemo(() => {
    // Open in's apps too, through the tunnel as Reveal is: the server opens them on this computer.
    const actions = createCadFileActions({ platform, clipboard: frameClipboard, reveal: path => client.reveal(path), openIn: client,
      ...(engineOrigin ? { link: { origin: engineOrigin, client } } : {}) });
    return homed && openInBrowser ? { ...actions, perform: { ...actions.perform, browser: (entry: { path: string }) => openInBrowser(entry.path) } } : actions;
  }, [platform, client, homed, openInBrowser, engineOrigin]);

  // The agent's show of a file is a step in the view's history, as a person's is.
  useEffect(() => { navigate(launched()); }, [launch, sequence]);
  useEffect(() => sync.watch({
    file: () => showing.current || null, revision: () => client.getSnapshot().catalogRevision,
    refresh: next => client.refresh({ ...(next ? { file: next } : {}), markRefreshing: false }),
  }), [sync, client]);
  useEffect(() => { reporter.showing(file || null); }, [reporter, file]);

  // Every other view has the home: the projects and the documents opened before, from every view and the web viewer.
  // What it opens is shown in place.
  // The home's first lists came with its launch, as `GET /api/v1/documents` and `GET /api/v1/projects` list them: the
  // cards draw at once, each its picture read by its document's id, and later reads ask.
  const seeded = useRef(launch.recents ?? null);
  const seededProjects = useRef(launch.projects ?? null);
  const library = useMemo<ModelLibrarySource | undefined>(() => homed ? {
    list: () => {
      const first = seeded.current;
      seeded.current = null;
      return first ? Promise.resolve(first.map(libraryRow)) : client.recents();
    },
    change: (action, entry) => client.changeRecents({ action, path: entry.path }),
    thumbnail: model => client.thumbnail(model),
    open: async entry => { navigate(normalizePath(entry.path)); },
    projects: () => {
      const first = seededProjects.current;
      seededProjects.current = null;
      return first ? Promise.resolve(first.map(projectOf)) : client.projects?.() ?? Promise.resolve([]);
    },
    removeProject: project => client.removeProject?.(project.id) ?? Promise.resolve([]),
    // Import, with the desktop's chooser where this computer has one: a file it picks is shown in place, a folder
    // opened as a project.
    ...(launch.pick ? {
      pick: async () => { const picked = await client.pick(); if (picked) navigate(normalizePath(picked)); },
      importFolder: async (start?: string) => {
        const folder = await client.pick({ folder: true, start });
        if (!folder || !client.openProject) return null;
        return { ...await client.openProject(folder), folder };
      },
    } : {}),
  } : undefined, [client, homed, launch.pick, navigate]);
  // Back and Forward, wherever the view can go elsewhere: not a file handler's, which shows its file alone.
  const viewerHistory = useMemo(() => homed ? {
    canGoBack: history.index > 0, canGoForward: history.index < history.entries.length - 1, back, forward,
  } : undefined, [homed, history, back, forward]);
  // A page in an app's frame has no address: no link to a document or a place (`hrefOf`). Where a launch carried a
  // page, a document opens beside the view in the person's browser, its page in the web viewer (Open in browser); the
  // server opens that page by the document's name and nothing else, so a place on the home is not offered.
  const navigation = useMemo(() => (homed && openInBrowser ? { openBeside: { kind: 'browser' as const, places: false,
    open: (target: NavigationTarget) => { if ('document' in target) openInBrowser(normalizePath(target.document)); } } } : undefined),
    [homed, openInBrowser]);
  const host = useMemo<CadViewerProps['host']>(() => ({
    files: source, fileActions, clipboard: frameClipboard, promptContext, promptFiles, links, ...(navigation ? { navigation } : {}),
    // A Quick Edit copied, queued or sent, counted by the CAD app's server for its telemetry.
    usage: { used: feature => { if (feature === 'quickEdit') client.reportActivity({ quickEdit: true }); },
      // The controls a person used, and how long a tool was up, counted by the shared viewer.
      controls: counts => client.reportActivity({ controls: counts }) },
    environment: { colorScheme, locale, platform },
  }), [client, source, fileActions, promptContext, promptFiles, links, navigation, colorScheme, locale, platform]);

  // Every view is under the navbar, the file handler's too: it carries the host's controls and the panels' toggles.
  // The file on screen joins the library every CAD view shares, with its picture.
  return <CadViewer client={client} host={host} tabStore={tabStore} live={live} file={file} onShow={navigate} place={place}
    onShown={path => { if (path) void client.changeRecents({ action: 'open', path }).catch(() => {}); }}
    library={library} appSettings={appSettings} colorScheme={theme} language={language} history={viewerHistory} whatsNew={whatsNew}
    fullSize={fullSize}
    onThumbnail={(png, pictured) => client.keepThumbnail(png, pictured)} />;
}
