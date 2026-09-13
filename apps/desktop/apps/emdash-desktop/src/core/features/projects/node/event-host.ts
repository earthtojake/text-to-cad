import { createEventStreamHost } from '@emdash/wire/live';
import { projectsWireContract } from '../api';

export const projectEvents = createEventStreamHost(projectsWireContract.events);
