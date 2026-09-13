export type Deferred<T = void> = {
  promise: Promise<T>;
  settled: boolean;
  resolve(value: T | PromiseLike<T>): void;
  reject(error?: unknown): void;
};

export function deferred<T = void>(): Deferred<T> {
  let resolve!: (value: T | PromiseLike<T>) => void;
  let reject!: (error?: unknown) => void;
  const result: Deferred<T> = {
    promise: Promise.resolve(undefined as never),
    settled: false,
    resolve(value) {
      result.settled = true;
      resolve(value);
    },
    reject(error) {
      result.settled = true;
      reject(error);
    },
  };
  result.promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return result;
}
