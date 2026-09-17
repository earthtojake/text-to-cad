/** Browser page exit publishes viewer state; it never saves an edited document. */
export const browserLifecycle = {
  subscribeFlush(listener: () => void) {
    window.addEventListener('pagehide', listener);
    window.addEventListener('beforeunload', listener);
    return () => {
      window.removeEventListener('pagehide', listener);
      window.removeEventListener('beforeunload', listener);
    };
  },
};
