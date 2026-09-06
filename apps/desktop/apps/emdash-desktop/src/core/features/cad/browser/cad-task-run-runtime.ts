export interface CadTaskRunOwnership {
  projectId: string;
  taskId: string;
  contextKey: string;
  runId: string;
  conversationId: string;
  messageCountBeforeSubmit: number;
}

interface RegisteredRefreshHandler {
  token: symbol;
  refresh: () => void;
}

const ownershipByModel = new Map<string, CadTaskRunOwnership>();
const sourceRunOwnershipByModel = new Map<string, string>();
const refreshHandlers = new Map<string, RegisteredRefreshHandler>();
const focusedArtifactByTask = new Map<string, string>();

function taskKey(input: { projectId: string; taskId: string }): string {
  return `${input.projectId}\0${input.taskId}`;
}

function modelKey(input: { projectId: string; taskId: string; contextKey: string }): string {
  return `${input.projectId}\0${input.taskId}\0${input.contextKey}`;
}

export function recordCadTaskRunOwnership(ownership: CadTaskRunOwnership): void {
  ownershipByModel.set(modelKey(ownership), ownership);
}

export function getCadTaskRunOwnership(input: {
  projectId: string;
  taskId: string;
  contextKey: string;
}): CadTaskRunOwnership | undefined {
  return ownershipByModel.get(modelKey(input));
}

export function clearCadTaskRunOwnership(
  input: { projectId: string; taskId: string; contextKey: string },
  runId: string
): void {
  const key = modelKey(input);
  if (ownershipByModel.get(key)?.runId === runId) ownershipByModel.delete(key);
}

export function acquireCadSourceRunOwnership(
  input: { projectId: string; taskId: string; contextKey: string },
  runId: string
): boolean {
  const key = modelKey(input);
  const existing = sourceRunOwnershipByModel.get(key);
  if (existing && existing !== runId) return false;
  sourceRunOwnershipByModel.set(key, runId);
  return true;
}

export function isCadSourceRunLocallyOwned(
  input: { projectId: string; taskId: string; contextKey: string },
  runId: string
): boolean {
  return sourceRunOwnershipByModel.get(modelKey(input)) === runId;
}

export function clearCadSourceRunOwnership(
  input: { projectId: string; taskId: string; contextKey: string },
  runId: string
): void {
  const key = modelKey(input);
  if (sourceRunOwnershipByModel.get(key) === runId) sourceRunOwnershipByModel.delete(key);
}

export function recordFocusedCadArtifact(input: {
  projectId: string;
  taskId: string;
  contextKey: string;
}): void {
  focusedArtifactByTask.set(taskKey(input), input.contextKey);
}

export function getFocusedCadArtifact(input: {
  projectId: string;
  taskId: string;
}): string | undefined {
  return focusedArtifactByTask.get(taskKey(input));
}

export function registerCadTaskRunRefreshHandler(
  input: { projectId: string; taskId: string; contextKey: string },
  refresh: () => void
): () => void {
  const key = modelKey(input);
  const token = Symbol(key);
  refreshHandlers.set(key, { token, refresh });
  return () => {
    if (refreshHandlers.get(key)?.token === token) refreshHandlers.delete(key);
  };
}

export function refreshCadTaskRunArtifact(input: {
  projectId: string;
  taskId: string;
  contextKey: string;
}): void {
  refreshHandlers.get(modelKey(input))?.refresh();
}

/** Test-only reset for renderer-local run ownership. */
export function resetCadTaskRunRuntimeForTests(): void {
  ownershipByModel.clear();
  sourceRunOwnershipByModel.clear();
  refreshHandlers.clear();
  focusedArtifactByTask.clear();
}
