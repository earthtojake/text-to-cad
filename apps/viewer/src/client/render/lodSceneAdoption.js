import { createLodPublication } from "./lodPublication.js";

const lodDisplaySources = new WeakMap();

function preservesLodPublicationGeometry(displaySource, publicationSource) {
  const displayedParts = displaySource?.parts;
  const publicationParts = publicationSource?.parts;
  return Array.isArray(displayedParts) && Array.isArray(publicationParts)
    && displayedParts.length === publicationParts.length
    && displayedParts.every((part, index) => {
      const published = publicationParts[index];
      return part?.id === published?.id
        && part?.occurrenceId === published?.occurrenceId
        && part?.componentId === published?.componentId
        && part?.sourceMesh === published?.sourceMesh
        && part?.transform === published?.transform;
    });
}

// Appearance-only display wrappers preserve the complete occurrence geometry,
// but are not themselves the exact composed source owned by the LOD publisher.
// Keep that relationship out of serialized mesh data and unwrap it before the
// ownership state machine compares, commits, or disposes a publication.
export function registerLodDisplaySource(displaySource, publicationSource) {
  if (displaySource && publicationSource && displaySource !== publicationSource
      && preservesLodPublicationGeometry(displaySource, publicationSource)) {
    lodDisplaySources.set(displaySource, lodDisplaySources.get(publicationSource) || publicationSource);
  }
  return displaySource;
}

function lodPublicationSource(source) {
  return lodDisplaySources.get(source) || source;
}

export function lodOccurrenceProof({ source, descriptor, componentId, componentMesh }) {
  const sourceIds = descriptor?.occurrences
    ? descriptor.occurrences.filter(row => row.component === componentId).map(row => row.id)
    : (source?.parts || []).filter(part => part.componentId === componentId).map(part => part.occurrenceId || part.id);
  const ids = new Set(sourceIds);
  const valid = ids.size > 0 && ids.size === sourceIds.length && sourceIds.every(Boolean);
  return candidate => {
    if (!valid) return false;
    const seen = new Set();
    for (const part of candidate?.parts || []) {
      if (part.componentId !== componentId) continue;
      const id = part.occurrenceId || part.id;
      if (!ids.has(id) || seen.has(id) || part.sourceMesh !== componentMesh) return false;
      seen.add(id);
    }
    return seen.size === ids.size;
  };
}

// Exact source/payload proof around the app-private ownership state machine.
// It acknowledges CPU/Three/accounting adoption, never GPU upload completion.
export function createLodSceneAdoption(options) {
  const tracker = createLodPublication(options);
  function expectBatch(spec) {
    const items = spec.items || [];
    if (!items.length || items.length > 4 || new Set(items.map(item => item.componentId)).size !== items.length)
      throw new Error("LOD publication requires one to four distinct components");
    const candidates = items.map(item => lodOccurrenceProof({ ...spec, ...item }));
    const bases = items.map(item => item.baseMesh ? lodOccurrenceProof({ ...spec, ...item, componentMesh: item.baseMesh }) : null);
    const keysMatch = items.every(item => !item.tessellationKey || item.componentMesh?.lodKey === item.tessellationKey);
    const candidate = source => keysMatch && candidates.every(proof => proof(source));
    const base = source => bases.every(proof => proof?.(source));
    return tracker.expect({ ...spec,
      matchesCandidate: source => source === (spec.currentSource?.() || spec.context.meshData) && candidate(source),
      matchesBase: source => source === (spec.currentBaseSource?.() || spec.baseSource) && base(source),
      recognizesCandidate: source => spec.candidateSources?.has(source) && candidate(source),
      recognizesBase: source => source === spec.baseSource || spec.baseSources?.has(source),
    });
  }
  return {
    ...tracker,
    expectBatch,
    expect: spec => expectBatch({ ...spec, items: [spec] }),
    adopted: source => tracker.adopted(lodPublicationSource(source)),
    disposed: (source, detail) => tracker.disposed(lodPublicationSource(source), detail),
    failed: (source, detail) => tracker.failed(lodPublicationSource(source), detail),
  };
}
