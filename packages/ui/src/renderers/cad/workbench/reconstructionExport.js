import { createReconstructionScene } from './reconstructionScene.js';

export function videoMimeType(Recorder = globalThis.MediaRecorder) {
  return ['video/mp4;codecs=avc1.42001E', 'video/webm;codecs=vp9', 'video/webm;codecs=vp8'].find(type => Recorder?.isTypeSupported(type)) || null;
}
export function exportFilename(label, extension) {
  return `${(label || 'Part').replace(/[<>:"/\\|?*\x00-\x1f]/g, '-').slice(0, 100)}-build-sequence.${extension}`;
}
function wait(ms, signal) {
  return new Promise((resolve, reject) => {
    signal.throwIfAborted();
    const abort = () => { clearTimeout(timer); reject(signal.reason); };
    const timer = setTimeout(() => { signal.removeEventListener('abort', abort); resolve(); }, ms);
    signal.addEventListener('abort', abort, { once: true });
  });
}
async function gifFrames(canvas, draw, count, signal, progress) {
  const worker = new Worker(new URL('./reconstructionGif.worker.js', import.meta.url), { type: 'module' });
  const send = (data, transfer = []) => new Promise((resolve, reject) => {
    signal.throwIfAborted();
    const done = (error, value) => { clearTimeout(timer); signal.removeEventListener('abort', abort); worker.onmessage = worker.onerror = null; error ? reject(error) : resolve(value); };
    const abort = () => done(signal.reason);
    const timer = setTimeout(() => done(new Error('GIF encoding timed out. Try again.')), 30000);
    worker.onmessage = e => done(e.data.error ? new Error(e.data.error) : null, e.data);
    worker.onerror = () => done(new Error('GIF encoding failed. Try again.'));
    signal.addEventListener('abort', abort, { once: true }); worker.postMessage(data, transfer);
  });
  try {
    for (let i = 0; i < count; i++) {
      signal.throwIfAborted(); draw(i);
      const rgba = canvas.getContext('2d').getImageData(0, 0, canvas.width, canvas.height).data.buffer;
      await send({ rgba, width: canvas.width, height: canvas.height, delay: i === count - 1 ? 1800 : 1000 }, [rgba]);
      progress(i + 1, count);
    }
    const { bytes } = await send({ finish: true });
    return new Blob([bytes], { type: 'image/gif' });
  } finally { worker.terminate(); }
}
async function videoFrames(canvas, draw, count, externalSignal, progress, mimeType) {
  const lifetime = new AbortController(), signal = lifetime.signal;
  const abort = () => lifetime.abort(externalSignal.reason);
  externalSignal.throwIfAborted(); externalSignal.addEventListener('abort', abort, { once: true });
  const stream = canvas.captureStream(12);
  let recorder, heartbeat;
  try {
    recorder = new globalThis.MediaRecorder(stream, { mimeType, videoBitsPerSecond: 4000000 });
    return await new Promise((resolve, reject) => {
      const chunks = [];
      recorder.ondataavailable = e => { if (e.data.size) chunks.push(e.data); };
      recorder.onerror = () => reject(new Error('Video recording failed. Try GIF instead.'));
      recorder.onstop = () => resolve(new Blob(chunks, { type: mimeType }));
      recorder.start();
      // Canvas streams emit frames on repaint. Repaint unchanged frames too so
      // quiet steps and the final hold keep their duration in the video.
      heartbeat = setInterval(() => canvas.getContext('2d').drawImage(canvas, 0, 0), 1000 / 12);
      void (async () => {
        for (let i = 0; i < count; i++) {
          signal.throwIfAborted(); draw(i); progress(i + 1, count);
          // Keep a stable canvas frame for each step, including the final solid.
          await wait(i === count - 1 ? 1800 : 1000, signal);
        }
        recorder.stop();
      })().catch(reject);
    });
  } finally {
    clearInterval(heartbeat);
    lifetime.abort(); externalSignal.removeEventListener('abort', abort);
    if (recorder?.state === 'recording') recorder.stop();
    stream.getTracks().forEach(track => track.stop());
  }
}

/** Export in an isolated scene: playback, selection and document geometry stay intact. */
export async function exportReconstruction({ data, label, format, camera, signal, onProgress = () => {} }) {
  signal.throwIfAborted();
  const mimeType = format === 'video' ? videoMimeType() : null;
  if (format === 'video' && !mimeType) throw new Error('Video export is unavailable in this browser. Use GIF instead.');
  const width = format === 'gif' ? 800 : 1280, height = Math.round(width * 9 / 16), footer = 64;
  const view = createReconstructionScene(data), canvas = document.createElement('canvas');
  canvas.width = width; canvas.height = height + footer;
  const ctx = canvas.getContext('2d');
  try {
    view.resize(width, height);
    if (camera) { view.camera.position.copy(camera.position); view.camera.quaternion.copy(camera.quaternion); view.camera.zoom = camera.zoom; view.camera.updateProjectionMatrix(); }
    const draw = i => {
      view.show(i); ctx.fillStyle = '#171717'; ctx.fillRect(0, 0, canvas.width, canvas.height);
      ctx.drawImage(view.renderer.domElement, 0, 0);
      ctx.fillStyle = '#fafafa'; ctx.font = '16px sans-serif';
      ctx.fillText(`${i + 1} / ${data.steps.length} · ${data.steps[i].label}`, 20, height + 24, width - 40);
      ctx.fillStyle = '#a3a3a3'; ctx.font = '12px sans-serif';
      const summary = data.tracks ? `${data.verified} verified components · ${data.staticParts} kept as original` : 'Reconstructed from STEP geometry';
      ctx.fillText(`${label} · ${summary}`, 20, height + 46, width - 40);
    };
    const blob = format === 'gif' ? await gifFrames(canvas, draw, data.steps.length, signal, onProgress) : await videoFrames(canvas, draw, data.steps.length, signal, onProgress, mimeType);
    signal.throwIfAborted();
    if (!blob.size) throw new Error('The export was empty. Try again.');
    return { blob, filename: exportFilename(label, format === 'gif' ? 'gif' : mimeType.startsWith('video/mp4') ? 'mp4' : 'webm') };
  } finally { view.dispose(); canvas.width = canvas.height = 0; }
}

export function downloadExport({ blob, filename }) {
  const url = URL.createObjectURL(blob), link = document.createElement('a');
  link.href = url; link.download = filename; document.body.appendChild(link); link.click(); link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 60000);
}
