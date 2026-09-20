import { useLayoutEffect, useMemo, useRef, useState } from 'react';
import { createViewUpdateCoordinator } from './viewUpdateCoordinator.js';

const IDLE = { pending: false, error: null, label: '', revision: 0 };

export function useAppliedViewSettings(desired, scope, viewerRef, settingsStore = null) {
  const [update, setUpdate] = useState({ scene: desired, revision: 0, expensive: false });
  const [status, setStatus] = useState(IDLE);
  const receipt = useRef(null);
  const coordinator = useRef(null);
  const latest = useRef(null);
  latest.current = () => settingsStore?.getSnapshot().scene || desired;
  useLayoutEffect(() => {
    const current = createViewUpdateCoordinator(desired, {
      prepare: (scene, signal) => viewerRef.current?.prepareViewSettings?.(scene, signal),
      apply: (scene, metadata) => new Promise((resolve, reject) => {
        receipt.current = { ...metadata, resolve, reject };
        setUpdate({ scene, ...metadata });
      }),
      present: () => viewerRef.current?.presentViewSettings?.(),
      onStatus: setStatus,
    });
    coordinator.current = current;
    setUpdate({ scene: desired, revision: 0, expensive: false });
    setStatus(IDLE);
    return () => {
      current.dispose();
      receipt.current?.reject(new Error('Viewer closed'));
      receipt.current = null;
    };
  }, [scope]);
  useLayoutEffect(() => { coordinator.current.request(desired); }, [scope, desired]);
  const binding = useMemo(() => ({
    complete(revision, error) {
      if (receipt.current?.revision !== revision) return false;
      const current = receipt.current; receipt.current = null;
      error ? current.reject(error) : current.resolve();
      return true;
    },
    whenReady: () => {
      // Agent code may patch and capture in the same JavaScript turn, before
      // React subscribes/renders. Read the authority, not the last render.
      coordinator.current.request(latest.current());
      return coordinator.current.whenReady();
    },
    retry: () => coordinator.current.retry(),
  }), []);
  return { ...update, status, binding, retry: binding.retry };
}
