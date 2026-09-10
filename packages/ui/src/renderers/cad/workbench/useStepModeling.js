import { useMemo } from 'react';
import { entryAssetUrl } from '@hardcore/core/lib/entryAssets.js';
import { reconstructionTarget } from './reconstructionClient.js';
import { useModelingRecognition } from './useModelingRecognition.js';
import { useAutomaticReconstruction } from './useAutomaticReconstruction.js';

/** Owned by the STEP document, outside the inspector portal, including when closed. */
export function useStepModeling(entry, enabled, reconstructionEnabled, preferredOccurrenceId) {
  const meshUrl = entryAssetUrl(entry, 'glb');
  const target = useMemo(() => reconstructionTarget(meshUrl), [meshUrl]);
  const recognition = useModelingRecognition(meshUrl, enabled);
  const preferredComponent = recognition.descriptor?.occurrences.find(o => o.id === preferredOccurrenceId)?.component;
  const { statuses, retry } = useAutomaticReconstruction({
    target, file: entry?.file, results: recognition.results, preferredComponent,
    enabled: enabled && reconstructionEnabled,
  });
  return { ...recognition, target, statuses, retryVerification: retry };
}
