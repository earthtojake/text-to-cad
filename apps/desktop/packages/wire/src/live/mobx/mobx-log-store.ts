import { observable, runInAction } from 'mobx';
import type { LiveLogSnapshotData } from '../../api/channel';
import type { LogStore } from '../../live/replica/log';

export function createMobxLogStore(): LogStore {
  const text = observable.box('', { deep: false });

  return {
    reset(data: LiveLogSnapshotData) {
      runInAction(() => text.set(data.text));
    },
    append(chunk) {
      runInAction(() => text.set(`${text.get()}${chunk}`));
    },
    text() {
      return text.get();
    },
  };
}
