// Harness-only native Resource Timing. No fetch wrapper, response clones or
// per-request observer allocations; the browser owns a bounded entry buffer.
export function installViewerResourceTiming() {
  const state = { bufferSize: 8192, maxReportedEntries: 4096, bufferFullEvents: 0, installed: false };
  window.__cadResourceTimingProbe = state;
  try {
    performance.setResourceTimingBufferSize(state.bufferSize);
    performance.addEventListener('resourcetimingbufferfull', () => { state.bufferFullEvents++; });
    state.installed = true;
  } catch (error) { state.error = String(error.message || error); }
}

// Called after the acceptance grade. Timing fields share the window's time
// origin with the worker postMessage and LOD/adoption probes. A worker's own
// fetch timeline is separate and is deliberately not intercepted here.
export function collectViewerResourceTiming({ cutoffEpochMs } = {}) {
  const state = window.__cadResourceTimingProbe || {};
  const origin = window.location.origin;
  const cutoffAt = Number.isFinite(cutoffEpochMs) ? cutoffEpochMs - performance.timeOrigin : performance.now();
  const fields = ['startTime', 'duration', 'workerStart', 'fetchStart', 'domainLookupStart',
    'domainLookupEnd', 'connectStart', 'secureConnectionStart', 'connectEnd', 'requestStart',
    'responseStart', 'responseEnd', 'transferSize', 'encodedBodySize', 'decodedBodySize', 'responseStatus'];
  const all = performance.getEntriesByType('resource');
  const entries = [];
  let matchingEntries = 0, afterCutoffEntries = 0;
  for (const item of all) {
    let url;
    try { url = new URL(item.name, origin); } catch { continue; }
    if (url.origin !== origin) continue;
    let route, key;
    if (url.pathname === '/__tess_cache/batch') {
      route = 'tess-batch'; key = '';
    } else if (url.pathname.startsWith('/__tess_cache/') && url.pathname.endsWith('.tess')) {
      route = 'tess-entry'; key = url.pathname.slice('/__tess_cache/'.length);
    } else {
      const file = url.pathname === '/__cad/store' ? url.searchParams.get('file') : url.pathname;
      if (!file?.endsWith('.surf')) continue;
      route = 'surf'; key = file.split('/').at(-1);
    }
    if (Number.isFinite(item.responseEnd) && item.responseEnd > cutoffAt) { afterCutoffEntries++; continue; }
    matchingEntries++;
    if (entries.length >= (state.maxReportedEntries || 4096)) continue;
    // Route/key are bounded identifiers, not full model paths or response data.
    const entry = { route, key: key.slice(0, 512), initiatorType: String(item.initiatorType || '').slice(0, 40),
      nextHopProtocol: String(item.nextHopProtocol || '').slice(0, 40) };
    for (const field of fields) entry[field] = Number.isFinite(item[field]) ? item[field] : null;
    entries.push(entry);
  }
  return { ...state, collectedAfterGrade: true, collectedAt: performance.now(), timeOrigin: performance.timeOrigin,
    cutoffAt, totalBufferedEntries: all.length, matchingEntries, afterCutoffEntries,
    truncated: (state.bufferFullEvents || 0) > 0 || matchingEntries > entries.length,
    coverage: 'Window same-origin tess-cache and SURF requests only. Worker-owned SURF fetches have separate timelines and are absent. No HTTP method, server CPU, JS arrayBuffer materialization, dispatch/adoption or GPU completion timing is inferred. Zero/unsupported timing fields are preserved. Entries ending after the grade are excluded; incomplete requests may be absent.',
    entries };
}
