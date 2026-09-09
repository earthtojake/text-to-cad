import { createEventStreamHost } from '@emdash/wire/live';
import { conversationsContract } from '../api';

export const conversationWireEvents = createEventStreamHost(conversationsContract.events);
