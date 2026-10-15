// What a long wait says about itself, under the loading mark. The words are the
// locale's (`i18n/core.js`, read at render time by `LoadingIndicator`); the wait
// itself stays what it was.
import { translate } from "../../../i18n/core.js";

export function prolongedLoadingMessage(elapsedMs, connectionLost = null) {
  if (connectionLost) return translate("loading.waitingForResponse");
  if (elapsedMs < 10_000) return "";
  const seconds = Math.floor(elapsedMs / 1000);
  return seconds < 60
    ? translate("loading.secondsElapsed", { seconds })
    : translate("loading.minutesSecondsElapsed", { minutes: Math.floor(seconds / 60), seconds: seconds % 60 });
}
