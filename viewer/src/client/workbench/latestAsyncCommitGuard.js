export function createLatestAsyncCommitGuard() {
  let latestToken = 0;
  return {
    begin() {
      latestToken += 1;
      return latestToken;
    },
    clear() {
      latestToken += 1;
    },
    isLatest(token) {
      return token === latestToken;
    }
  };
}
