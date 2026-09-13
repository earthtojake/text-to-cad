import { err, type Result } from '@emdash/shared';

export type MutationErrorMapper<E> = (error: unknown) => E | undefined;

export async function mapMutationErrors<T, E>(
  work: () => Result<T, E> | Promise<Result<T, E>>,
  mapError: MutationErrorMapper<E>
): Promise<Result<T, E>> {
  try {
    return await work();
  } catch (error) {
    const mapped = mapError(error);
    if (mapped !== undefined) return err(mapped);
    throw error;
  }
}
