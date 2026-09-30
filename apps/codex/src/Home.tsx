import { useCallback, useEffect, useRef, useState, type ChangeEvent, type MouseEvent } from 'react';
import { Box, FolderOpen, Pin, Search, X } from 'lucide-react';
import { Button } from '@text-to-cad/ui/primitives/button';
import { Input } from '@text-to-cad/ui/primitives/input';
import { TooltipHint } from '@text-to-cad/ui/primitives/tooltip';
import { version } from '../package.json';
import cadLogo from './assets/logo-cad.svg';
import type { Launch, Recent, Server } from './host/server';

const GITHUB = 'https://github.com/earthtojake/text-to-cad';
const DISCORD = 'https://discord.gg/5FGB9DwJYU';

export function filterRecents(items: readonly Recent[], query: string): Recent[] {
  const words = query.trim().toLowerCase().split(/\s+/).filter(Boolean);
  return items.filter(item => words.every(word => item.path.toLowerCase().includes(word)));
}

function Thumbnail({ item, load }: { item: Recent; load(name: string): Promise<string | null> }) {
  const element = useRef<HTMLSpanElement>(null);
  const [image, setImage] = useState<string | null>(null);
  useEffect(() => {
    let active = true;
    setImage(null);
    if (!item.thumbnail || item.missing || !element.current) return;
    const name = item.thumbnail;
    const observer = new IntersectionObserver(entries => {
      if (!entries.some(entry => entry.isIntersecting)) return;
      observer.disconnect();
      void load(name).then(value => { if (active) setImage(value); }).catch(() => {});
    });
    observer.observe(element.current);
    return () => { active = false; observer.disconnect(); };
  }, [item.thumbnail, item.missing, load]);
  return <span className="cad-recent-thumbnail" ref={element}>{image ? <img src={image} alt="" /> : <Box size={28} strokeWidth={1} aria-hidden="true" />}</span>;
}

/**
 * CAD's home: open a model from disk, or one opened before. Opening switches this same view to
 * the model; nothing on this page waits visibly.
 */
export default function Home({ server, onOpen, onOpenLink }: { server: Server; onOpen(launch: Launch): void; onOpenLink(url: string): Promise<void> }) {
  const [items, setItems] = useState<Recent[]>([]);
  const [query, setQuery] = useState('');
  const [error, setError] = useState('');
  const cache = useRef(new Map<string, Promise<string | null>>());
  const refresh = useCallback(() => server.recents().then(setItems), [server]);
  useEffect(() => {
    void refresh().catch(failure => setError(failure instanceof Error ? failure.message : String(failure)));
    const again = () => { if (document.visibilityState !== 'hidden') void refresh().catch(() => {}); };
    document.addEventListener('visibilitychange', again);
    return () => document.removeEventListener('visibilitychange', again);
  }, [refresh]);
  const load = useCallback((name: string) => {
    let image = cache.current.get(name);
    if (!image) {
      image = server.thumbnails([name]).then(found => found[name] ? `data:image/png;base64,${found[name]}` : null);
      cache.current.set(name, image);
    }
    return image;
  }, [server]);
  const fail = (failure: unknown) => setError(failure instanceof Error ? failure.message : String(failure));
  const openRecent = (item: Recent) => { setError(''); void server.launch(item.path).then(onOpen, fail); };
  const pick = () => {
    setError('');
    void server.pickModel().then(result => { if (result.launch) onOpen(result.launch); }, fail);
  };
  const change = (action: 'pin' | 'unpin' | 'remove', item: Recent) => { void server.recents({ action, path: item.path }).then(setItems, fail); };
  const openLink = (event: MouseEvent<HTMLAnchorElement>) => {
    event.preventDefault();
    void onOpenLink(event.currentTarget.href).catch(fail);
  };
  const searchQuery = items.length ? query : '';
  const shown = filterRecents(items, searchQuery);
  const pinned = shown.filter(item => item.pinned);
  const recent = shown.filter(item => !item.pinned);
  const section = (name: string, models: readonly Recent[]) => <section className="cad-library-section" aria-label={name}>
    <h2>{name}</h2>
    <ul className="cad-recent-grid">{models.map(item => <li key={item.path} className="cad-recent-item">
      <button className="cad-recent-open" disabled={item.missing} aria-label={`Open ${item.name}`} onClick={() => openRecent(item)}>
        <Thumbnail item={item} load={load} />
        <TooltipHint content={item.path} overflowOnly><span className="cad-recent-name truncate">{item.name}</span></TooltipHint>
        <TooltipHint content={item.folder} overflowOnly><span className="cad-recent-folder truncate">{item.folder}</span></TooltipHint>
      </button>
      <div className="cad-recent-detail">
        <span className="cad-recent-status">{item.missing ? 'File unavailable' : new Date(item.opened * 1000).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}</span>
        <div className="cad-recent-actions">
          <TooltipHint content={item.pinned ? 'Unpin' : 'Pin'}><Button variant="ghost" size="icon-xs" aria-label={`${item.pinned ? 'Unpin' : 'Pin'} ${item.name}`} aria-pressed={item.pinned} onClick={() => change(item.pinned ? 'unpin' : 'pin', item)}><Pin aria-hidden="true" /></Button></TooltipHint>
          <TooltipHint content="Remove from recents"><Button variant="ghost" size="icon-xs" aria-label={`Remove ${item.name} from recents`} onClick={() => change('remove', item)}><X aria-hidden="true" /></Button></TooltipHint>
        </div>
      </div>
    </li>)}</ul>
  </section>;
  return <main className="cad-library text-ui" aria-label="CAD models">
    <header className="cad-library-brand"><img className="cad-library-logo" src={cadLogo} alt="CAD" /></header>
    <div className="cad-library-content">
      <div className="cad-library-toolbar">
        <Button size="sm" onClick={pick}><FolderOpen aria-hidden="true" />Open Model</Button>
        {items.length > 0 && <div className="cad-library-search"><Search size={14} aria-hidden="true" /><Input className="h-8" type="search" aria-label="Search models" placeholder="Search models" value={query} onChange={(event: ChangeEvent<HTMLInputElement>) => setQuery(event.target.value)} /></div>}
      </div>
      {error && <div className="cad-library-error" role="alert"><p>{error}</p></div>}
      {searchQuery && !shown.length ? <p className="cad-library-empty" role="status">No matching models.</p> : <>
        {pinned.length > 0 && section('Pinned', pinned)}
        {recent.length > 0 ? section('Recent', recent) : !items.length && <section className="cad-library-section" aria-label="Recent"><h2>Recent</h2><p className="cad-library-empty">Open a CAD file to see it here.</p></section>}
      </>}
    </div>
    <footer className="cad-library-footer" aria-label="CAD links">
      <a href={`${GITHUB}/releases/tag/v${version}`} aria-label={`CAD version ${version}`} target="_blank" rel="noreferrer" onClick={openLink}>v{version}</a>
      <a href={GITHUB} target="_blank" rel="noreferrer" onClick={openLink}>GitHub</a>
      <a href={DISCORD} target="_blank" rel="noreferrer" onClick={openLink}>Discord</a>
    </footer>
  </main>;
}
