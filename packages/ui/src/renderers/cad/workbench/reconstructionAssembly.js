import { resolvePackageAssetUrl } from '@hardcore/core/client';
import { loadRenderSurf } from '@hardcore/core/lib/renderAssetClient.js';
import { requestReconstruction } from './reconstructionClient.js';

/** Compose verified component sequences without inventing dependencies between parts. */
export function composeAssemblyPlayback(descriptor, tracks) {
  tracks = { ...tracks };
  const steps = [];
  let verified = 0, staticParts = 0;
  const occurrences = descriptor.occurrences.filter(o => tracks[o.component]);
  for (const component of new Set(occurrences.map(o => o.component))) {
    const track = tracks[component];
    if (!track.steps?.length) { if (track.reference.vertices.length) staticParts++; continue; }
    verified++;
    tracks[component] = { ...track, start: steps.length };
    const instances = occurrences.filter(o => o.component === component);
    const label = `${instances[0].name || 'Part'}${instances.length > 1 ? ` × ${instances.length}` : ''}`;
    for (const [index, step] of track.steps.entries()) steps.push({
      ...step, id: `${component}/${step.id}`, component, index,
      label: `${label} · ${step.label}`,
      dependsOn: step.dependsOn.map(id => `${component}/${id}`),
    });
  }
  if (!steps.length) throw new Error('No verified component sequences are available yet.');
  return { tracks, occurrences, steps, verified, staticParts,
    bounds: [...descriptor.bbox.min, ...descriptor.bbox.max] };
}

/** Other components remain in view, including ones with no complete reconstruction. */
export function assemblyPlaybackFrames(data, frame, original = false) {
  return data.occurrences.map(occurrence => {
    const track = data.tracks[occurrence.component];
    const index = frame - track.start;
    const active = !original && track.steps && index >= 0 && index < track.steps.length;
    const step = active ? track.steps[index] : null;
    const mesh = active ? step.solidFrame == null ? null : track.steps[step.solidFrame] : track.reference;
    const context = !original && frame < data.steps.length - 1 && !active;
    return { occurrence, mesh, lines: step?.lines || [], active, context };
  });
}

export async function loadAssemblyPlayback({ target, file, descriptor, results, statuses, meshUrl, signal, onProgress = () => {} }) {
  const tracks = {}, warnings = [];
  const components = [...new Set(descriptor.occurrences.map(o => o.component))];
  for (const [i, component] of components.entries()) {
    signal.throwIfAborted();
    onProgress(`Loading assembly playback · ${i + 1} of ${components.length} components`);
    if (statuses[component]?.state === 'ready' && results[component]?.recipe) {
      try {
        tracks[component] = await requestReconstruction({ target, file, component, recipe: results[component].recipe, signal });
        continue;
      } catch (error) { signal.throwIfAborted(); warnings.push(error.message); }
    }
    const surf = descriptor.components[component]?.surf;
    if (!surf) throw new Error('A component has no display geometry. Use individual part playback for this model.');
    // Reuse the viewer's worker/cache path; never tessellate on the UI thread.
    const reference = await loadRenderSurf(resolvePackageAssetUrl(meshUrl, surf), { signal });
    signal.throwIfAborted();
    tracks[component] = { reference };
  }
  return { ...composeAssemblyPlayback(descriptor, tracks), warnings };
}
