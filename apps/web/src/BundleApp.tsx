import { useCallback, useEffect, useMemo, useRef } from 'react';
import { CadViewer, createCadFileSource } from '@cad/ui/cad-viewer';
import { createLiveRegistry, type PromptSubject, type ViewerHost } from '@cad/ui/host';
import type { Appearance, TabStore } from '@cad/ui/tab-store';
import type { CadViewBundleClient } from '@cad/core/client';
import { english, translator, useLanguage } from '@cad/ui/i18n';
import { browserClipboard, browserClipboardSupportsImages } from './host/clipboard';
import { createWebPromptContext } from './host/promptContext';
import { browserLanguage } from './host/browserLanguage.js';
import { useViewerLinks } from './host/viewerLinks.js';
import { applyColorSchemeToDocument } from './client/ui/colorScheme.js';
import { useTabAppearance } from './App';

/** The keyboard the page is typed on — ⌘ on Apple devices, Ctrl elsewhere. */
const keyboardPlatform = () => /Mac|iPhone|iPad/.test(navigator.platform) ? "darwin" : /Win/.test(navigator.platform) ? "win32" : "linux";
const NOWHERE = () => {};

/**
 * The viewer's page over one view bundle, a share's (`main.tsx`'s `/<id>`): the bundle's one document and nothing
 * else, read from the bundle alone with no engine behind the page. It is the shared
 * viewer with no library (no home, no Recents, no explorer, no link to another file) and only the host's
 * ports that need no engine: the clipboard (Quick Edit's Copy), this build's links, the tab's appearance and
 * the person's language, kept in this browser (`host/browserLanguage.js`). Everything the engine answered
 * is left out where the viewer reads it: the client has no exports, no parameters to save or preview, no board's 3D
 * models table (a board is drawn in 2D) and no next version, and the host no file actions, no folders to name files
 * from, no Telemetry and no What's new. A Quick Edit carries its snapshot packet as on any page (the page makes it). A
 * prompt from the page names the document by the share's link, not as the view does (`promptSubject`): the host's.
 * The document's ⋯ offers the files that made it, the share's zip (`sharedFiles`), where the page is a share's.
 */
export default function BundleApp({ client, tabStore, language: chosenLanguage = null, promptSubject, sharedFiles }: { client: CadViewBundleClient; tabStore: TabStore;
  language?: string | null; promptSubject: PromptSubject; sharedFiles?: { url: string } }) {
  const files = useMemo(() => createCadFileSource(client, { id: 'view-bundle' }), [client]);
  const sayRef = useRef<(key: string, params?: Record<string, unknown>) => string>(english);
  const promptContext = useMemo(() => createWebPromptContext(browserClipboard, browserClipboardSupportsImages(),
    (key, params) => sayRef.current(key, params)), []);
  const live = useMemo(() => createLiveRegistry(), []);
  const links = useViewerLinks();
  const name = client.manifest.document.name;
  useEffect(() => { document.title = name || 'text-to-cad'; }, [name]);
  const appearance = useTabAppearance(tabStore);
  const changeColorScheme = useCallback((value: string) => tabStore.settings.update({ appearance: value as Appearance }), [tabStore]);
  const colorScheme = useMemo(() => ({ preference: appearance.preference, onPreferenceChange: changeColorScheme }), [appearance.preference, changeColorScheme]);
  useEffect(() => { applyColorSchemeToDocument(appearance.colorScheme, document.documentElement); }, [appearance.colorScheme]);
  const kept = useMemo(() => browserLanguage(), []);
  const { locale, language } = useLanguage(kept, { preferred: navigator.languages ?? [navigator.language], initial: chosenLanguage });
  useEffect(() => { document.documentElement.lang = locale; }, [locale]);
  sayRef.current = translator(locale);
  const host = useMemo<Omit<ViewerHost, 'navigation'>>(() => ({
    files, clipboard: browserClipboard, promptContext, links, promptSubject, sharedFiles,
    environment: { colorScheme: appearance.colorScheme, locale, platform: keyboardPlatform() },
  }), [files, promptContext, links, promptSubject, sharedFiles, appearance.colorScheme, locale]);
  return <div className="fixed inset-0 flex flex-col overflow-hidden">
    <div className="isolate min-h-0 flex-1">
      <CadViewer client={client} host={host} tabStore={tabStore} live={live} file={client.file} name={name} onShow={NOWHERE}
        colorScheme={colorScheme} language={language} />
    </div></div>;
}
