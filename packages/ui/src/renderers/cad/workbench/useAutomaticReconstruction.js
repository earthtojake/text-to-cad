import { useEffect, useRef, useState } from 'react';
import { requestReconstruction } from './reconstructionClient.js';

/** One verification at a time, independent of the inspector's visible tab.
 * Keep only proof summaries here; full meshes stay in the bounded server cache.
 */
export function useAutomaticReconstruction({ target, file, results, enabled, preferredComponent }) {
  const [statuses, setStatuses] = useState({});
  const lifetime = useRef(null);
  useEffect(() => {
    const scope = { controller: new AbortController(), busy: false };
    lifetime.current = scope;
    setStatuses({});
    return () => { scope.controller.abort(); };
  }, [target, file, enabled]);

  useEffect(() => {
    const scope = lifetime.current;
    if (!enabled || !target || !scope || scope.busy || scope.controller.signal.aborted) return;
    const candidates = Object.keys(results).filter(id => results[id]?.recipe && !statuses[id]);
    const component = candidates.includes(preferredComponent) ? preferredComponent : candidates[0];
    if (!component) return;
    scope.busy = true;
    setStatuses(current => ({ ...current, [component]: { state: 'checking' } }));
    requestReconstruction({ target, file, component, recipe: results[component].recipe, preview: false, signal: scope.controller.signal })
      .then(result => {
        scope.busy = false;
        if (!scope.controller.signal.aborted) setStatuses(current => ({ ...current, [component]: { state: 'ready', ...result } }));
      }).catch(error => {
        scope.busy = false;
        if (!scope.controller.signal.aborted) setStatuses(current => ({ ...current, [component]: { state: 'failed', error: error.message } }));
      });
  }, [target, file, results, enabled, preferredComponent, statuses]);

  const retry = component => setStatuses(current => {
    if (current[component]?.state !== 'failed') return current;
    const next = { ...current }; delete next[component]; return next;
  });
  return { statuses, retry };
}
