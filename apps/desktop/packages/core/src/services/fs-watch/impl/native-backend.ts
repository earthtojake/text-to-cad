import type { WatchBackend, WatchOnError } from './backend';
import { NativeWatch, type ParcelSubscribeFn } from './native-watch';

export type NativeWatchBackendOptions = {
  onError?: WatchOnError;
  subscribe?: ParcelSubscribeFn;
};

export function nativeWatchBackend(options: NativeWatchBackendOptions = {}): WatchBackend {
  const onError = options.onError ?? (() => {});

  return {
    async subscribe(key, sink, scope) {
      const native = new NativeWatch(
        key.root,
        key.ignore,
        sink.events,
        sink.resync,
        onError,
        options.subscribe
      );
      scope.add(() => {
        // A Parcel subscribe can remain pending after the channel startup timeout. Start cleanup
        // without making scope disposal wait for that promise; NativeWatch disposes a late result.
        void native.dispose();
      });
      await native.ready();
    },
  };
}
