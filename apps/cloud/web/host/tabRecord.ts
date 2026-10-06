import type { TabRecordStorage } from '@text-to-cad/ui/tab-store';

/**
 * Where the page keeps the tab record (`@text-to-cad/ui/tab-store`): one `sessionStorage` entry,
 * the browser's own tab, so a reload shows the file as it was left and a closed tab takes it
 * along. The inline script in `index.html` reads this same key for the first paint's appearance.
 */
export const TAB_RECORD_KEY = 'text-to-cad:cloud-tab:v1';

export function sessionTabRecord(storage: Pick<Storage, 'getItem' | 'setItem'>): TabRecordStorage {
  return {
    read() { try { return JSON.parse(storage.getItem(TAB_RECORD_KEY) || 'null'); } catch { return null; } },
    write(record) { try { storage.setItem(TAB_RECORD_KEY, JSON.stringify(record)); } catch { /* a full or refused storage keeps nothing */ } },
  };
}
