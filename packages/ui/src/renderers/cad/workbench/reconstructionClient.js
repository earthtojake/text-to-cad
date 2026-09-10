import { cadApiUrl } from '@hardcore/core/client';

export function reconstructionTarget(meshUrl) {
  const url = new URL(meshUrl, globalThis.location?.href || 'http://localhost');
  const tree = (url.searchParams.get('file') || '').split('/').filter(Boolean)[0];
  if (!/^[a-f0-9]{64}$/.test(tree)) return null;
  return { origin: url.origin, tree };
}

export async function requestReconstruction({ target, file, component, recipe, signal, preview = true }) {
  const response = await fetch(cadApiUrl('/__cad/reconstruction', { origin: target.origin, file }), {
    method: 'POST', signal, headers: { 'content-type': 'application/json', 'x-cadgen-viewer': '1' },
    body: JSON.stringify({ tree: target.tree, component, recipe, preview }),
  });
  const result = await response.json();
  if (!response.ok || result.status !== 'verified') throw new Error(result.error || 'A matching reconstruction could not be verified.');
  if (result.tree !== target.tree || result.component !== component || !result.proof?.passed || !(preview ? result.steps?.length : result.frameCount)) {
    throw new Error('The reconstruction does not match the selected part.');
  }
  return result;
}
