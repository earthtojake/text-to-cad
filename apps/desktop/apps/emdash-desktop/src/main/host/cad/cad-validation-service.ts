import { execFile, type ChildProcess } from 'node:child_process';
import { createHash } from 'node:crypto';
import { existsSync, readFileSync } from 'node:fs';
import { isAbsolute, join, relative, resolve, sep } from 'node:path';
import { promisify } from 'node:util';
import type { CadValidationResult } from '@core/features/browser/api';
import { cadToolEnvironment } from '@main/host/cad/cad-python-environment';
import {
  cadSourceRebuildToolPlan as recipeRebuildToolPlan,
  linkedSourceFromCadgenRecord,
  normalizeCadArtifactRelationship,
  resolveCadBuildArtifactPath,
  resolveCadSourceArtifactRelationship,
  type CadRuntimeCommand,
} from '@main/host/cad/cad-recipe';
import { findCadPythonExecutable, provisionCadRuntime } from '@main/host/cad/cad-runtime-service';
import { log } from '@main/lib/logger';

const execFileAsync = promisify(execFile);
const VALIDATION_TIMEOUT_MS = 120_000;
const REBUILD_TIMEOUT_MS = 10 * 60_000;
const MAX_OUTPUT_BYTES = 5 * 1024 * 1024;
interface CadValidationInFlight {
  revision: string;
  promise: Promise<CadValidationResult>;
}

const validationInFlight = new Map<string, CadValidationInFlight>();
const runningCadProcesses = new Set<ChildProcess>();
const recentValidation = new Map<string, CadValidationResult>();
const cadArtifactOperationTails = new Map<string, Promise<void>>();
const cadArtifactRebuildCounts = new Map<string, number>();

type CadArtifactTarget =
  | {
      success: true;
      workspacePath: string;
      relativeModelPath: string;
      relativeSourcePath?: string;
    }
  | { success: false; error: string };

export type CadArtifactTargetInput = {
  workspacePath: string;
  filePath: string;
  /** Persisted model-catalog provenance; preferred over cadgen's cache record. */
  sourcePath?: string;
};

export function validateCadModel(input: CadArtifactTargetInput): Promise<CadValidationResult> {
  const key = cadArtifactOperationKey(input);
  const existing = validationInFlight.get(key);
  const requestedRevision = cadValidationInputRevision(input);
  const rebuildQueued = (cadArtifactRebuildCounts.get(key) ?? 0) > 0;
  if (!rebuildQueued && existing?.revision === requestedRevision) return existing.promise;
  const cached = recentValidation.get(key);
  if (!rebuildQueued && cached?.success && cadValidationResultIsCurrent(input, cached)) {
    return Promise.resolve(cached);
  }
  // A prior inspection may still be building derived render metadata. Queue
  // the newer artifact revision behind it rather than sharing stale facts.
  const pending = enqueueCadArtifactOperation(key, () => validateCadModelOnce(input));
  const cleanup = () => {
    if (validationInFlight.get(key)?.promise === pending) validationInFlight.delete(key);
  };
  validationInFlight.set(key, { revision: requestedRevision, promise: pending });
  void pending.then((result) => {
    if (result.success) recentValidation.set(key, result);
    cleanup();
  }, cleanup);
  return pending;
}

/**
 * Explicitly runs an authored Python recipe before inspecting the STEP it
 * produced. Normal open/restart validation must use validateCadModel instead;
 * that path treats the accepted STEP as immutable input and never runs Python.
 */
export function rebuildCadModel(input: {
  workspacePath: string;
  filePath: string;
}): Promise<CadValidationResult> {
  const key = cadArtifactOperationKey(input);
  cadArtifactRebuildCounts.set(key, (cadArtifactRebuildCounts.get(key) ?? 0) + 1);
  return enqueueCadArtifactOperation(key, () => rebuildCadModelOnce(input)).finally(() => {
    const remaining = (cadArtifactRebuildCounts.get(key) ?? 1) - 1;
    if (remaining > 0) cadArtifactRebuildCounts.set(key, remaining);
    else cadArtifactRebuildCounts.delete(key);
  });
}

