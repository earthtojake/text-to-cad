import * as THREE from 'three';

// Per viewport: at most one preparing worker and three owned PMREM textures.
// No model geometry crosses the worker boundary. Rotation/exposure do not
// change the cache key; size/fill/quality do.
export function createStudioEnvironmentCache({ maxEntries = 3 } = {}) {
  const entries = new Map();
  let worker = null, disposed = false, pending = null;
  function stop(error) {
    worker?.terminate(); worker = null;
    pending?.reject(error); pending = null;
  }
  function pixels(configuration, size, signal) {
    return new Promise((resolve, reject) => {
      const abort = () => stop(new DOMException('Superseded view update', 'AbortError'));
      function finish(error, result) {
        signal?.removeEventListener('abort', abort);
        pending = null;
        error ? reject(error) : resolve(result);
      }
      pending = { reject: error => finish(error) };
      try {
        worker ??= new Worker(new URL('./studioEnvironment.worker.js', import.meta.url), { type: 'module' });
        worker.onmessage = ({ data }) => {
          // An inactive file tab must not retain a second WebGL context.
          worker?.terminate(); worker = null;
          data.error ? finish(new Error(data.error)) : finish(null, data);
        };
        worker.onerror = event => stop(new Error(event.message || 'Studio preparation failed'));
        worker.onmessageerror = () => stop(new Error('Invalid studio preparation response'));
        signal?.addEventListener('abort', abort, { once: true });
        if (signal?.aborted) { abort(); return; }
        worker.postMessage({ configuration, size });
      } catch (error) { stop(error); }
    });
  }
  return {
    get(key) {
      const resource = entries.get(key);
      if (resource) { entries.delete(key); entries.set(key, resource); }
      return resource;
    },
    owns(resource) { return entries.get(resource?.identity) === resource; },
    async prepare(studio, renderer, configuration, size, signal, pinned) {
      if (disposed) throw new Error('Viewer closed');
      const identity = studio.environmentResourceIdentity(configuration, { size });
      if (entries.has(identity)) return entries.get(identity);
      let resource;
      if (typeof OffscreenCanvas === 'undefined' || typeof Worker === 'undefined') {
        // Compatibility path for browsers without worker WebGL. Still runs
        // after the settings paint, but PMREM itself is synchronous there.
        resource = studio.createEnvironmentResource(renderer, configuration, { size });
      } else {
        const { data, width, height } = await pixels(configuration, size, signal);
        signal?.throwIfAborted();
        const texture = new THREE.DataTexture(data, width, height, THREE.RGBAFormat, THREE.HalfFloatType);
        texture.mapping = THREE.CubeUVReflectionMapping;
        texture.minFilter = texture.magFilter = THREE.LinearFilter;
        texture.colorSpace = THREE.LinearSRGBColorSpace;
        texture.needsUpdate = true;
        let released = false;
        resource = { identity, texture, dispose() { if (!released) { released = true; texture.dispose(); } } };
      }
      if (disposed || signal?.aborted) { resource.dispose(); throw new DOMException('Viewer closed', 'AbortError'); }
      entries.set(identity, resource);
      for (const [key, cached] of entries) {
        if (entries.size <= maxEntries) break;
        if (cached === pinned || cached === resource) continue;
        entries.delete(key); cached.dispose();
      }
      return resource;
    },
    dispose() {
      disposed = true; stop(new Error('Viewer closed'));
      for (const resource of entries.values()) resource.dispose();
      entries.clear();
    },
  };
}
