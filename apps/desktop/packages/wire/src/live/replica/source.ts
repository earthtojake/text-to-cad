import type { Unsubscribe } from '@emdash/shared';
import type { ResourceCache } from '@emdash/shared/concurrency';
import type { LiveSource, LiveSubscribeOptions, LiveUpdate } from '../../api/channel';

export function resourceCachedLiveSource<K, T>(
  source: ResourceCache<K, T>,
  key: K,
  getSource: (value: T) => LiveSource
): LiveSource {
  return {
    async snapshot() {
      const lease = await source.acquire(key);
      try {
        return await getSource(await lease.ready()).snapshot();
      } finally {
        await lease.release();
      }
    },
    async subscribe(cb: (update: LiveUpdate) => void, options?: LiveSubscribeOptions) {
      const lease = source.acquire(key);
      let unsubscribe: Unsubscribe | undefined;
      try {
        const value = await lease.ready();
        unsubscribe = await getSource(value).subscribe(cb, options);
      } catch (error) {
        await lease.release();
        throw error;
      }

      return () => {
        unsubscribe?.();
        void lease.release();
      };
    },
  };
}