export function cadArtifactOperationKey(input: CadArtifactTargetInput): string {
  const workspacePath = resolve(input.workspacePath);
  const requestedPath = isAbsolute(input.filePath)
    ? resolve(input.filePath)
    : resolve(workspacePath, input.filePath);
  const modelPath = isPythonModelPath(requestedPath)
    ? cadSourceOutputPath(workspacePath, requestedPath)
    : requestedPath;
  return `${workspacePath}\0${modelPath}`;
}

/**
 * Resolve the artifact a recipe declares without executing it. cadgen requires
 * `out=` to be a string literal, so this lightweight import / decorator scan
 * can give a custom output the same mutex as direct STEP validation before
 * Python runs.
 */
function cadSourceOutputPath(workspacePath: string, sourcePath: string): string {
  const relationship = resolveCadSourceArtifactRelationship({ workspacePath, sourcePath });
  return relationship
    ? join(relationship.workspacePath, relationship.relativeModelPath)
    : resolve(workspacePath, defaultModelPath(relative(workspacePath, sourcePath)));
}

export function enqueueCadArtifactOperation<T>(
  key: string,
  operation: () => Promise<T>
): Promise<T> {
  const previous = cadArtifactOperationTails.get(key) ?? Promise.resolve();
  const result = previous.catch(() => undefined).then(operation);
  const tail = result.then(
    () => undefined,
    () => undefined
  );
  cadArtifactOperationTails.set(key, tail);
  void tail.then(() => {
    if (cadArtifactOperationTails.get(key) === tail) cadArtifactOperationTails.delete(key);
  });
  return result;
}

export function cadValidationInputRevision(input: CadArtifactTargetInput): string {
  const target = resolveCadArtifactTarget(input);
  if (!target.success) return 'missing';
  try {
    const modelHash = sha256(join(target.workspacePath, target.relativeModelPath));
    const sourceState = target.relativeSourcePath
      ? optionalFileHash(join(target.workspacePath, target.relativeSourcePath))
      : 'unlinked';
    return `${modelHash}:${sourceState}`;
  } catch {
    return 'unreadable';
  }
}

function cadValidationResultIsCurrent(
  input: CadArtifactTargetInput,
  result: Extract<CadValidationResult, { success: true }>
): boolean {
  try {
    const target = resolveCadArtifactTarget(input);
    if (
      !target.success ||
      result.artifact.modelPath !== target.relativeModelPath ||
      result.artifact.sourcePath !== target.relativeSourcePath
    ) {
      return false;
    }
    const modelPath = join(target.workspacePath, result.artifact.modelPath);
    if (!existsSync(modelPath) || sha256(modelPath) !== result.artifact.modelHash) return false;
    const sourcePath = result.artifact.sourcePath;
    if (!sourcePath) return true;
    const absoluteSourcePath = join(target.workspacePath, sourcePath);
    if (!result.artifact.sourceHash) return !existsSync(absoluteSourcePath);
    return (
      existsSync(absoluteSourcePath) && sha256(absoluteSourcePath) === result.artifact.sourceHash
    );
  } catch {
    return false;
  }
}

async function validateCadModelOnce(input: CadArtifactTargetInput): Promise<CadValidationResult> {
  const target = resolveCadArtifactTarget(input);
  if (!target.success) return target;

  const runtime = await prepareCadRuntime();
  if (!runtime.success) return runtime;

  try {
    const beforeHash = sha256(join(target.workspacePath, target.relativeModelPath));
    const result = await inspectCadArtifact(
      runtime.python,
      target.workspacePath,
      target.relativeModelPath,
      target.relativeSourcePath
    );
    const afterHash = sha256(join(target.workspacePath, target.relativeModelPath));
    if (afterHash !== beforeHash) {
      throw new Error('The canonical STEP changed while it was being inspected.');
    }
    return result;
  } catch (error) {
    return { success: false, error: validationErrorMessage(error) };
  }
}

