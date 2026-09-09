/** Small FIFO lane used by one repository family. Rejections never poison later work. */
export class RepositoryFamilyLane {
  private tail: Promise<unknown> = Promise.resolve();

  run<T>(task: () => Promise<T>): Promise<T> {
    const next = this.tail.then(task, task);
    this.tail = next.catch(() => {});
    return next;
  }

  async drain(): Promise<void> {
    await this.tail;
  }
}
