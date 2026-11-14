import { useCallback, useEffect, useState } from 'react';
import { readNotice, type UpdateNotice } from '@cad/ui/update';

/**
 * Whether a newer release is known, for the update nudge: the page starts on its server's description
 * (`/api/v1/server`'s `notice`, read before the page drew), so the nudge draws with the page, and reads
 * it again whenever the person comes back to the tab (the server's background check may have found a
 * release meanwhile, or the person has updated). Nothing is kept: the nudge stays while a notice is
 * known and goes once none is. A read that fails changes nothing.
 */
export function useUpdateNotice(read: () => Promise<{ notice?: unknown }>, initial: unknown): UpdateNotice | null {
  const [notice, setNotice] = useState<UpdateNotice | null>(() => readNotice(initial));
  const again = useCallback(() => {
    void read().then(answer => setNotice(readNotice(answer?.notice)), () => {});
  }, [read]);
  useEffect(() => {
    window.addEventListener('focus', again);
    return () => window.removeEventListener('focus', again);
  }, [again]);
  return notice;
}
