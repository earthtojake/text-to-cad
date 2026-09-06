declare global {
  interface Window {
    electronAPI: {
      getPathForFile: (file: File) => string;
      requestWirePort: (channel: string) => Promise<void>;
      onBootStuck: (callback: (payload: { stuckPhase: string }) => void) => () => void;
      requestBootEscape: (action: 'restart' | 'open-recovery') => Promise<void>;
      reportBootUsable: () => void;
    };
  }
}

export {};
