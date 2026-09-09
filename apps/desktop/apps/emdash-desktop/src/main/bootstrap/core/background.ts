import { log } from '@main/lib/logger';

type BackgroundTaskOptions = {
  onError?: (error: unknown) => void;
};

export function runInBackground(
  name: string,
  task: () => Promise<unknown> | unknown,
  options: BackgroundTaskOptions = {}
): void {
  void Promise.resolve()
    .then(task)
    .catch((error: unknown) => {
      if (options.onError) {
        options.onError(error);
        return;
      }
      log.error(`Background task '${name}' failed`, error);
    });
}
