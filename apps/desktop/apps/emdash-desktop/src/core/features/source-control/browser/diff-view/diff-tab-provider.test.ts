import { describe, expect, it } from 'vitest';
import { portablePath } from '@core/primitives/desktop-runtime/api';
import { commitRef } from '@core/primitives/git/api';
import { diffTabProvider } from './diff-tab-provider';

describe('diff tab identity', () => {
  it('keeps new diff tabs checkout-relative', () => {
    const payload = diffTabProvider.onBeforeOpen!(
      {
        activeFile: {
          path: portablePath('src/index.ts'),
          type: 'disk',
          group: 'disk',
          originalRef: commitRef('HEAD'),
        },
      },
      { viewId: 'task-1' }
    );

    expect(payload).toMatchObject({ path: 'src/index.ts', diffGroup: 'disk' });
  });
});
