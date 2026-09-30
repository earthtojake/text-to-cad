import { useMemo, useRef, useState, type MouseEvent } from 'react';
import { ModelLibrary, type ModelLibrarySource } from '@text-to-cad/ui/library';
import { version } from '../package.json';
import cadLogo from './assets/logo-cad.svg';
import type { Launch, Server } from './host/server';

const GITHUB = 'https://github.com/earthtojake/text-to-cad';
const DISCORD = 'https://discord.gg/5FGB9DwJYU';

/**
 * CAD's home: the models opened before, from every view and the web viewer, and Open Model to
 * pick one from disk with the desktop's chooser. Opening switches this same view to the model.
 */
export default function Home({ server, onOpen, onOpenLink }: { server: Server; onOpen(launch: Launch): void; onOpenLink(url: string): Promise<void> }) {
  const opened = useRef(onOpen);
  opened.current = onOpen;
  const library = useMemo<ModelLibrarySource>(() => ({
    list: () => server.recents(),
    change: (action, model) => server.recents({ action, path: model.path }),
    thumbnail: name => server.thumbnails([name]).then(found => found[name] ? `data:image/png;base64,${found[name]}` : null),
    open: model => server.launch(model.path).then(launch => opened.current(launch)),
    pick: () => server.pickModel().then(result => { if (result.launch) opened.current(result.launch); }),
  }), [server]);
  const [failure, setFailure] = useState('');
  const openLink = (event: MouseEvent<HTMLAnchorElement>) => {
    event.preventDefault();
    setFailure('');
    void onOpenLink(event.currentTarget.href).catch(error => setFailure(error instanceof Error ? error.message : String(error)));
  };
  return <ModelLibrary library={library} failure={failure}
    header={<header className="cad-library-brand"><img className="cad-library-logo" src={cadLogo} alt="CAD" /></header>}
    footer={<footer className="cad-library-footer" aria-label="CAD links">
      <a href={`${GITHUB}/releases/tag/v${version}`} aria-label={`CAD version ${version}`} target="_blank" rel="noreferrer" onClick={openLink}>v{version}</a>
      <a href={GITHUB} target="_blank" rel="noreferrer" onClick={openLink}>GitHub</a>
      <a href={DISCORD} target="_blank" rel="noreferrer" onClick={openLink}>Discord</a>
    </footer>} />;
}
