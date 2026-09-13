import { notesApi } from './contract';

const entries = Object.entries(notesApi);

console.log(
  'procedures:',
  entries.filter(([, def]) => def.kind === 'procedure').map(([name]) => name)
);
console.log(
  'live models:',
  entries.filter(([, def]) => def.kind === 'liveModel').map(([name]) => name)
);
console.log(
  'live states:',
  entries.flatMap(([name, def]) =>
    def.kind === 'liveModel' ? Object.keys(def.states).map((model) => `${name}.${model}`) : []
  )
);
console.log(
  'live logs:',
  entries.filter(([, def]) => def.kind === 'liveLog').map(([name]) => name)
);
