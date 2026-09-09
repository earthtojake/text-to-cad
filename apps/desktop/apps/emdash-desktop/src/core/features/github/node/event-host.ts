import { createEventStreamHost } from '@emdash/wire/live';
import { githubContract } from '../api';

export const githubEvents = createEventStreamHost(githubContract.events);
