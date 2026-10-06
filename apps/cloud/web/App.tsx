import { useCallback, useEffect, useMemo, useRef, useState, useSyncExternalStore } from 'react';
import { cadApiUrl, createCadClient, createHttpAttachmentStore, type CadEditingPreview } from '@text-to-cad/core/client';
import { CadViewer, createCadFileSource, normalizePath } from '@text-to-cad/ui/cad-viewer';
import { createLiveRegistry, type ViewerHost } from '@text-to-cad/ui/host';
import { viewerLinks } from '@text-to-cad/ui/links';
import type { Appearance as AppearancePreference, TabStore } from '@text-to-cad/ui/tab-store';
import type { FileActions, FileSource } from '@text-to-cad/ui/file-viewer';
import { version } from '../package.json';
import Appearance from './Appearance.jsx';
import CodePanel from './CodePanel.tsx';
import HostBar from './HostBar.tsx';
import { baseName, buildOrigin, buildPagePath, fileAddress, normalizeVirtualPath } from './build.ts';
import { fetchBuild, type BuildSummary } from './host/buildApi.ts';
import { browserClipboard, clipboardSupportsImages } from './host/clipboard.ts';
import { applyColorSchemeToDocument, resolveColorSchemeMode, type ColorSchemePreference } from './host/colorScheme.ts';
import { createClipboardPromptContext } from './host/promptContext.ts';

/** The keyboard the page is typed on — ⌘ on Apple devices, Ctrl elsewhere. */
const keyboardPlatform = () => /Mac|iPhone|iPad/.test(navigator.platform) ? 'darwin' : /Win/.test(navigator.platform) ? 'win32' : 'linux';
const DARK_QUERY = '(prefers-color-scheme: dark)';
const subscribeToSystemDark = (onChange: () => void) => {
  const query = matchMedia(DARK_QUERY);
  query.addEventListener('change', onChange);
  return () => query.removeEventListener('change', onChange);
};
const systemPrefersDark = () => matchMedia(DARK_QUERY).matches;
const FEATURES = Object.freeze({ quickEdit: true });

/** The appearance the tab keeps, resolved against the OS: `light` or `dark`, live. */
function useTabAppearance(tabStore: TabStore) {
  const settings = useSyncExternalStore(tabStore.settings.subscribe, tabStore.settings.getSnapshot, tabStore.settings.getSnapshot);
  const prefersDark = useSyncExternalStore(subscribeToSystemDark, systemPrefersDark, systemPrefersDark);
  return { preference: settings.appearance as ColorSchemePreference, mode: resolveColorSchemeMode(settings.appearance, { prefersDark }) };
}

/**
 * One build's page: the shared CAD viewer over the build's recorded viewer API, showing the file
 * the URL names (`/b/<build>/<virtual path>`), with the page's own row above it. The build is
 * immutable, so nothing polls: the catalog is read when a file is shown, and a file's build feed
 * once. References, Quick Edit and Copy link name a file by its address on this page.
 */
