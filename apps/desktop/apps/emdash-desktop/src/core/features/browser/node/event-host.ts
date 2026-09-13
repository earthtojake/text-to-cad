import { createEventStreamHost } from '@emdash/wire/live';
import { browserContract } from '../api';

export const browserEvents = createEventStreamHost(browserContract.events);
