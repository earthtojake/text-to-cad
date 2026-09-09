import { UpdateCard as UpdateCardUi, type UpdateStatus } from '@emdash/ui/react/components';
import { autorun } from 'mobx';
import { observer } from 'mobx-react-lite';
import type React from 'react';
import { getUpdateStore } from '@core/features/updates/contributions/app-stores';
import { PRODUCT_NAME } from '@core/primitives/app-identity/api/app-identity';

export const UpdateCard = observer(function UpdateCard(): React.JSX.Element {
  const update = getUpdateStore();
  const state = update.state;

  const availableVersion =
    update.availableVersion ?? (state.status === 'available' ? state.info?.version : undefined);
  const downloadVersion = availableVersion ?? update.currentVersion;

  let status: UpdateStatus;
  switch (state.status) {
    case 'available':
    case 'downloading':
      status = buildDownloadAvailable(downloadVersion);
      break;
    case 'downloaded':
    case 'installing':
      status = { type: 'update-install-available', onInstall: () => update.install() };
      break;
    case 'error':
      status = availableVersion ? buildDownloadAvailable(availableVersion) : { type: 'up-to-date' };
      break;
    default:
      status = { type: 'up-to-date' };
  }

  return (
    <UpdateCardUi
      currentVersion={update.currentVersion}
      appName={PRODUCT_NAME}
      status={status}
      error={state.status === 'error' ? { message: state.message } : undefined}
      onCheckForUpdates={() => update.check()}
    />
  );

  function buildDownloadAvailable(version: string): UpdateStatus {
    return {
      type: 'update-download-available',
      version,
      size: 0,
      onDownload: async (onProgress) => {
        const dispose = autorun(() => {
          const nextState = update.state;
          if (nextState.status === 'downloading' && nextState.progress?.percent != null) {
            onProgress(nextState.progress.percent);
          }
        });

        try {
          await update.download();
        } finally {
          dispose();
        }
      },
    };
  }
});
