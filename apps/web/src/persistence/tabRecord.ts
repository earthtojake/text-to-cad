import type { TabRecordStorage } from '@hardcore/ui/tab-store';

/**
 * Where the web host keeps the tab record: one `sessionStorage` entry. sessionStorage is the
 * browser's own tab: it survives a reload, and a closed tab takes it with it; a new tab, a
 * duplicated one included, starts empty. The inline script in `index.html` reads this same key
 * for the first paint's appearance, so the key and the record's shape are shared with it.
 */
export const TAB_RECORD_KEY = 'hardcore:tab:v1';

export function sessionTabRecord(storage: Pick<Storage, 'getItem' | 'setItem'>): TabRecordStorage {
  return {
    read() { return JSON.parse(storage.getItem(TAB_RECORD_KEY) || 'null'); },
    write(record) { storage.setItem(TAB_RECORD_KEY, JSON.stringify(record)); },
  };
}