async function rebuildCadModelOnce(input: {
  workspacePath: string;
  filePath: string;
}): Promise<CadValidationResult> {
  const target = validateSourceTarget(input);
  if (!target.success) return target;
  log.info(
    { workspacePath: target.workspacePath, recipe: target.relativeFilePath },
    'cad: rebuild requested'
  );
  if (!isPythonModelPath(target.relativeFilePath)) {
    return { success: false, error: 'A source rebuild requires a Python @step model.' };
  }

  const runtime = await prepareCadRuntime();
  if (!runtime.success) return runtime;

  try {
    const buildCommand = cadSourceRebuildToolPlan(target.relativeFilePath);
    const build = await runCadCommand(
      runtime.python,
      target.workspacePath,
      buildCommand.tool,
      buildCommand.args,
      REBUILD_TIMEOUT_MS
    );
    if (build.outcome === 'contended') {
      throw new Error('Another build of this model is still running. Try again when it finishes.');
    }
    const modelPath = cadValidationModelPath(target.workspacePath, target.relativeFilePath, build);
    return inspectCadArtifact(
      runtime.python,
      target.workspacePath,
      modelPath,
      target.relativeFilePath
    );
  } catch (error) {
    return { success: false, error: validationErrorMessage(error) };
  }
}

async function prepareCadRuntime(): Promise<
  { success: true; python: string } | { success: false; error: string }
> {
  let python = findCadPythonExecutable();
  if (!python) {
    try {
      await provisionCadRuntime();
    } catch (error) {
      return {
        success: false,
        error: `Could not prepare the CAD environment: ${errorMessage(error)}`,
      };
    }
    python = findCadPythonExecutable();
  }
  if (!python) {
    return { success: false, error: 'The CAD Python environment is incomplete.' };
  }
  return { success: true, python };
}

async function inspectCadArtifact(
  python: string,
  workspacePath: string,
  modelPath: string,
  sourcePath?: string
): Promise<Extract<CadValidationResult, { success: true }>> {
  const inspectionResults: Record<string, unknown>[] = [];
  for (const command of cadInspectionToolPlan(modelPath)) {
    inspectionResults.push(await runCadCommand(python, workspacePath, command.tool, command.args));
  }
  const [refs = {}, validation = {}] = inspectionResults;
  const token = Array.isArray(refs.tokens) ? refs.tokens[0] : undefined;
  const summary = isRecord(token) && isRecord(token.summary) ? token.summary : {};
  const entryFacts = isRecord(token) && isRecord(token.entryFacts) ? token.entryFacts : {};
  return {
    success: true,
    artifact: cadArtifactIdentity(workspacePath, modelPath, sourcePath),
    facts: {
      occurrenceCount: numberValue(summary.occurrenceCount),
      faceCount: numberValue(summary.faceCount),
      size: numberTuple(entryFacts.size),
    },
    validation,
  };
}

export type { CadRuntimeCommand } from '@main/host/cad/cad-recipe';
export { cadToolEnvironment } from '@main/host/cad/cad-python-environment';

export function cadSourceRebuildToolPlan(relativeFilePath: string): CadRuntimeCommand {
  return recipeRebuildToolPlan(relativeFilePath);
}

export function cadInspectionToolPlan(modelPath: string): CadRuntimeCommand[] {
  return [
    {
      tool: 'cadgen',
      args: ['step', 'inspect', 'refs', modelPath, '--facts', '--planes', '--positioning'],
    },
    { tool: 'cadgen', args: ['step', 'inspect', 'validate', modelPath] },
  ];
}

export function cadArtifactIdentity(workspacePath: string, modelPath: string, sourcePath?: string) {
  const absoluteModelPath = join(workspacePath, modelPath);
  if (!existsSync(absoluteModelPath)) {
    throw new Error(`Canonical CAD artifact does not exist: ${absoluteModelPath}`);
  }
  const modelHash = sha256(absoluteModelPath);
  const sourceHash = sourcePath ? optionalFileHash(join(workspacePath, sourcePath)) : undefined;
  return {
    // The accepted on-disk artifact is canonical. Source identity remains
    // attached for staleness/conflict checks but does not redefine the model
    // revision independently of the STEP bytes.
    revisionId: `sha256:${modelHash}`,
    modelPath,
    modelHash,
    ...(sourcePath ? { sourcePath } : {}),
    ...(sourceHash ? { sourceHash } : {}),
  };
}

function sha256(path: string): string {
  return createHash('sha256').update(readFileSync(path)).digest('hex');
}

function optionalFileHash(path: string): string | undefined {
  return existsSync(path) ? sha256(path) : undefined;
}

/**
 * Resolves the immutable artifact inspected by normal open/restart validation.
 * A Python path is accepted only as a link to its declared STEP; the recipe is
 * never executed here.
 */
