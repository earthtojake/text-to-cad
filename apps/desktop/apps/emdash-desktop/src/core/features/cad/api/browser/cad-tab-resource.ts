import { action, makeObservable, observable, runInAction } from 'mobx';
import { browserControlsRegistry } from '@core/features/browser/api/browser/browser-controls-registry';
import { browserSessionStore } from '@core/features/browser/api/browser/browser-session-store';
import { BrowserTabResource } from '@core/features/browser/api/browser/browser-tab-resource';
import { getBrowserClient } from '@core/features/browser/api/browser/client';
import type { EngineeringWorkspaceMode } from '@core/features/cad/api/browser/cad-engineering-object';
import type {
  TabEntry,
  TabHandle,
  TabResource,
} from '@core/primitives/workbench-shell/browser/tabs/core/tab-provider';
import type { CadState } from '../../browser/cad-tab-provider';

export type CadViewerStatus = 'starting' | 'ready' | 'error';

/**
 * One CAD artifact tab: it asks the host to serve the workspace through Jake's
 * CAD Viewer and embeds that page. The Viewer owns everything inside the
 * frame (viewport, topology tree, measurement, references, display and pose
 * controls); the desktop owns the artifact lifecycle around it and only ever
 * reloads the page when the accepted STEP changes.
 */
export class CadTabResource implements TabResource {
  status: CadViewerStatus = 'starting';
  error: string | null = null;
  chatOpen: boolean;
  workspaceMode: EngineeringWorkspaceMode;
  drawingCreating = false;
  captureRequest = 0;
  private readonly browserResource: BrowserTabResource;
  private requestId = 0;
  private disposed = false;

  constructor(
    private readonly entry: TabEntry<CadState>,
    handle: TabHandle
  ) {
    this.chatOpen = entry.state.chatOpen !== false;
    this.workspaceMode = entry.state.workspaceMode ?? '3d';
    makeObservable(this, {
      status: observable,
      error: observable,
      chatOpen: observable,
      workspaceMode: observable,
      drawingCreating: observable,
      captureRequest: observable,
      retry: action.bound,
      setChatOpen: action.bound,
      setWorkspaceMode: action.bound,
      setDrawingCreating: action.bound,
      requestCaptureForChat: action.bound,
    });
    this.browserResource = new BrowserTabResource(entry, handle);
    void this.start();
  }

  get browserId(): string {
    return this.entry.state.browserId;
  }

  get path(): string {
    return this.entry.state.path;
  }

  get workspacePath(): string {
    return this.entry.state.workspacePath;
  }

  /** Reload the Viewer page so it re-reads the accepted artifact from disk. */
  refreshViewer = (): void => {
    browserControlsRegistry.get(this.browserId)?.adapter?.reloadIgnoringCache();
  };

  setChatOpen(open: boolean): void {
    this.chatOpen = open;
    this.entry.state.chatOpen = open;
  }

  setWorkspaceMode(mode: EngineeringWorkspaceMode): void {
    this.workspaceMode = mode;
    this.entry.state.workspaceMode = mode;
  }

  setDrawingCreating(creating: boolean): void {
    this.drawingCreating = creating;
  }

  requestCaptureForChat(): void {
    this.setChatOpen(true);
    const revealDelay = this.workspaceMode === '3d' ? 0 : 450;
    this.setWorkspaceMode('3d');
    window.setTimeout(() => {
      if (this.disposed) return;
      runInAction(() => {
        this.captureRequest += 1;
      });
    }, revealDelay);
  }

  retry(): void {
    this.status = 'starting';
    this.error = null;
    void this.start();
  }

  dispose(): void {
    if (this.disposed) return;
    this.disposed = true;
    this.requestId += 1;
    this.browserResource.dispose();
  }

  private async start(): Promise<void> {
    const requestId = ++this.requestId;
    const result = await getBrowserClient().then((client) =>
      client.ensureCadViewer({
        workspacePath: this.entry.state.workspacePath,
        filePath: this.entry.state.path,
      })
    );
    if (this.disposed || requestId !== this.requestId) return;
    if (!result.success) {
      runInAction(() => {
        this.status = 'error';
        this.error = result.error;
      });
      return;
    }
    browserSessionStore.updateSession(this.browserId, {
      currentUrl: result.url,
      isLoading: true,
      loadError: null,
    });
    runInAction(() => {
      this.status = 'ready';
      this.error = null;
    });
  }
}
