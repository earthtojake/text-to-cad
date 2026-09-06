import { MonacoFacetBinder } from '@core/features/editor/api/browser/facet-binder/monaco-facet-binder';
import { openFileStore } from '@core/features/editor/api/browser/open-file-store/open-file-store';
import { monacoBootstrap } from './monaco-bootstrap';

let installed: MonacoFacetBinder | null = null;

/**
 * Registers the Monaco facet binder with the app-global OpenFileStore
 * (migration stage 2, spec §11). Idempotent — the renderer bootstrap calls
 * it once and editor components reuse the returned binder for attach/detach
 * and view-state APIs. Monaco loads lazily through `monacoBootstrap.init()`
 * on first handle creation; an init failure rejects handle creation and the
 * store degrades those facets to error placeholders instead of wedging.
 */
export function installMonacoFacetBinder(): MonacoFacetBinder {
  if (installed) return installed;
  installed = new MonacoFacetBinder(() => monacoBootstrap.init());
  openFileStore.registerBinder(installed);
  return installed;
}
