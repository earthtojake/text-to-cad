export type Middleware<T> = (next: T) => T;

export function compose<T>(target: T, middlewares: readonly Middleware<T>[]): T {
  return middlewares.reduceRight((next, middleware) => middleware(next), target);
}
