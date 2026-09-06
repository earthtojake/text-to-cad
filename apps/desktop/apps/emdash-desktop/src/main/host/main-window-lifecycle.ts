export type MainWindowLifecycle = {
  canCreate(): boolean;
  disableCreation(): void;
};

/** Prevents tray/activation callbacks from recreating the normal UI in recovery mode. */
export function createMainWindowLifecycle(): MainWindowLifecycle {
  let creationEnabled = true;
  return {
    canCreate: () => creationEnabled,
    disableCreation: () => {
      creationEnabled = false;
    },
  };
}
