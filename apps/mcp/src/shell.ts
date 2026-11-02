// The CAD app's resource, as a host keeps it: the shell (`host/shell.ts`), which loads the engine's app.
import { say, start } from './host/shell';

if (window.parent === window) say('CAD runs in an agent app.');
else void start().catch(error => say(error instanceof Error ? error.message : String(error)));
