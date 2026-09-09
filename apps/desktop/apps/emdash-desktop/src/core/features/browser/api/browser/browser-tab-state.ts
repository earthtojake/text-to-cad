import type { BrowserSessionSnapshot } from '@core/primitives/browser/api';

export interface BrowserState {
  browserId: string;
  /** Session snapshot — kept current by BrowserTabResource's MobX reaction. */
  session: BrowserSessionSnapshot;
}

export interface BrowserOpenArgs {
  initialUrl?: string;
}
