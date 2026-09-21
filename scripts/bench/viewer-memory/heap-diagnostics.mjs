// Optional profiling and failure-side collection for this harness's own page.
// Numeric summaries only: probes never keep transferred mesh/cache payloads.
export function installCacheWriteProbe() {
  const original = window.fetch;
  const stats = { active: 0, activeBytes: 0, peakActive: 0, peakBytes: 0, total: 0, totalBytes: 0 };
  window.__cadCacheWriteProbe = stats;
  window.fetch = async function(input, init) {
    const url = String(input?.url || input);
    const tracked = String(init?.method || input?.method || 'GET').toUpperCase() === 'POST'
      && url.includes('/__tess_cache/') && !url.endsWith('/batch');
    if (!tracked) return original.apply(this, arguments);
    const size = Number(init?.body?.byteLength ?? init?.body?.size) || 0;
    stats.active += 1;
    stats.activeBytes += size;
    stats.total += 1;
    stats.totalBytes += size;
    stats.peakActive = Math.max(stats.peakActive, stats.active);
    stats.peakBytes = Math.max(stats.peakBytes, stats.activeBytes);
    try { return await original.apply(this, arguments); }
    finally { stats.active -= 1; stats.activeBytes -= size; }
  };
}

export function summarizeSamplingProfile(profile, limit = 30) {
  const rows = [];
  const visit = (node, parents) => {
    const frame = node.callFrame || {};
    const name = `${frame.functionName || '(anonymous)'} ${frame.url || ''}:${(frame.lineNumber ?? -1) + 1}`;
    if (node.selfSize > 0) rows.push({ bytes: node.selfSize, site: name, callers: parents.slice(-5) });
    for (const child of node.children || []) visit(child, [...parents, name]);
  };
  if (profile?.head) visit(profile.head, []);
  rows.sort((a, b) => b.bytes - a.bytes);
  return { sampledBytes: rows.reduce((sum, row) => sum + row.bytes, 0), sites: rows.length, largestSites: rows.slice(0, limit) };
}

async function requestSourceHints(requests, origin) {
  const recent = [...new Map((requests || []).slice(-8).map(row => [row.url, row])).values()];
  return Promise.all(recent.map(async row => {
    const hint = { worker: row.worker, requestId: row.id, url: row.url, tessellation: row.tessellation };
    try {
      const response = await fetch(new URL(row.url, origin), { method: 'HEAD', signal: AbortSignal.timeout(1500) });
      const bytes = Number(response.headers.get('content-length'));
      return { ...hint, status: response.status, sourceBytes: response.ok && bytes > 0 ? bytes : null };
    } catch (error) { return { ...hint, error: String(error.message || error) }; }
  }));
}

async function workerHeap(cdp, target, bounded) {
  let sessionId;
  let listener;
  try {
    ({ sessionId } = await bounded(cdp.send('Target.attachToTarget', { targetId: target.targetId, flatten: false }), 1500));
    const reply = new Promise((resolve, reject) => {
      listener = event => {
        if (event.sessionId !== sessionId) return;
        const message = JSON.parse(event.message);
        if (message.id !== 1) return;
        if (message.error) reject(new Error(message.error.message));
        else resolve(message.result);
      };
      cdp.on('Target.receivedMessageFromTarget', listener);
    });
    const [, heap] = await Promise.all([
      bounded(cdp.send('Target.sendMessageToTarget', {
        sessionId, message: JSON.stringify({ id: 1, method: 'Runtime.getHeapUsage' }),
      }), 1500),
      bounded(reply, 1500),
    ]);
    return { targetId: target.targetId, url: target.url, ...heap };
  } catch (error) {
    return { targetId: target.targetId, url: target.url, error: String(error.message || error) };
  } finally {
    if (listener) cdp.off('Target.receivedMessageFromTarget', listener);
    if (sessionId) await bounded(cdp.send('Target.detachFromTarget', { sessionId }), 500).catch(() => {});
  }
}

export async function collectHeapDiagnostics({ page, cdp, bounded, sampleRss, failed, sampling }) {
  const result = { failureSide: failed, workersStopped: false, mainThreadQuiescenceVerified: false, errors: [] };
  const attempt = async (label, operation) => {
    try { return await operation(); }
    catch (error) { result.errors.push({ phase: label, error: String(error.message || error) }); return null; }
  };
  result.before = { rss: sampleRss(), page: await attempt('before-page', () => bounded(cdp.send('Runtime.getHeapUsage'), 2000)) };
  result.before.dom = await attempt('before-dom', () => bounded(cdp.send('Memory.getDOMCounters'), 1500));
  const { targetInfos } = await bounded(cdp.send('Target.getTargets'), 1500).catch(() => ({ targetInfos: [] }));
  result.before.workers = await Promise.all(targetInfos.filter(target => target.type === 'worker').slice(0, 8)
    .map(target => workerHeap(cdp, target, bounded)));
  if (sampling) {
    const profile = await attempt('before-sampling', () => bounded(cdp.send('HeapProfiler.getSamplingProfile'), 2000));
    if (profile) result.before.sampling = summarizeSamplingProfile(profile.profile);
  }
  if (failed) {
    result.stoppedWorkers = await attempt('stop-workers', () => bounded(page.evaluate(() => window.__cadStopMemoryProbeWorkers?.() || 0), 1000));
    result.workersStopped = result.stoppedWorkers !== null;
  }
  await attempt('collect-garbage', () => bounded(cdp.send('HeapProfiler.collectGarbage'), 2500));
  await new Promise(resolve => setTimeout(resolve, 1000));
  // Already-queued publications can allocate during the settling interval.
  // Collect again before sampling; the former GC-then-wait sample mixed retained
  // objects with that new garbage. Even this bounded drain is not an idle proof.
  await attempt('collect-garbage-after-settle', () => bounded(cdp.send('HeapProfiler.collectGarbage'), 2500));
  result.after = {
    rss: sampleRss(),
    page: await attempt('after-page', () => bounded(cdp.send('Runtime.getHeapUsage'), 2000)),
    dom: await attempt('after-dom', () => bounded(cdp.send('Memory.getDOMCounters'), 1500)),
    state: await attempt('after-state', () => bounded(page.evaluate(() => ({
      heapUsed: performance.memory?.usedJSHeapSize || 0,
      workers: window.__cadWorkerProbe ? { ...window.__cadWorkerProbe } : null,
      workerRequests: window.__cadWorkerRequests || [],
      cacheWrites: window.__cadCacheWriteProbe ? { ...window.__cadCacheWriteProbe } : null,
      owned: window.__cadRenderMemoryProbe?.() || null,
    })), 1500)) || {},
  };
  if (sampling) {
    const profile = await attempt('after-sampling', () => bounded(cdp.send('HeapProfiler.stopSampling'), 2000));
    if (profile) result.after.sampling = summarizeSamplingProfile(profile.profile);
  }
  result.sourceHints = await requestSourceHints(result.after.state.workerRequests, page.url());
  return result;
}
