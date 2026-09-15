// Browser init script: worker-isolate ownership independent of the app ledger.
export function installWorkerProbe() {
  const OriginalWorker = window.Worker;
  if (typeof OriginalWorker !== 'function') return;
  const stats = { created: 0, terminated: 0, live: 0, peakLive: 0 };
  window.__cadWorkerProbe = stats;
  const terminated = new WeakSet();
  const liveWorkers = new Set();
  let stopped = false;
  const requests = [];
  window.__cadWorkerRequests = requests;
  // Only the disposable diagnostic page calls this after recording failure.
  // Also terminate later workers immediately: queued cache/publication work
  // can otherwise start another isolate during failure diagnostics. Main-thread
  // callbacks can still drain; this is not proof that the whole page is idle.
  // It cannot make the failed run pass or affect the user's viewer.
  window.__cadStopMemoryProbeWorkers = () => {
    stopped = true;
    const count = liveWorkers.size;
    for (const worker of [...liveWorkers]) worker.terminate();
    return count;
  };
  window.Worker = class extends OriginalWorker {
    constructor(...args) {
      super(...args);
      liveWorkers.add(this);
      stats.created += 1;
      this.__probeId = stats.created;
      stats.live += 1;
      stats.peakLive = Math.max(stats.peakLive, stats.live);
      if (stopped) this.terminate();
      this.addEventListener?.('message', event => {
        const request = requests.find(item => item.worker === this.__probeId && item.id === event.data?.id);
        if (request) { request.finishedAt = performance.now(); request.ok = event.data?.ok; }
      });
    }
    postMessage(message, ...rest) {
      if (message?.type === 'loadSurf') {
        if (requests.length >= 128) requests.shift();
        requests.push({ worker: this.__probeId, id: message.id, url: String(message.url),
          startedAt: performance.now(), capabilities: { ...message.capabilities },
          tessellation: { ...message.tessellation }, cachedBytes: message.cachedEntry?.byteLength || 0 });
      }
      return super.postMessage(message, ...rest);
    }
    terminate() {
      if (!terminated.has(this)) {
        liveWorkers.delete(this);
        terminated.add(this);
        stats.terminated += 1;
        stats.live -= 1;
      }
      return super.terminate();
    }
  };
}
