import { log } from '@main/lib/logger';

export async function withCompensation<T>({
  action,
  compensate,
  onCompensationError,
}: {
  action: () => Promise<T>;
  compensate: () => Promise<void>;
  onCompensationError?: (error: unknown) => void;
}): Promise<T> {
  try {
    return await action();
  } catch (error) {
    try {
      await compensate();
    } catch (compensationError) {
      if (onCompensationError) {
        onCompensationError(compensationError);
      } else {
        log.error('withCompensation: compensation failed', {
          error:
            compensationError instanceof Error
              ? compensationError.message
              : String(compensationError),
        });
      }
    }
    throw error;
  }
}
