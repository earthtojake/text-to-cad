export type BootSignals = {
  windowPhaseReady: boolean;
};

export class BootAborted extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'BootAborted';
  }
}

export function isBootAborted(error: unknown): error is BootAborted {
  return error instanceof BootAborted;
}
