/**
 * The Viewer's part in the app menu's features (`cadgen/features.py`, served by `cadgen.viewer`'s
 * `/__cad/features`): every feature as the person left it, and their change of one. The server
 * keeps it in the person's settings, beside the analytics answer, so it is one choice with the CAD
 * app's and holds whatever port this Viewer is served on — which a browser's own storage would not.
 */
import type { ViewerFeatures } from '@text-to-cad/ui/features';

const HEADERS = { 'x-cadgen-viewer': '1', 'content-type': 'application/json' };

/** Read the features (`change` omitted), or change some and read them all. */
export async function features(change?: Partial<ViewerFeatures>): Promise<ViewerFeatures> {
  const response = change === undefined
    ? await fetch('/__cad/features')
    : await fetch('/__cad/features', { method: 'POST', headers: HEADERS, body: JSON.stringify(change) });
  if (!response.ok) throw new Error(`features: ${response.status}`);
  return await response.json() as ViewerFeatures;
}
