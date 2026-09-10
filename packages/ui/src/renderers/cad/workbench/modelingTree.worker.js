import { parseSurf } from '@hardcore/core/lib/surf/container.js';
import { buildModelingTree } from './modelingTree.js';

// One requested component, bounded input, and a disposable worker. Never generate CAD.
const MAX_BYTES = 16 * 1024 * 1024;
self.onmessage = async ({ data: { url } }) => {
  try {
    const response = await fetch(url);
    if (!response.ok) throw new Error('Could not read this part’s geometry. Try again.');
    if (Number(response.headers.get('content-length')) > MAX_BYTES) throw new Error('This part exceeds the prototype’s analysis limit.');
    const reader = response.body.getReader(), chunks = [];
    let size = 0;
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      size += value.byteLength;
      if (size > MAX_BYTES) { await reader.cancel(); throw new Error('This part exceeds the prototype’s analysis limit.'); }
      chunks.push(value);
    }
    const bytes = new Uint8Array(size);
    let offset = 0;
    for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.byteLength; }
    const { index, floats } = parseSurf(bytes.buffer);
    const tree = buildModelingTree(index, floats);
    self.postMessage({ tree, hasFaces: index.faces.length > 0 });
  } catch (error) {
    self.postMessage({ error: error instanceof Error ? error.message : 'Could not infer a modeling tree.' });
  }
};
