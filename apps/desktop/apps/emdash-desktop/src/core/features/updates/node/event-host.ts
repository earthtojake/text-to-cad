import { createEventStreamHost } from '@emdash/wire/live';
import { updatesContract } from '../api';

export const updateEvents = createEventStreamHost(updatesContract.events);
