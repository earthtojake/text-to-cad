/**
 * The Viewer's part in CAD's anonymous usage analytics (`cadgen/analytics.py`, served by
 * `cadgen.viewer`'s `/__cad/analytics`): the card's and Settings toggle's state, the person's
 * answer, and what the page did -- the model it shows, and a person touching it. The server keeps
 * the model as a code, notes all of it in memory, and sends it only with consent.
 */
import type { AnalyticsConsent, AnswerFrom } from '@text-to-cad/ui/consent';

const HEADERS = { 'x-cadgen-viewer': '1', 'content-type': 'application/json' };

/** Read the consent (`share` omitted), or answer it: the card's answer counts only while the question is open. */
export async function consent(share?: boolean, from?: AnswerFrom): Promise<AnalyticsConsent> {
  const response = share === undefined
    ? await fetch('/__cad/analytics')
    : await fetch('/__cad/analytics', { method: 'POST', headers: HEADERS, body: JSON.stringify({ share, ...(from === 'card' ? { card: true } : {}) }) });
  if (!response.ok) throw new Error(`analytics consent: ${response.status}`);
  return await response.json() as AnalyticsConsent;
}

/** What the page did: shows `file` (as the catalog names it), or a person `touched` it. Never fails. */
export function reportActivity(activity: { file?: string; touched?: boolean }): void {
  void fetch('/__cad/analytics/activity', { method: 'POST', headers: HEADERS, body: JSON.stringify(activity) }).catch(() => {});
}