export function resolveCadArtifactTarget(input: CadArtifactTargetInput): CadArtifactTarget {
  const workspacePath = resolve(input.workspacePath);
  const requestedFilePath = resolveWorkspaceFilePath(workspacePath, input.filePath);
  const requestedRelativePath = relative(workspacePath, requestedFilePath);
  if (!isSafeWorkspaceRelativePath(requestedRelativePath)) {
    return { success: false, error: 'CAD files must be inside the active model workspace.' };
  }

  let modelPath: string;
  let sourcePath: string | undefined;
  if (/\.(?:step|stp)$/i.test(requestedFilePath)) {
    modelPath = requestedFilePath;
    sourcePath =
      linkedSourceForStep(workspacePath, requestedFilePath, input.sourcePath) ?? undefined;
  } else if (isPythonModelPath(requestedFilePath)) {
    modelPath = cadSourceOutputPath(workspacePath, requestedFilePath);
    sourcePath = requestedFilePath;
  } else {
    return {
      success: false,
      error: 'Artifact validation requires a canonical STEP/STP file.',
    };
  }

  const relativeModelPath = relative(workspacePath, modelPath);
  if (!isSafeWorkspaceRelativePath(relativeModelPath)) {
    return { success: false, error: 'CAD files must be inside the active model workspace.' };
  }
  if (!existsSync(modelPath)) {
    return {
      success: false,
      error: `Canonical CAD artifact does not exist: ${modelPath}. Rebuild its source explicitly to create it.`,
    };
  }

  const relativeSourcePath = sourcePath ? relative(workspacePath, sourcePath) : undefined;
  return {
    success: true,
    workspacePath,
    relativeModelPath,
    ...(relativeSourcePath && isSafeWorkspaceRelativePath(relativeSourcePath)
      ? { relativeSourcePath }
      : {}),
  };
}

function validateSourceTarget(input: {
  workspacePath: string;
  filePath: string;
}):
  | { success: true; workspacePath: string; relativeFilePath: string }
  | { success: false; error: string } {
  const workspacePath = resolve(input.workspacePath);
  const requestedFilePath = resolveWorkspaceFilePath(workspacePath, input.filePath);
  const filePath = requestedFilePath;
  const relativeFilePath = relative(workspacePath, filePath);
  if (!isSafeWorkspaceRelativePath(relativeFilePath)) {
    return { success: false, error: 'CAD files must be inside the active model workspace.' };
  }
  if (!existsSync(filePath))
    return { success: false, error: `CAD file does not exist: ${filePath}` };
  return { success: true, workspacePath, relativeFilePath };
}

/**
 * The recipe behind an accepted STEP, in order of trust: the model catalog's
 * persisted association, cadgen's own provenance record (verified both ways
 * against the recipe's declared output), then the legacy `.step.py` sibling.
 * A same-stem `.py` beside an imported STEP is never assumed to own it, and
 * the `.step.json` sidecar carries declarations only, never source identity.
 */
function linkedSourceForStep(
  workspacePath: string,
  filePath: string,
  explicitSourcePath?: string
): string | null {
  if (!/\.(?:step|stp)$/i.test(filePath)) return null;
  const stepRelativePath = relative(workspacePath, filePath);
  if (!isSafeWorkspaceRelativePath(stepRelativePath)) return null;

  if (explicitSourcePath) {
    const relationship = normalizeCadArtifactRelationship({
      workspacePath,
      modelPath: filePath,
      sourcePath: explicitSourcePath,
    });
    if (relationship) {
      const sourcePath = join(workspacePath, relationship.relativeSourcePath);
      if (existsSync(sourcePath)) return sourcePath;
    }
  }

  const recorded = linkedSourceFromCadgenRecord({ workspacePath, modelPath: filePath });
  if (recorded) return join(workspacePath, recorded.relativeSourcePath);

  // Preserve the old artifact.step.py naming convention as a bounded legacy
  // compatibility link. Legacy recipes remain read-only until renamed.
  const legacySibling = `${filePath}.py`;
  return existsSync(legacySibling) ? legacySibling : null;
}

function isSafeWorkspaceRelativePath(path: string): boolean {
  return Boolean(path) && !path.startsWith(`..${sep}`) && !isAbsolute(path);
}

function resolveWorkspaceFilePath(workspacePath: string, filePath: string): string {
  return isAbsolute(filePath) ? resolve(filePath) : resolve(workspacePath, filePath);
}

