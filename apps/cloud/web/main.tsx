import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { FileWarning } from 'lucide-react';
import { EmptyState } from '@text-to-cad/ui/navigation';
import { createTabStore } from '@text-to-cad/ui/tab-store';
import App from './App.tsx';
import { parseBuildLocation } from './build.ts';
import { sessionTabRecord } from './host/tabRecord.ts';
import './styles.css';

const element = document.getElementById('root');
if (!element) throw new Error('Missing #root mount point.');
const root = createRoot(element);
document.title = 'CAD';

// The link names the build and the file: /b/<build>/<path>. Anything else is not a build's page.
const location = parseBuildLocation(window.location.pathname);
if (!location) {
  root.render(<div className="cloud-notice"><EmptyState icon={FileWarning} title="Not a build link" description="A build opens at /b/<build>/<file>." tone="warn" /></div>);
} else {
  // The tab's one store, over this tab's sessionStorage: what the viewer keeps survives a reload.
  const tabStore = createTabStore(sessionTabRecord(window.sessionStorage));
  root.render(<StrictMode><App id={location.id} initialPath={location.path} tabStore={tabStore} /></StrictMode>);
}
