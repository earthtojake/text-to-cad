import { BROWSER_DEFAULT_URL } from '@core/primitives/browser/api';

export function browserUrlInputText(url: string): string {
  return url === BROWSER_DEFAULT_URL ? '' : url;
}
