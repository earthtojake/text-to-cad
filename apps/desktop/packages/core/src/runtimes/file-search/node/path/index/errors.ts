export class RootWatchError extends Error {
  constructor(
    message: string,
    readonly cause: unknown
  ) {
    super(message);
    this.name = 'RootWatchError';
  }
}