export default function App({ id, initialPath, tabStore }: { id: string; initialPath: string; tabStore: TabStore }) {
  const pageOrigin = window.location.origin;
  const origin = useMemo(() => buildOrigin(pageOrigin, id), [pageOrigin, id]);
  const client = useMemo(() => createCadClient({
    origin, pollIntervalMs: 0,
    // A build's feed, once: the build is immutable, so the recorded answer is the whole story.
    editingPreviewFeed: (file, onUpdate, onError) => {
      const controller = new AbortController();
      fetch(cadApiUrl('/__cad/preview', { origin, file }), { signal: controller.signal, cache: 'no-store' })
        .then(response => response.ok ? response.json() as Promise<CadEditingPreview> : Promise.reject(new Error(`HTTP ${response.status}`)))
        .then(preview => { if (!controller.signal.aborted) onUpdate(preview); })
        .catch(error => { if (!controller.signal.aborted) onError(error); });
      return () => controller.abort();
    },
  }), [origin]);
  useEffect(() => () => client.dispose(), [client]);

  // The file the URL names; '' while the link names none (the build's primary file is asked for).
  const [file, setFile] = useState(() => normalizePath(initialPath));
  const shownFile = useRef(file);
  shownFile.current = file;
  const [build, setBuild] = useState<BuildSummary | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    fetchBuild(id, controller.signal).then(found => {
      if (controller.signal.aborted) return;
      setBuild(found);
      if (!shownFile.current && found?.primaryFile) {
        window.history.replaceState(null, '', buildPagePath(id, found.primaryFile));
        setFile(normalizePath(found.primaryFile));
      }
    }).catch(() => {});
    return () => controller.abort();
  }, [id]);
  useEffect(() => {
    const sync = () => {
      const match = /^\/b\/[^/]+(\/.*)?$/.exec(window.location.pathname);
      let rest = match?.[1] || '';
      try { rest = decodeURIComponent(rest); } catch { rest = ''; }
      setFile(normalizePath(normalizeVirtualPath(rest)));
    };
    window.addEventListener('popstate', sync);
    return () => window.removeEventListener('popstate', sync);
  }, []);
  /** Show another file of the build: a new step in the browser's history. */
  const show = useCallback((next: string) => {
    const path = normalizePath(next);
    if (!path || path === shownFile.current) return;
    window.history.pushState(null, '', buildPagePath(id, path));
    setFile(path);
  }, [id]);
  const shown = useCallback((path: string | null) => {
    document.title = path ? `CAD | ${baseName(path)}` : 'CAD';
  }, []);

  const address = useCallback((path: string) => fileAddress(pageOrigin, id, path), [pageOrigin, id]);
  // The host's ports: the build's files (named by their address on this page), the browser's
  // clipboard (Copy for prompt, Copy link), the build's sketches, and the shared links.
  const source = useMemo<FileSource>(() => ({ ...createCadFileSource(client, { id: `build:${id}` }), address }), [client, id, address]);
  const fileActions = useMemo<FileActions>(() => ({ platform: keyboardPlatform(), perform: { 'copy-path': entry => browserClipboard.writeText(address(entry.path)) } }), [address]);
  const promptContext = useMemo(() => createClipboardPromptContext(browserClipboard, clipboardSupportsImages()), []);
  const attachments = useMemo(() => createHttpAttachmentStore({ origin }), [origin]);
  const links = useMemo(() => viewerLinks({ version }), []);
  const live = useMemo(() => createLiveRegistry(), []);
  const appearance = useTabAppearance(tabStore);
  useEffect(() => { applyColorSchemeToDocument(appearance.mode, document.documentElement); }, [appearance.mode]);
  const changeAppearance = useCallback((value: string) => tabStore.settings.update({ appearance: value as AppearancePreference }), [tabStore]);
  const host = useMemo<Omit<ViewerHost, 'navigation'>>(() => ({
    files: source, fileActions, clipboard: browserClipboard, promptContext, attachments, links,
    environment: { colorScheme: appearance.mode, platform: keyboardPlatform() },
  }), [source, fileActions, promptContext, attachments, links, appearance.mode]);

  const [codeOpen, setCodeOpen] = useState(false);
  const downloadUrl = file ? cadApiUrl('/__cad/asset', { origin, file }) : '';
  return <div className="flex h-svh flex-col overflow-hidden" data-cloud-build={id}>
    <HostBar title={build?.title || ''} id={id} status={build?.status || ''} fileName={file ? baseName(file) : ''} downloadUrl={downloadUrl}
      address={file ? address(file) : ''} codeOpen={codeOpen} onToggleCode={() => setCodeOpen(open => !open)} onCopyLink={link => browserClipboard.writeText(link)} />
    <div className="flex min-h-0 flex-1">
      <div className="min-w-0 flex-1">
        <CadViewer client={client} host={host} tabStore={tabStore} live={live} file={file} onShow={show} onShown={shown} features={FEATURES}
          displayActions={<Appearance preference={appearance.preference} mode={appearance.mode} onChange={changeAppearance} />} />
      </div>
      {codeOpen ? <CodePanel id={id} /> : null}
    </div>
  </div>;
}