async function runCadCommand(
  python: string,
  cwd: string,
  tool: CadRuntimeCommand['tool'],
  args: string[],
  timeout = VALIDATION_TIMEOUT_MS
): Promise<Record<string, unknown>> {
  const pythonArgs = tool === 'model' ? args : ['-m', 'cadgen.cli', ...args];
  log.info({ cwd, tool, args }, 'cad: running python');
  const pending = execFileAsync(python, pythonArgs, {
    cwd,
    timeout,
    maxBuffer: MAX_OUTPUT_BYTES,
    env: cadToolEnvironment(),
  });
  // Track the child so an app exit terminates an in-flight build instead of
  // leaving an orphaned run to overwrite the accepted STEP later.
  runningCadProcesses.add(pending.child);
  let result: { stdout: string };
  try {
    result = await pending;
  } finally {
    runningCadProcesses.delete(pending.child);
  }
  const line = result.stdout
    .trim()
    .split('\n')
    .map((candidate) => candidate.trim())
    .filter(Boolean)
    .at(-1);
  if (!line)
    throw new Error(
      tool === 'model'
        ? 'The recipe produced no build result. Call its parameterless @step function from an if __name__ == "__main__": block.'
        : 'CAD tool returned no result.'
    );
  const parsed: unknown = JSON.parse(line);
  if (!isRecord(parsed) || parsed.ok !== true) throw new Error('CAD tool did not pass.');
  return parsed;
}

export function cadValidationModelPath(
  workspacePath: string,
  relativeFilePath: string,
  build: Record<string, unknown>
): string {
  if (!isPythonModelPath(relativeFilePath)) return relativeFilePath;
  return resolveCadBuildArtifactPath({
    workspacePath,
    relativeSourcePath: relativeFilePath,
    build,
  });
}

function defaultModelPath(sourcePath: string): string {
  if (/\.(?:step|stp)\.py$/i.test(sourcePath)) return sourcePath.slice(0, -3);
  return sourcePath.replace(/\.py$/i, '.step');
}

function isPythonModelPath(path: string): boolean {
  return path.toLowerCase().endsWith('.py');
}

export function terminateRunningCadProcesses(): void {
  for (const child of runningCadProcesses) {
    if (child.exitCode === null && child.signalCode === null) child.kill('SIGTERM');
  }
  runningCadProcesses.clear();
}

process.once('exit', terminateRunningCadProcesses);

function validationErrorMessage(error: unknown): string {
  if (isRecord(error)) {
    const stdout = typeof error.stdout === 'string' ? error.stdout.trim() : '';
    if (stdout) {
      const lastLine = stdout
        .split('\n')
        .map((line) => line.trim())
        .filter(Boolean)
        .at(-1);
      try {
        const parsed: unknown = JSON.parse(lastLine ?? stdout);
        if (isRecord(parsed)) {
          const failureCount = numberValue(parsed.failureCount);
          if (failureCount)
            return `Geometry validation found ${failureCount} failing occurrence${failureCount === 1 ? '' : 's'}.`;
          if (Array.isArray(parsed.errors) && parsed.errors.length > 0) {
            const first = parsed.errors[0];
            if (isRecord(first) && typeof first.message === 'string') return first.message;
            return String(first);
          }
          if (typeof parsed.error === 'string' && parsed.error.trim()) return parsed.error.trim();
        }
      } catch {
        // Use the process error below when stdout is not JSON.
      }
    }
    if (typeof error.stderr === 'string' && error.stderr.trim()) {
      const lines = error.stderr.trim().split('\n');
      const failure = [...lines].reverse().find((line) => /FAILED|Error|error:/i.test(line));
      return (failure ?? lines.at(-1) ?? 'CAD validation failed.').trim();
    }
    if (typeof error.message === 'string') return error.message;
  }
  return 'CAD validation failed.';
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null;
}

function numberValue(value: unknown): number | undefined {
  return typeof value === 'number' && Number.isFinite(value) ? value : undefined;
}

function numberTuple(value: unknown): [number, number, number] | undefined {
  if (
    !Array.isArray(value) ||
    value.length !== 3 ||
    !value.every((item) => typeof item === 'number')
  )
    return undefined;
  return [value[0], value[1], value[2]];
}
