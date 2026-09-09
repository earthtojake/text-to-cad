import { log } from '@main/lib/logger';
import { recordBootPhase } from './boot-report';

/**
 * Stack of currently running `step()` names (outermost first). The boot
 * watchdog reads it to report which phase a hung boot is stuck in.
 */
const activeSteps: string[] = [];

export function activeBootSteps(): readonly string[] {
  return activeSteps;
}

export interface Phase<Context> {
  readonly name: string;
  readonly critical?: boolean;
  run(context: Context): void | Promise<void>;
}

export async function runPhase<Context>(phase: Phase<Context>, context: Context): Promise<void> {
  const startedAt = Date.now();
  log.info('Lifecycle phase started', { phase: phase.name });
  try {
    await phase.run(context);
    log.info('Lifecycle phase completed', {
      phase: phase.name,
      durationMs: Date.now() - startedAt,
    });
  } catch (error) {
    log.error('Lifecycle phase failed', {
      phase: phase.name,
      durationMs: Date.now() - startedAt,
      error,
    });
    throw error;
  }
}

export async function step<T>(name: string, run: () => T | Promise<T>): Promise<T> {
  const startedAt = Date.now();
  log.info('Lifecycle phase started', { phase: name });
  activeSteps.push(name);
  try {
    const result = await run();
    const durationMs = Date.now() - startedAt;
    log.info('Lifecycle phase completed', { phase: name, durationMs });
    recordBootPhase(name, durationMs);
    return result;
  } catch (error) {
    log.error('Lifecycle phase failed', {
      phase: name,
      durationMs: Date.now() - startedAt,
      error,
    });
    throw error;
  } finally {
    const index = activeSteps.lastIndexOf(name);
    if (index !== -1) activeSteps.splice(index, 1);
  }
}

export async function stepOptional<T>(
  name: string,
  run: () => T | Promise<T>
): Promise<T | undefined> {
  try {
    return await step(name, run);
  } catch (error) {
    log.warn('Non-critical boot phase failed; continuing', { phase: name, error });
    return undefined;
  }
}
