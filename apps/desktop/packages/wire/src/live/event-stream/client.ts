import type { LiveUpdate } from '../../api/channel';
import { eventStreamDeltaSchema } from '../protocol';

export function eventFromUpdate<Event = unknown>(update: LiveUpdate): Event {
  return eventStreamDeltaSchema.parse(update.delta).event as Event;
}
