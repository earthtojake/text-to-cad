/**
 * The app's version, platform and dev flag, read once per mount.
 *
 * About prints it and compares cadgen's version against it, and it never
 * changes while the app is running, so it is a hook around one IPC call
 * rather than a store.
 */
import { useEffect, useState } from "react";

import type { AppInfo } from "@shared/types";

export function useAppInfo(): AppInfo | null {
  const [info, setInfo] = useState<AppInfo | null>(null);

  useEffect(() => {
    let live = true;
    void window.hardcore.app.info().then((next) => {
      if (live) {
        setInfo(next);
      }
    });
    return () => {
      live = false;
    };
  }, []);

  return info;
}
